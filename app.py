import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
from collections import defaultdict, Counter
import random

# ==========================================
# 1. CONFIGURATION & STYLES
# ==========================================
st.set_page_config(page_title="Roster Scheduler", layout="wide")

class AppConfig:
    DATE_FMT_INPUT = "%Y-%m-%d"
    DATE_FMT_DISPLAY = "%d-%b"
    DATE_FMT_MONTH = "%B %Y"

# Custom CSS for the HTML view
TABLE_CSS = """
<style>
    table.roster-table {
        width: 100%;
        border-collapse: collapse;
        font-family: Arial, sans-serif;
        font-size: 14px;
        color: #000;
        background-color: #fff;
    }
    .roster-table th {
        background-color: #4472c4;
        color: white;
        text-align: center;
        padding: 8px;
        border: 1px solid #000;
    }
    .roster-table td {
        border: 1px solid #000;
        padding: 8px;
        text-align: center;
    }
    .roster-table tr:nth-child(even) {
        background-color: #d9e1f2;
    }
    .roster-table tr:nth-child(odd) {
        background-color: #ffffff;
    }
    .date-col { font-weight: bold; white-space: nowrap; }
    .details-col { text-align: left; font-style: italic; }
</style>
"""
st.markdown(TABLE_CSS, unsafe_allow_html=True)

# ==========================================
# 2. DATA MODELS
# ==========================================
class Role:
    def __init__(self, label, key):
        self.label = label
        self.key = key

class Roles:
    VM = Role("Vision Mixer", "vm")
    SOUND = Role("Sound", "sound")
    LIGHTS = Role("Lights", "lights")
    CAM1 = Role("Cam 1", "cam1")
    CAM2 = Role("Cam 2", "cam2")
    PPT = Role("ProPresenter", "ppt")
    LEAD = Role("Team Lead", "lead")
    DETAILS = Role("Details", "details")

    @classmethod
    def get_tech_roles(cls):
        # Roles filled by the algorithm (excluding Lead/Cam2 initially)
        return [cls.VM, cls.SOUND, cls.LIGHTS, cls.CAM1, cls.PPT]

class TeamMembers:
    TECHS = [
        "Alan", "Ben", "Christine", "Colin", "Dannel", 
        "Feli", "Gavin", "Jax", "Jessica", "Micah", 
        "Min", "Mitch", "Sam", "Siew Mun"
    ]
    LEADS = ["Ben", "Gavin", "Mitch"]

class SessionState:
    def __init__(self):
        # Step 1: Dates
        if 'start_date' not in st.session_state: st.session_state.start_date = datetime.today()
        if 'end_date' not in st.session_state: st.session_state.end_date = datetime.today() + timedelta(days=60)
        
        # Step 2: Team
        if 'selected_techs' not in st.session_state: st.session_state.selected_techs = TeamMembers.TECHS
        if 'selected_leads' not in st.session_state: st.session_state.selected_leads = TeamMembers.LEADS
        
        # Step 3: Unavailability
        if 'unavailability' not in st.session_state: st.session_state.unavailability = defaultdict(list)
        
        # Logic State
        if 'stage' not in st.session_state: st.session_state.stage = 1
        if 'roster_dates' not in st.session_state: st.session_state.roster_dates = []
        if 'master_schedule' not in st.session_state: st.session_state.master_schedule = None

    def reset(self):
        st.session_state.stage = 1
        st.session_state.master_schedule = None
        st.session_state.roster_dates = []

    @property
    def stage(self): return st.session_state.stage
    @stage.setter
    def stage(self, val): st.session_state.stage = val

    @property
    def start_date(self): return st.session_state.start_date
    @property
    def end_date(self): return st.session_state.end_date
    
    @property
    def selected_techs(self): return st.session_state.selected_techs
    @property
    def selected_leads(self): return st.session_state.selected_leads
    
    @property
    def unavailability(self): return st.session_state.unavailability
    @property
    def roster_dates(self): return st.session_state.roster_dates
    
    @property
    def master_schedule(self): return st.session_state.master_schedule
    @master_schedule.setter
    def master_schedule(self, val): st.session_state.master_schedule = val

# ==========================================
# 3. ROSTER ENGINE
# ==========================================
class RosterEngine:
    def __init__(self, techs, leads):
        self.techs = techs
        self.leads = leads
        # History tracking for fairness
        self.history = defaultdict(int)
        self.role_history = defaultdict(lambda: defaultdict(int))
        self.lead_history = defaultdict(int)
        self.prev_crew = []

    def get_candidate(self, role, unavailable, current_crew, seed_salt):
        # Filter available people
        candidates = [
            p for p in self.techs 
            if p not in unavailable 
            and p not in current_crew
            and p not in self.prev_crew  # Avoid consecutive weeks
        ]
        
        if not candidates:
            # Relax consecutive rule if desperate
            candidates = [p for p in self.techs if p not in unavailable and p not in current_crew]
        
        if not candidates:
            return "TBD" # No one available

        # Score candidates: lower score is better (less shifts assigned so far)
        # We add random fuzz to shuffle people with equal shift counts
        random.seed(seed_salt + len(current_crew)) 
        scored = []
        for p in candidates:
            score = self.history[p] + (self.role_history[p][role.key] * 0.5) + random.uniform(0, 0.9)
            scored.append((score, p))
            
        scored.sort()
        winner = scored[0][1]
        
        # Update stats
        self.history[winner] += 1
        self.role_history[winner][role.key] += 1
        return winner

    def assign_lead(self, current_crew, seed_salt):
        # 1. Try to pick from current crew who is also a Lead
        internal_leads = [p for p in current_crew if p in self.leads]
        
        if internal_leads:
            random.seed(seed_salt)
            # Pick the one who has led the least
            internal_leads.sort(key=lambda x: self.lead_history[x] + random.uniform(0, 0.9))
            winner = internal_leads[0]
            self.lead_history[winner] += 1
            return winner
            
        # 2. If no crew member is a lead, you might need an external lead (or leave blank)
        # For this specific roster logic, usually one of the crew is the lead. 
        # If not, we return a placeholder.
        return "TBD (No Lead in Crew)"

# ==========================================
# 4. VIEW HELPERS
# ==========================================
class HtmlGenerator:
    @staticmethod
    def render_month_block(month_name, df_subset):
        if df_subset.empty: return
        
        headers = df_subset.columns.tolist()
        
        # Build HTML Table
        html = f"<h3>{month_name}</h3>"
        html += '<table class="roster-table">'
        
        # Header Row
        html += '<thead><tr>'
        for h in headers:
            html += f'<th>{h}</th>'
        html += '</tr></thead>'
        
        # Body
        html += '<tbody>'
        for _, row in df_subset.iterrows():
            html += '<tr>'
            for col in headers:
                val = row[col]
                cls = "date-col" if col == "Service Date" else ("details-col" if col == Roles.DETAILS.label else "")
                html += f'<td class="{cls}">{val}</td>'
            html += '</tr>'
        html += '</tbody></table>'
        
        st.markdown(html, unsafe_allow_html=True)

def render_live_stats_table(df: pd.DataFrame):
    """Generates the stats table in an expander at the top."""
    if df is None or df.empty:
        return

    # 1. Define Columns to scan
    # Check tech columns + Cam 2 + Lead
    tech_cols = [r.label for r in Roles.get_tech_roles()] + [Roles.CAM2.label]
    lead_col = Roles.LEAD.label
    
    # 2. Flatten and Count
    tech_flat = []
    lead_flat = []
    
    for col in df.columns:
        if col in tech_cols:
            # Get valid names (ignore TBD/Empty)
            names = df[col].astype(str).tolist()
            tech_flat.extend([n.strip() for n in names if len(n) > 2 and "TBD" not in n and n.lower() != 'nan'])
        elif col == lead_col:
            names = df[col].astype(str).tolist()
            lead_flat.extend([n.strip() for n in names if len(n) > 2 and "TBD" not in n and n.lower() != 'nan'])

    t_counts = Counter(tech_flat)
    l_counts = Counter(lead_flat)
    
    # 3. Get all unique people
    all_people = sorted(list(set(t_counts.keys()) | set(l_counts.keys())))
    
    # 4. Build Data
    stats_data = []
    for p in all_people:
        t = t_counts.get(p, 0)
        l = l_counts.get(p, 0)
        stats_data.append({
            "Name": p,
            "Tech Shifts": t,
            "Lead Shifts": l,
            "Total": t + l
        })
        
    stats_df = pd.DataFrame(stats_data)

    # 5. Render
    with st.expander("📊 Live Load Statistics (Updates automatically)", expanded=True):
        st.dataframe(
            stats_df,
            use_container_width=True,
            hide_index=True,
            column_config={
                "Name": st.column_config.TextColumn("Name"),
                "Tech Shifts": st.column_config.NumberColumn("Tech Shifts", format="%d"),
                "Lead Shifts": st.column_config.NumberColumn("Lead Shifts", format="%d"),
                "Total": st.column_config.NumberColumn("Total", format="%d"),
            }
        )

# ==========================================
# 5. STEP RENDERING
# ==========================================

def render_step_1_dates(state: SessionState):
    st.header("Step 1: Set Date Range")
    
    c1, c2 = st.columns(2)
    start = c1.date_input("Start Date", value=state.start_date)
    end = c2.date_input("End Date", value=state.end_date)
    
    if start > end:
        st.error("End date must be after start date.")
        return

    # Generate dates
    dates = []
    curr = start
    while curr <= end:
        # 6 = Sunday, 2 = Wednesday
        if curr.weekday() in [6, 2]:
            dates.append(curr)
        curr += timedelta(days=1)
    
    st.info(f"Generated {len(dates)} service dates (Sundays & Wednesdays).")
    
    # Config for specific dates
    st.subheader("Date Configuration")
    
    # Convert existing if reloading
    editor_data = []
    for d in dates:
        # Check if we have existing data for this date
        existing = next((item for item in state.roster_dates if item["Date"] == d), None)
        if existing:
            editor_data.append(existing)
        else:
            is_wed = (d.weekday() == 2)
            editor_data.append({
                "Date": d,
                "Day": d.strftime("%A"),
                "Include?": True,
                "Combined": False, # MSS Combined
                "HC": False, # Holy Communion
                "Notes": "Prayer Meeting" if is_wed else ""
            })
    
    df_dates = pd.DataFrame(editor_data)
    
    edited_df = st.data_editor(
        df_dates,
        column_config={
            "Date": st.column_config.DateColumn("Date", format="DD-MMM"),
            "Include?": st.column_config.CheckboxColumn("Include?", default=True),
        },
        use_container_width=True,
        hide_index=True,
        num_rows="dynamic"
    )

    if st.button("Next: Choose Team →"):
        # Save filtered list
        valid = edited_df[edited_df["Include?"] == True].to_dict('records')
        state.roster_dates = valid
        
        # Update raw dates for persistence
        state.start_date = start
        state.end_date = end
        
        state.stage = 2
        st.rerun()

def render_step_2_team(state: SessionState):
    st.header("Step 2: Team Selection")
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.subheader("Tech Team Pool")
        # Default options from constants
        selected_t = st.multiselect(
            "Select active technicians",
            options=TeamMembers.TECHS,
            default=state.selected_techs
        )
        
    with col2:
        st.subheader("Leaders Pool")
        selected_l = st.multiselect(
            "Select active leads",
            options=selected_t, # Leads must be in tech team
            default=[p for p in state.selected_leads if p in selected_t]
        )
    
    st.markdown("---")
    c1, c2 = st.columns([1, 10])
    if c1.button("← Back"):
        state.stage = 1
        st.rerun()
    if c2.button("Next: Unavailability →"):
        state.selected_techs = selected_t
        state.selected_leads = selected_l
        state.stage = 3
        st.rerun()

def render_step_3_unavailability(state: SessionState):
    st.header("Step 3: Unavailability")
    st.markdown("Select dates where a person is **NOT** available.")

    # Get valid dates from step 1
    valid_dates_obj = [x['Date'] for x in state.roster_dates]
    
    # We create a multiselect for every person
    st.write("Expand a person to set their off-dates.")
    
    people = sorted(state.selected_techs)
    
    # Grid layout
    cols = st.columns(3)
    
    new_unavailability = defaultdict(list)
    
    for i, person in enumerate(people):
        col = cols[i % 3]
        with col:
            # Pre-fill
            default_dates = [d for d in state.unavailability.get(person, []) if d in valid_dates_obj]
            
            excludes = st.multiselect(
                f"🚫 {person}",
                options=valid_dates_obj,
                default=default_dates,
                format_func=lambda x: x.strftime("%d-%b"),
                key=f"un_{person}"
            )
            new_unavailability[person] = excludes

    st.markdown("---")
    c1, c2 = st.columns([1, 10])
    if c1.button("← Back"):
        state.stage = 2
        st.rerun()
        
    if c2.button("Generate Roster →", type="primary"):
        state.unavailability = new_unavailability
        state.stage = 4
        # Force fresh generation
        state.master_schedule = None 
        st.rerun()

def render_step_4_final(state: SessionState, engine: RosterEngine):
    st.header("Step 4: Roster Dashboard")

    # --- 1. GENERATION LOGIC ---
    # Only generate if not already generated or if "Regenerate" was clicked
    if state.master_schedule is None:
        raw_rows = []
        unavailable_map = defaultdict(list)
        
        # Remap unavailability for fast lookup: DateString -> [Persons]
        for name, dates in state.unavailability.items():
            for d in dates:
                unavailable_map[str(d)].append(name)

        for idx, entry in enumerate(state.roster_dates):
            d_obj = entry['Date']
            if pd.isna(d_obj): continue
            
            # Create details string
            notes = [entry.get('Notes', '')]
            if entry.get('Combined'): notes.insert(0, "MSS Combined")
            if entry.get('HC'): notes.insert(0, "HC")
            desc = " / ".join([n for n in notes if n])
            
            row = {
                "Service Date": d_obj.strftime(AppConfig.DATE_FMT_DISPLAY),
                "_month_group": d_obj.strftime(AppConfig.DATE_FMT_MONTH),
                Roles.DETAILS.label: desc
            }
            
            curr_crew = []
            unavailable_today = unavailable_map.get(str(d_obj), [])
            
            # Assign Tech Roles
            for role in Roles.get_tech_roles():
                person = engine.get_candidate(role, unavailable_today, curr_crew, idx)
                row[role.label] = person
                if person and person != "TBD":
                    curr_crew.append(person)
            
            # Cam 2 is usually manual or blank initially
            row[Roles.CAM2.label] = "" 
            
            # Assign Lead
            lead = engine.assign_lead(curr_crew, idx)
            row[Roles.LEAD.label] = lead
            
            raw_rows.append(row)
            
            # Set history constraint for next loop
            engine.prev_crew = curr_crew 
        
        state.master_schedule = pd.DataFrame(raw_rows)

    # --- 2. LIVE STATS TABLE (Top) ---
    render_live_stats_table(state.master_schedule)
    
    st.markdown("---")

    # --- 3. EDITOR INTERFACE ---
    df_master = state.master_schedule
    
    # Define Column Order
    display_cols = [Roles.DETAILS.label] + [r.label for r in Roles.get_tech_roles()] + [Roles.CAM2.label, Roles.LEAD.label]
    
    st.subheader("✏️ Roster Editor")
    
    has_edits = False
    months = df_master['_month_group'].unique()
    
    for month in months:
        st.caption(f"**{month}**")
        
        # Filter data for this month
        mask = df_master['_month_group'] == month
        subset = df_master.loc[mask].set_index("Service Date")[display_cols]
        
        # Transpose for the editor (Dates as Columns, Roles as Rows) or Standard?
        # Standard View: Rows=Dates, Cols=Roles is typical for Dataframes.
        # But user requested "Transposed" logic in previous prompts context, 
        # let's stick to standard Table view here as it's easier to edit bulk.
        # Actually, let's use the transposed view to match typical roster grids if preferred,
        # but standard rows=dates is usually more intuitive for editors. 
        # I will stick to Row=Date for the Editor to ensure the "Live Stats" logic works cleanly on column updates.
        
        # We need to Transpose visually if the table is wide? 
        # Let's keep it Rows = Dates for the editor.
        
        # BUT, to make it look like the "View" HTML, let's just make it a standard grid.
        # If you really want Transposed (Cols = Dates), uncomment below:
        # edited_transposed = st.data_editor(subset.T) ...
        
        edited_subset = st.data_editor(
            subset,
            use_container_width=True,
            key=f"edit_{month.replace(' ', '_')}"
        )
        
        # Check against original
        original_subset = df_master.loc[mask].set_index("Service Date")[display_cols]
        
        if not edited_subset.equals(original_subset):
            # Update Master DataFrame in session state
            # 1. Reset index to get Service Date back
            updated_data = edited_subset.reset_index()
            
            # 2. Update the master rows
            for idx, row in updated_data.iterrows():
                # Find matching row in master based on (Month + Date)
                # This depends on Date being unique within month, which it is.
                date_val = row["Service Date"]
                
                master_idx = df_master[
                    (df_master['Service Date'] == date_val) & 
                    (df_master['_month_group'] == month)
                ].index
                
                if not master_idx.empty:
                    df_master.loc[master_idx[0], display_cols] = row[display_cols].values
            
            has_edits = True

    if has_edits:
        state.master_schedule = df_master
        st.rerun() # Rerun to update stats

    # --- 4. COPY VIEW ---
    st.markdown("---")
    st.subheader("📋 View for Copying")
    
    view_cols = ["Service Date"] + display_cols
    for month in months:
        mask = df_master['_month_group'] == month
        HtmlGenerator.render_month_block(
            month, 
            df_master.loc[mask, view_cols]
        )

    # --- 5. FOOTER ACTIONS ---
    st.markdown("---")
    xc1, xc2, xc3, xc4 = st.columns(4)
    
    with xc1:
        if st.button("← Back"):
            state.stage = 3
            st.rerun()
            
    with xc2:
        if st.button("🔄 Regenerate"):
            state.master_schedule = None
            st.rerun()

    with xc3:
        # CSV Download
        csv = df_master.to_csv(index=False).encode('utf-8')
        st.download_button(
            label="💾 Download CSV",
            data=csv,
            file_name=f"roster_export_{datetime.now().strftime('%Y%m%d')}.csv",
            mime="text/csv",
            type="primary"
        )
        
    with xc4:
        if st.button("Start Over"):
            state.reset()
            st.rerun()

# ==========================================
# 6. MAIN APP FLOW
# ==========================================
def main():
    state = SessionState()
    
    if state.stage == 1:
        render_step_1_dates(state)
        
    elif state.stage == 2:
        render_step_2_team(state)
        
    elif state.stage == 3:
        render_step_3_unavailability(state)
        
    elif state.stage == 4:
        engine = RosterEngine(state.selected_techs, state.selected_leads)
        render_step_4_final(state, engine)

if __name__ == "__main__":
    main()
