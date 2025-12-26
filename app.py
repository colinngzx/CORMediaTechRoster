import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
import random
import collections

# --- PAGE SETUP ---
st.set_page_config(page_title="Roster Wizard", page_icon="🧙‍♂️", layout="wide")

# --- SESSION STATE INITIALIZATION ---
if 'stage' not in st.session_state:
    st.session_state.stage = 1

if 'event_details' not in st.session_state:
    st.session_state.event_details = pd.DataFrame(columns=["Date", "Holy Communion", "MSS Combined", "Notes"])

if 'roster_dates' not in st.session_state:
    st.session_state.roster_dates = []

if 'roster_df' not in st.session_state:
    st.session_state.roster_df = None

# Default Data (Example)
if 'roles_df' not in st.session_state:
    st.session_state.roles_df = pd.DataFrame({
        "Role": ["Team Lead", "Sound Crew", "Projectionist", "Stream Director", "Cam 1"]
    })

if 'team_members' not in st.session_state:
    st.session_state.team_members = pd.DataFrame({
        "Name": ["Ben", "mich ler", "Christine", "mich lo", "Colin", "Gavin", "Dannel", "Micah", "Jessica Tong", "Ming Zhe", "darrell", "Samuel", "Ee Li", "Timmy", "Jax", "Sherry", "Alan", "Vivian Ng", "Timothy"]
    })

# --- HELPER FUNCTIONS ---
def generate_sundays(start_date, num_weeks):
    dates = []
    current_date = start_date
    # Find next Sunday
    while current_date.weekday() != 6:
        current_date += timedelta(days=1)
    
    for _ in range(num_weeks):
        dates.append(current_date)
        current_date += timedelta(weeks=1)
    return dates

# ==========================================
# STEP 1: CONFIGURATION
# ==========================================
def render_step_1_config():
    st.title("🧙‍♂️ Roster Wizard")
    st.header("1. Setup")
    
    c1, c2 = st.columns(2)
    with c1:
        start_date = st.date_input("Start Date", datetime.today())
        weeks = st.number_input("How many weeks?", min_value=1, max_value=52, value=4)
    
    st.subheader("Roles & Team")
    rc1, rc2 = st.columns(2)
    with rc1:
        st.caption("Roles")
        st.session_state.roles_df = st.data_editor(st.session_state.roles_df, num_rows="dynamic", use_container_width=True)
    with rc2:
        st.caption("Team Members")
        st.session_state.team_members = st.data_editor(st.session_state.team_members, num_rows="dynamic", use_container_width=True)

    if st.button("Generate Dates ➡️", type="primary"):
        # Generate the initial list of Sundays
        dates = generate_sundays(pd.Timestamp(start_date), weeks)
        
        # logical merge with existing data if needed, but here we reset for simplicity
        data = []
        for d in dates:
            data.append({
                "Date": d,
                "Holy Communion": False,
                "MSS Combined": False,
                "Notes": ""
            })
        
        st.session_state.event_details = pd.DataFrame(data)
        st.session_state.stage = 2
        st.rerun()

# ==========================================
# STEP 2: REVIEW DATES (Read Only + Add/Remove)
# ==========================================
def render_step_2_details():
    st.title("🧙‍♂️ Roster Wizard")
    st.header("2. Review Dates")
    
    # 1. SHOW CURRENT DATES (Read-Only Table)
    current_df = st.session_state.event_details.copy()
    
    # Format the Date column for display purposes
    display_df = current_df.copy()
    display_df["Date"] = display_df["Date"].dt.strftime('%a, %d %b')
    
    st.table(display_df[["Date", "Holy Communion", "MSS Combined", "Notes"]])

    st.divider()

    # 2. ADD / REMOVE CONTROLS
    st.write("### Modify Dates")
    c1, c2 = st.columns(2)

    # --- ADD DATE SECTION ---
    with c1:
        st.write("**Add a new date**")
        new_date_input = st.date_input("Select date to add", value=None)
        if st.button("➕ Add Date"):
            if new_date_input:
                new_date_ts = pd.Timestamp(new_date_input)
                # Check if unique
                if new_date_ts not in st.session_state.event_details["Date"].values:
                    new_row = pd.DataFrame([{
                        "Date": new_date_ts,
                        "Holy Communion": False,
                        "MSS Combined": False,
                        "Notes": ""
                    }])
                    st.session_state.event_details = pd.concat([st.session_state.event_details, new_row], ignore_index=True)
                    st.session_state.event_details = st.session_state.event_details.sort_values(by="Date").reset_index(drop=True)
                    st.rerun()
                else:
                    st.warning("Date already exists.")

    # --- REMOVE DATE SECTION ---
    with c2:
        st.write("**Remove dates**")
        dates_list = st.session_state.event_details["Date"].dt.strftime('%a, %d %b %Y').tolist()
        dates_to_remove = st.multiselect("Select dates to remove", options=dates_list)
        
        if st.button("🗑️ Remove Selected"):
            if dates_to_remove:
                mask = ~st.session_state.event_details["Date"].dt.strftime('%a, %d %b %Y').isin(dates_to_remove)
                st.session_state.event_details = st.session_state.event_details[mask].reset_index(drop=True)
                st.rerun()

    st.markdown("<br>", unsafe_allow_html=True)
    
    col_back, col_next = st.columns([1, 5])
    if col_back.button("⬅ Back"):
        st.session_state.stage = 1
        st.rerun()
        
    if col_next.button("Confirm & Continue ➡️", type="primary"):
        st.session_state.roster_dates = st.session_state.event_details['Date'].tolist()
        st.session_state.stage = 3
        st.rerun()

# ==========================================
# STEP 3: AVAILABILITY (Placeholder)
# ==========================================
def render_step_3_availability():
    st.title("🧙‍♂️ Roster Wizard")
    st.header("3. Manage Availability")
    st.info("In a full version, team members would mark blackout dates here. Proceeding with full availability.")
    
    col_back, col_next = st.columns([1, 5])
    if col_back.button("⬅ Back"):
        st.session_state.stage = 2
        st.rerun()
        
    if col_next.button("Generate Roster ➡️", type="primary"):
        st.session_state.stage = 4
        st.rerun()

# ==========================================
# STEP 4: FINAL ROSTER (The Logic & The View)
# ==========================================
def render_step_4_results():
    st.header("4. Final Roster")
    st.caption("Auto-balancing Logic: Prioritizes those with fewer shifts and handles back-to-back prevention.")

    # --- 1. GENERATE ROSTER WITH LOGIC ---
    if st.session_state.roster_df is None:
        with st.spinner("Applying logic: 'Darrell max 1 Lead/Month'..."):
            
            roster = []
            roles = [c for c in st.session_state.roles_df['Role']]
            all_people = list(st.session_state.team_members['Name'].unique())

            # TRACKER: { '2024-01': { 'darrell': 0, 'Ben': 1 } }
            monthly_lead_tracker = {}

            for date in st.session_state.roster_dates:
                # 1. Identify Month
                month_key = date.strftime("%Y-%m")
                if month_key not in monthly_lead_tracker:
                    monthly_lead_tracker[month_key] = collections.Counter()

                # 2. Setup Row
                row = {"Date": date}
                details = st.session_state.event_details[
                    st.session_state.event_details["Date"] == date
                ].iloc[0]
                
                # Format details string
                details_str = []
                if details.get("Holy Communion", False): details_str.append("HC")
                if details.get("MSS Combined", False): details_str.append("Comb")
                row["Details"] = " ".join(details_str) if details_str else ""
                row["Notes"] = details["Notes"]

                # 3. ASSIGN ROLES
                daily_assigned = [] # Prevent double booking same day

                for role in roles:
                    candidates = [p for p in all_people if p not in daily_assigned]
                    random.shuffle(candidates)
                    
                    selected_person = "Unassigned"

                    # --- LOGIC: TEAM LEAD SPECIFIC ---
                    if role == "Team Lead":
                        for candidate in candidates:
                            # THE DARRELL RULE:
                            name_lower = str(candidate).lower()
                            if "darrell" in name_lower:
                                # Check if he has already led this month
                                if monthly_lead_tracker[month_key][candidate] >= 1:
                                    continue # Skip him
                            
                            selected_person = candidate
                            monthly_lead_tracker[month_key][candidate] += 1
                            break
                    
                    # --- LOGIC: OTHER ROLES ---
                    else:
                        if candidates:
                            selected_person = candidates[0]

                    row[role] = selected_person
                    if selected_person != "Unassigned":
                        daily_assigned.append(selected_person)

                roster.append(row)
            
            st.session_state.roster_df = pd.DataFrame(roster)

    # --- 2. DISPLAY STATISTICS (Dropdown) ---
    if st.session_state.roster_df is not None:
        
        df = st.session_state.roster_df
        role_cols = [c for c in df.columns if c not in ["Date", "Notes", "Details"]]
        
        all_assignments = df[role_cols].values.flatten()
        total_counts = collections.Counter(all_assignments)
        
        lead_counts = collections.Counter()
        # Count anything with "Lead" in the role name
        lead_role_names = [r for r in role_cols if "Lead" in r]
        for r_col in lead_role_names:
            lead_counts.update(df[r_col])

        stats_data = []
        unique_people = st.session_state.team_members['Name'].unique()
        
        for person in unique_people:
            if person == "Unassigned": continue
            stats_data.append({
                "Name": person,
                "Tech Shifts": total_counts[person],
                "Leads": lead_counts[person]
            })
            
        stats_df = pd.DataFrame(stats_data).sort_values(by=["Leads", "Tech Shifts"], ascending=False)

        # THE DROP DOWN MENU
        with st.expander("View Shift Statistics", expanded=True):
            st.table(stats_df.set_index("Name"))

    # --- 3. SHOW MONTHLY VIEWS (Transposed) ---
    if st.session_state.roster_df is not None:
        df = st.session_state.roster_df.copy()
        df['Month'] = df['Date'].dt.month_name()
        unique_months = df['Date'].dt.to_period("M").unique()

        for period in unique_months:
            month_name = period.strftime("%B")
            month_mask = df['Date'].dt.to_period("M") == period
            month_data = df[month_mask].copy()
            
            st.subheader(month_name)
            
            # 1. Format Dates as Strings
            month_data['DateStr'] = month_data['Date'].dt.strftime('%d-%b')
            
            # 2. Transpose (Pivot)
            cols_to_show = ["Details"] + [c for c in st.session_state.roles_df['Role']]
            display_mx = month_data.set_index('DateStr')[cols_to_show].T
            display_mx.index.name = "Role"
            
            st.dataframe(display_mx, use_container_width=True)

    # --- 4. EXPORT & REGENERATE ---
    st.markdown("<br>", unsafe_allow_html=True)
    c1, c2 = st.columns(2)
    with c1:
        st.download_button(
            "📥 Download CSV",
            data=st.session_state.roster_df.to_csv(index=False).encode('utf-8'),
            file_name="roster.csv",
            mime="text/csv"
        )
    with c2:
        if st.button("🔄 Regenerate Roster"):
            st.session_state.roster_df = None
            st.rerun()
    
    if st.button("⬅ Start Over"):
        st.session_state.stage = 1
        st.session_state.roster_df = None
        st.rerun()

# --- MAIN APP ROUTER ---
def main():
    if st.session_state.stage == 1:
        render_step_1_config()
    elif st.session_state.stage == 2:
        render_step_2_details()
    elif st.session_state.stage == 3:
        render_step_3_availability()
    elif st.session_state.stage == 4:
        render_step_4_results()

if __name__ == "__main__":
    main()
