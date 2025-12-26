import streamlit as st
import pandas as pd
import datetime
import calendar
import random
from collections import defaultdict, Counter

# ==========================================
# 1. CONFIGURATION & ROLES
# ==========================================
class CONFIG:
    # 1. Sound Crew (Needs 1)
    # 2. Projectionist (Needs 1)
    # 3. Stream Director (Needs 1)
    # 4. Cam 1 (Needs 1)
    # 5. Cam 2 (Optional/Placeholder)
    # 6. Team Lead (Derived from scheduled crew)
    
    ROLES = [
        {"label": "Sound Crew",      "key": "Sound",      "count": 1},
        {"label": "Projectionist",   "key": "Projection", "count": 1},
        {"label": "Stream Director", "key": "Stream Dir", "count": 1},
        {"label": "Cam 1",           "key": "Cam 1",      "count": 1},
        # Cam 2 is usually empty/placeholder, handled manually in logic
    ]

# ==========================================
# 2. ROSTER LOGIC ENGINE
# ==========================================
class RosterEngine:
    def __init__(self, team_df):
        self.team_df = team_df.fillna(0)
        self.history = []  # List of {date, role, name}
        self.points = defaultdict(int)        # Total "Business" score
        self.role_counts = defaultdict(lambda: defaultdict(int)) # name -> role -> count
        self.prev_week_crew = [] # Who served last week? (To prevent back-to-back)

    def get_candidates_for_role(self, role_col):
        """Return list of names who have '1' for this role."""
        return self.team_df[self.team_df[role_col] == 1]['Name'].tolist()

    def get_tech_candidate(self, role_col, unavailable_names, current_crew, week_index):
        """
        Pick the best person for a specific role (Sound, Projection, etc).
        Rules:
        1. Must be capable (marked 1 in Excel).
        2. Not unavailable.
        3. Not already working this Sunday (in current_crew).
        4. PREFERENCE: Someone who didn't work last week.
        5. PREFERENCE: Lowest 'Load Score' (balance the work).
        """
        candidates = self.get_candidates_for_role(role_col)
        
        # Filter exclusions
        valid = [c for c in candidates if c not in unavailable_names and c not in current_crew]
        
        if not valid:
            return "" # No one available

        # --- SCORING SYSTEM ---
        # We want the person with the LOWEST score.
        scored_candidates = []
        for p in valid:
            score = 0
            
            # 1. WORKLOAD BALANCE (Major Factor)
            # Count how many times they have done *Any Tech Role* assigned so far
            tech_roles = ["Sound", "Projection", "Stream Dir", "Cam 1"]
            total_shifts = sum(self.role_counts[p][r] for r in tech_roles)
            score += (total_shifts * 10) 

            # 2. AVOID BACK-TO-BACK (Medium Factor)
            if p in self.prev_week_crew:
                score += 50
            
            # 3. ROTATION GAP (Minor Factor)
            # If they did THIS specific role recently, bump score slightly
            # (Simplistic check: randomly shuffle creates variety, but we add a small noise factor)
            score += random.randint(0, 2) 

            scored_candidates.append((score, p))
        
        # Sort by score ascending (lowest score wins)
        scored_candidates.sort(key=lambda x: x[0])
        
        # Pick winner
        winner = scored_candidates[0][1]
        
        # Update State
        self.points[winner] += 1
        self.role_counts[winner][role_col] += 1
        return winner

    def assign_lead(self, current_crew, unavailable_names, week_index):
        """
        Assign Team Lead from the people ALREADY scheduled in current_crew.
        Must be a 'Lead' capable person.
        """
        # Find who in the current crew is capable of leading
        leads = self.team_df[self.team_df['Lead'] == 1]['Name'].tolist()
        possible_leads = [p for p in current_crew if p in leads]
        
        if not possible_leads:
            # If no one in crew is a lead, try to pull an external lead? 
            # For this script, we return "TBD" or empty if no leader is present.
            return ""

        # Logic: Pick the person with the fewest LEAD shifts so far
        best_lead = None
        min_lead_shifts = 999
        
        for p in possible_leads:
            c = self.role_counts[p]['Lead']
            # Bonus: Try not to give Lead to the Stream Director if possible (optional preference)
            # but for now, just strictly numeric balancing
            if c < min_lead_shifts:
                min_lead_shifts = c
                best_lead = p
            elif c == min_lead_shifts:
                # Random tie break
                if random.random() > 0.5:
                    best_lead = p
        
        if best_lead:
            self.role_counts[best_lead]['Lead'] += 1
            return best_lead
        return ""

    def get_stats(self):
        """Return a dataframe of how many times each person served."""
        data = []
        all_names = self.team_df['Name'].tolist()
        for name in all_names:
            row = {"Name": name}
            total_tech = 0
            for r_conf in CONFIG.ROLES:
                key = r_conf['key']
                count = self.role_counts[name][key]
                row[key] = count
                total_tech += count
            row["Lead"] = self.role_counts[name]["Lead"]
            row["Total (Tech Only)"] = total_tech
            data.append(row)
        return pd.DataFrame(data).sort_values("Total (Tech Only)", ascending=False)


# ==========================================
# 3. HELPER CLASSES
# ==========================================
class RosterDateSpec:
    def __init__(self, date_obj, is_hc, is_combined, specific_notes=""):
        self.date = date_obj
        self.is_hc = is_hc
        self.is_combined = is_combined
        self.notes = specific_notes

    @property
    def display_details(self):
        parts = []
        if self.is_combined: parts.append("MSS Combined")
        if self.is_hc: parts.append("HC")
        if self.notes: parts.append(self.notes)
        return " / ".join(parts)


# ==========================================
# 4. STREAMLIT APP
# ==========================================
def main():
    st.set_page_config(page_title="SWS Scheduler", layout="wide")
    st.title("Simple Worship Scheduler 2026")

    # --- SESSION STATE INITIALIZATION ---
    if 'stage' not in st.session_state: st.session_state.stage = 1
    if 'team_data' not in st.session_state: st.session_state.team_data = None
    if 'roster_dates' not in st.session_state: st.session_state.roster_dates = [] 
    if 'unavailability_by_person' not in st.session_state: st.session_state.unavailability_by_person = {}

    # --- STEP 1: LOAD TEAM DATA ---
    if st.session_state.stage == 1:
        st.header("Step 1: Upload Team List")
        st.write("Upload a CSV/Excel with columns: Name, Sound, Projection, Stream Dir, Cam 1, Lead. (Use 1 for yes, 0 for no)")
        
        # Hardcoded default for demo if no file uploaded
        default_data = {
            "Name": ["Samuel","Gavin","Ben","Timothy","Micah","mich lo","mich ler","Jessica Tong","Vivian Ng","Ee Li","Dannel","Jax","Ming Zhe","Alan","Sherry","Christine","Colin","Timmy"],
            "Sound":      [1,1,1,0,1,0,1,0,0,0,0,0,0,0,0,0,0,0],
            "Projection": [0,1,0,0,0,1,0,0,0,1,0,0,0,0,0,1,0,1],
            "Stream Dir": [0,0,0,1,0,1,0,1,1,0,1,1,1,0,0,0,0,0],
            "Cam 1":      [0,0,0,1,0,0,0,0,1,0,0,1,1,1,1,0,1,0],
            "Lead":       [0,1,1,0,0,1,0,0,0,0,0,0,0,0,0,0,0,0]
        }
        
        uploaded_file = st.file_uploader("Upload Team File", type=['csv', 'xlsx'])
        
        if uploaded_file:
            if uploaded_file.name.endswith('.csv'):
                df = pd.read_csv(uploaded_file)
            else:
                df = pd.read_excel(uploaded_file)
            st.success("File uploaded!")
            if st.button("Next Rules"):
                st.session_state.team_data = df
                st.session_state.stage = 2
                st.rerun()
        else:
            if st.button("Use Demo Data"):
                st.session_state.team_data = pd.DataFrame(default_data)
                st.session_state.stage = 2
                st.rerun()

    # --- STEP 2: SELECT DATES ---
    elif st.session_state.stage == 2:
        st.header("Step 2: Configure Dates")
        
        c1, c2 = st.columns(2)
        with c1:
            start_d = st.date_input("Start Date", datetime.date(2026, 1, 1))
        with c2:
            num_months = st.number_input("How many months to generate?", 1, 12, 3)

        # Generate Sundays
        if st.button("Generate Sunday List"):
            sundays = []
            current = start_d
            # Fast forward to first Sunday
            while current.weekday() != 6:
                current += datetime.timedelta(days=1)
            
            # Collect Sundays for X months roughly
            end_date = start_d + datetime.timedelta(days=30*num_months)
            
            while current < end_date:
                sundays.append(current)
                current += datetime.timedelta(days=7)
            
            # Initialize structure in session state
            st.session_state.roster_dates = []
            for s in sundays:
                # Default logic: First Sunday often HC? 
                is_hc = False
                is_combined = False
                
                # Heuristic: 1st Sunday of month = HC & Combined
                if s.day <= 7:
                    is_hc = True
                    is_combined = True
                
                st.session_state.roster_dates.append({
                    "Date": s,
                    "HC": is_hc,
                    "Combined": is_combined,
                    "Notes": ""
                })
        
        if st.session_state.roster_dates:
            st.divider()
            st.write("Customize specific Sundays:")
            
            updated_dates = []
            for i, r_data in enumerate(st.session_state.roster_dates):
                d_str = r_data['Date'].strftime("%d-%b-%Y")
                
                with st.expander(f"{d_str}", expanded=False):
                    c_a, c_b, c_c = st.columns(3)
                    new_hc = c_a.checkbox(f"Holy Communion ({i})", value=r_data['HC'])
                    new_comb = c_b.checkbox(f"Combined Service ({i})", value=r_data['Combined'])
                    new_note = c_c.text_input(f"Special Note ({i})", value=r_data['Notes'])
                    
                    updated_dates.append({
                        "Date": r_data['Date'],
                        "HC": new_hc,
                        "Combined": new_comb,
                        "Notes": new_note
                    })
            
            st.session_state.roster_dates = updated_dates

            if st.button("Confirm Dates & Continue"):
                st.session_state.stage = 3
                st.rerun()

    # --- STEP 3: UNAVAILABILITY ---
    elif st.session_state.stage == 3:
        st.header("Step 3: Unavailability")
        st.write("Mark who is AWAY on specific dates.")
        
        df_team = st.session_state.team_data
        names = df_team['Name'].tolist()
        
        # Display valid dates for reference
        date_strs = [d['Date'].strftime("%Y-%m-%d") for d in st.session_state.roster_dates]
        
        # User input: select person, select dates
        c1, c2 = st.columns(2)
        with c1:
            selected_person = st.selectbox("Select Person", names)
        with c2:
            current_blocks = st.session_state.unavailability_by_person.get(selected_person, [])
            # Convert string dates back to list for multiselect if needed, but simple multiselect is easier
            blocked_dates = st.multiselect("Select Unavailable Dates", date_strs, default=current_blocks)
        
        if st.button("Update Person"):
            st.session_state.unavailability_by_person[selected_person] = blocked_dates
            st.success(f"Updated unavailability for {selected_person}")

        # Show summary
        st.write("### Current Blockouts:")
        if st.session_state.unavailability_by_person:
            st.json(st.session_state.unavailability_by_person)
        else:
            st.caption("No blockouts set.")

        if st.button("Generate Roster"):
            st.session_state.stage = 4
            st.rerun()

    # --- STEP 4: FINAL ROSTER WITH BALANCING LOGIC ---
    elif st.session_state.stage == 4:
        st.header("Step 4: Final Roster")
        st.caption("Auto-optimizing for the most balanced workload...")

        df_team = st.session_state.team_data
        
        # 1. Prepare Availability Dictionary
        unavailable_by_date_str = defaultdict(list)
        for name, unavailable_dates in st.session_state.unavailability_by_person.items():
            for d_str in unavailable_dates:
                unavailable_by_date_str[d_str].append(name)

        # 2. RUN SIMULATION LOOP (Monte Carlo)
        # We generate the roster 50 times and keep the one with the most even distribution of shifts
        
        best_schedule = []
        best_stats = pd.DataFrame()
        best_engine = None
        min_std_dev = float('inf')  # Start with infinite variance
        
        # Shows a little spinner while calculating
        with st.spinner("Finding the fairest schedule..."):
            iterations = 50
            for i in range(iterations):
                # New engine per run to reset counters
                temp_engine = RosterEngine(df_team)
                temp_schedule = []
                
                # --- GENERATE SINGLE ROSTER ---
                for idx, r_data in enumerate(st.session_state.roster_dates):
                    d_obj = r_data['Date']
                    spec = RosterDateSpec(d_obj, r_data['HC'], r_data['Combined'], r_data['Notes'])
                    d_str_key = str(d_obj) # Matches YYYY-MM-DD
                    unavailable_today = unavailable_by_date_str.get(d_str_key, [])
                    
                    current_crew = []
                    
                    date_entry = {
                        "Service Dates": d_obj.strftime("%d-%b"),
                        "_full_date": d_obj,
                        "Additional Details": spec.display_details
                    }
                    
                    # Assign Roles
                    for role_conf in CONFIG.ROLES:
                        person = temp_engine.get_tech_candidate(role_conf['key'], unavailable_today, current_crew, idx)
                        date_entry[role_conf['label']] = person
                        if person: current_crew.append(person)
                    
                    # Manual placeholder (Cam 2)
                    date_entry["Cam 2"] = "" 
                    
                    # Assign Lead
                    t_lead = temp_engine.assign_lead(current_crew, unavailable_today, idx)
                    date_entry["Team Lead"] = t_lead
                    
                    temp_schedule.append(date_entry)
                    temp_engine.prev_week_crew = current_crew
                
                # --- CALCULATE FAIRNESS SCORE ---
                # We calculate the Standard Deviation of "Tech Shifts". 
                # Lower Std Dev means everyone has roughly the same amount of work.
                stats_df = temp_engine.get_stats()
                
                if not stats_df.empty:
                    # Calculate variance of shifts
                    current_std = stats_df['Total (Tech Only)'].std()
                    
                    # Tie-breaker: If variance is lower, OR equal but maybe lead shifts balanced better...
                    # For now, strict lowest Tech Shift Variance wins.
                    if current_std < min_std_dev:
                        min_std_dev = current_std
                        best_schedule = temp_schedule
                        best_stats = stats_df
                        best_engine = temp_engine
                else:
                    # Fallback if empty (shouldn't happen)
                    best_schedule = temp_schedule
                    best_stats = stats_df

        # 3. DISPLAY RESULTS (Using the best found schedule)
        df_schedule = pd.DataFrame(best_schedule)
        
        # Transpose logic for display
        col_headers = df_schedule['Service Dates'].tolist()
        df_for_t = df_schedule.drop(columns=['Service Dates', '_full_date'])
        
        df_transposed = df_for_t.T
        df_transposed.columns = col_headers
        
        desired_order = [
            "Additional Details", "Sound Crew", "Projectionist", "Stream Director", "Cam 1", "Cam 2", "Team Lead"
        ]
        df_final_master = df_transposed.reindex(desired_order).fillna("")

        # Display Grouped by Month
        dates_by_month = defaultdict(list)
        for entry in best_schedule:
            d_obj = entry['_full_date']
            month_key = d_obj.strftime("%B %Y")
            col_name = entry['Service Dates']
            dates_by_month[month_key].append(col_name)

        for month_name, col_names in dates_by_month.items():
            st.subheader(month_name)
            valid_cols = [c for c in col_names if c in df_final_master.columns]
            if valid_cols:
                st.dataframe(df_final_master[valid_cols], use_container_width=True)

        with st.expander("Show Load Statistics (Optimized)", expanded=True):
            if not best_stats.empty:
                st.dataframe(best_stats, use_container_width=True)
            else:
                st.write("No stats available.")

        # 4. DOWNLOAD
        csv = df_final_master.to_csv().encode('utf-8')
        col1, col2 = st.columns(2)
        with col1:
             st.download_button("📥 Download Master CSV", csv, "sws_roster_final.csv", "text/csv")
        with col2:
            if st.button("Start Over"):
                st.session_state.stage = 1
                st.session_state.roster_dates = []
                st.session_state.unavailability_by_person = {}
                st.rerun()

if __name__ == "__main__":
    main()
