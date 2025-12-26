import streamlit as st
import pandas as pd
import random
import calendar
from datetime import datetime, date
from typing import List, Dict, Optional, Any
from dataclasses import dataclass, field
from enum import Enum

# ==========================================
# 1. CONSTANTS & CONFIGURATION
# ==========================================

class AppConfig:
    PAGE_TITLE = "SWS Roster Wizard"
    SHEET_ID = "1jh6ScfqpHe7rRN1s-9NYPsm7hwqWWLjdLKTYThRRGUo"
    SHEET_URL = f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/export?format=csv&gid=0"
    
    # Priority for Team Lead assignments (lowercased)
    PRIMARY_LEADS = {"gavin", "ben", "mich lo"}
    
    # Date formatting
    DATE_FMT_DISPLAY = "%d-%b"
    DATE_FMT_MONTH = "%B %Y"

@dataclass(frozen=True)
class RoleDefinition:
    label: str
    key: str     # Internal key for dataframes
    sheet_col: str

class Roles:
    """Centralized definition of all roles to prevent string typos."""
    DETAILS = "Details"
    SOUND = RoleDefinition("Sound Crew", "Sound Crew", "sound")
    PROJ = RoleDefinition("Projectionist", "Projectionist", "projection")
    STREAM = RoleDefinition("Stream Director", "Stream Director", "stream director")
    CAM1 = RoleDefinition("Cam 1", "Cam 1", "camera")
    CAM2 = RoleDefinition("Cam 2", "Cam 2", "cam2") # Placeholder
    LEAD = RoleDefinition("Team Lead", "Team Lead", "team lead")
    
    @classmethod
    def get_tech_roles(cls) -> List[RoleDefinition]:
        return [cls.SOUND, cls.PROJ, cls.STREAM, cls.CAM1]

# ==========================================
# 2. STATE MANAGEMENT (Facade Pattern)
# ==========================================

class SessionState:
    """
    A strong-typed interface for Streamlit's session state.
    Eliminates 'magic strings' and ensures default values.
    """
    @property
    def stage(self) -> int:
        return st.session_state.get('stage', 1)

    @stage.setter
    def stage(self, value: int):
        st.session_state.stage = value

    @property
    def roster_dates(self) -> List[Dict]:
        return st.session_state.get('roster_dates', [])

    @roster_dates.setter
    def roster_dates(self, value: List[Dict]):
        st.session_state.roster_dates = value

    @property
    def unavailability(self) -> Dict[str, List[str]]:
        return st.session_state.get('unavailability', {})

    @unavailability.setter
    def unavailability(self, value: Dict[str, List[str]]):
        st.session_state.unavailability = value

    @property
    def master_schedule(self) -> Optional[pd.DataFrame]:
        return st.session_state.get('master_schedule', None)

    @master_schedule.setter
    def master_schedule(self, df: Optional[pd.DataFrame]):
        st.session_state.master_schedule = df

    def reset(self):
        """Clean slate reset."""
        keys = ['stage', 'roster_dates', 'unavailability', 'master_schedule']
        for k in keys:
            if k in st.session_state:
                del st.session_state[k]

# ==========================================
# 3. DOMAIN LOGIC & SERVICES
# ==========================================

class DataService:
    """Handles all interaction with external data sources."""
    
    @staticmethod
    @st.cache_data(ttl=600)
    def fetch_team_data() -> pd.DataFrame:
        try:
            df = pd.read_csv(AppConfig.SHEET_URL).fillna("")
            # Normalize Headers
            df.columns = df.columns.str.strip().str.lower()
            
            # Correction mapping for messy sheet headers
            renames = {
                'stream dire': Roles.STREAM.sheet_col,
                'team lead': 'team lead'
            }
            df = df.rename(columns=renames)
            
            if 'name' not in df.columns:
                raise ValueError("Column 'Name' missing in Google Sheet.")
                
            return df
        except Exception as e:
            st.error(f"Data Fetch Error: {str(e)}")
            return pd.DataFrame()

class RosterEngine:
    """pure logic class for assigning people."""
    
    def __init__(self, df: pd.DataFrame):
        self.df = df
        self.names = sorted(df['name'].unique().tolist(), key=lambda x: str(x).lower())
        # Tracking loads to balance roster
        self.stats = {
            "tech_count": {n: 0 for n in self.names},
            "lead_count": {n: 0 for n in self.names},
            "last_idx": {n: -999 for n in self.names}
        }
        self.prev_crew = []

    def get_candidate(self, role: RoleDefinition, unavailable: List[str], current_crew: List[str], week_idx: int) -> str:
        if role.sheet_col not in self.df.columns:
            return ""

        # Filter: Who can do the job?
        capable_mask = self.df[role.sheet_col].astype(str).str.strip() != ""
        candidates = self.df[capable_mask]['name'].tolist()

        # Filter: Who is available and not already working today?
        exclusions = set(unavailable) | set(current_crew)
        
        # Prefer people who didn't work last week
        pool_primary = [p for p in candidates if p not in exclusions and p not in self.prev_crew]
        pool_secondary = [p for p in candidates if p not in exclusions]

        final_pool = pool_primary if pool_primary else pool_secondary
        
        if not final_pool:
            return ""

        # Strategy: Least loaded, then Random
        random.shuffle(final_pool) # Add randomness for tie-breaking
        final_pool.sort(key=lambda x: (self.stats["tech_count"][x], self.stats["last_idx"][x]))
        
        selected = final_pool[0]
        self.stats["tech_count"][selected] += 1
        self.stats["last_idx"][selected] = week_idx
        return selected

    def assign_lead(self, current_crew: List[str], week_idx: int) -> str:
        """Pick a lead from the already assigned crew."""
        present_crew = [p for p in current_crew if p]
        
        # 1. Look for Primary Leads (configured constants)
        # Using string matching (e.g., "Ben" matches "Ben", or "Ben S")
        primaries = [p for p in present_crew if any(pl in p.lower() for pl in AppConfig.PRIMARY_LEADS)]
        
        candidates = primaries if primaries else present_crew
        if not candidates: 
            return ""

        # Sort by lead load to balance load
        candidates.sort(key=lambda x: self.stats["lead_count"][x])
        selected = candidates[0]
        
        self.stats["lead_count"][selected] += 1
        return selected

class HtmlGenerator:
    """Safe HTML generation for the copy block."""
    
    @staticmethod
    def render_month_block(month_name: str, df: pd.DataFrame) -> None:
        """Renders specific HTML structure for copying."""
        # Clean dataframe for view
        if "Service Date" in df.columns:
            df = df.set_index("Service Date")
        
        # Transpose so Dates are headers
        df_t = df.T
        df_t.reset_index(inplace=True)
        
        # Add a manual header row so the copy operation includes column names naturally
        header_row = pd.DataFrame([df_t.columns.values], columns=df_t.columns)
        final_df = pd.concat([header_row, df_t], ignore_index=True)

        # Convert to HTML
        html_table = final_df.to_html(header=False, index=False, border=1, classes="roster-table")
        
        # Render
        st.markdown(
            f"""
            <div style="margin-bottom: 30px; font-family: sans-serif;">
                <h4 style="margin-bottom: 5px;">{month_name}</h4>
                {html_table}
            </div>
            """, 
            unsafe_allow_html=True
        )

# ==========================================
# 4. VIEW RENDERERS (UI Components)
# ==========================================

def render_step_1_date_selection(state: SessionState):
    st.header("Step 1: Select Service Dates")
    c1, c2 = st.columns(2)
    
    now = datetime.now()
    default_year = now.year + 1 if now.month == 12 else now.year
    default_months = []
    
    # Suggest next 3 months
    for i in range(1, 4):
        idx = (now.month + i - 1) % 12 + 1
        default_months.append(calendar.month_name[idx])

    with c1:
        year = st.number_input("Year", value=default_year, min_value=2024, max_value=2030)
    with c2:
        months = st.multiselect("Months", list(calendar.month_name)[1:], default=default_months)

    if st.button("Generate Date List", type="primary"):
        # Logic to find Sundays
        dates = []
        month_map = {m: i for i, m in enumerate(calendar.month_name) if m}
        
        for m_name in months:
            m_idx = month_map.get(m_name)
            if not m_idx: continue
            _, days = calendar.monthrange(year, m_idx)
            for d in range(1, days + 1):
                dt = date(year, m_idx, d)
                if dt.weekday() == 6: # Sunday
                    dates.append(dt)
        
        state.roster_dates = [
            {"Date": d, "Combined": False, "HC": False, "Notes": ""} 
            for d in sorted(dates)
        ]
        state.stage = 2
        st.rerun()

def render_step_2_details(state: SessionState):
    st.header("Step 2: Service Details & Customization")
    
    df = pd.DataFrame(state.roster_dates)
    if not df.empty:
        df['Date'] = pd.to_datetime(df['Date']).dt.date

    # Main Editor
    edited_df = st.data_editor(
        df,
        column_config={
            "Date": st.column_config.DateColumn("Service Date", format="DD-MMM", required=True),
            "Combined": st.column_config.CheckboxColumn("Combined Svc?", default=False),
            "HC": st.column_config.CheckboxColumn("Holy Comm?", default=False),
        },
        num_rows="dynamic",
        use_container_width=True,
        key="details_editor",
        hide_index=True
    )

    col_nav_1, col_nav_2 = st.columns([1, 4])
    if col_nav_1.button("← Back"):
        state.stage = 1
        st.rerun()
        
    if col_nav_2.button("Next: Availability →", type="primary"):
        # Save state cleanly
        state.roster_dates = edited_df.to_dict('records')
        state.stage = 3
        st.rerun()

def render_step_3_unavailability(state: SessionState, all_names: List[str]):
    st.header("Step 3: Track Unavailability")
    st.info("Mark dates where team members are **NOT** available.")

    # Prepare safe date strings for the multiselect
    raw_dates = [d['Date'] for d in state.roster_dates if isinstance(d.get('Date'), (date, datetime))]
    date_options = sorted(raw_dates)
    date_map = {str(d): d for d in date_options}
    sorted_str_keys = sorted(date_map.keys())

    # Initialize container if empty
    current_avail = state.unavailability
    if not current_avail:
        current_avail = {name: [] for name in all_names}

    with st.form("availability_form"):
        cols = st.columns(3)
        updated_avail = {}
        
        for i, name in enumerate(all_names):
            with cols[i % 3]:
                defaults = [x for x in current_avail.get(name, []) if x in sorted_str_keys]
                selected = st.multiselect(
                    label=f"🚫 {name}",
                    options=sorted_str_keys,
                    default=defaults,
                    format_func=lambda x: date_map[x].strftime(AppConfig.DATE_FMT_DISPLAY),
                    key=f"una_{name}"
                )
                updated_avail[name] = selected
        
        st.markdown("---")
        if st.form_submit_button("Generate Roster", type="primary"):
            state.unavailability = updated_avail
            state.master_schedule = None # Force regeneration
            state.stage = 4
            st.rerun()

    if st.button("← Back"):
        state.stage = 2
        st.rerun()

def render_step_4_final(state: SessionState, engine: RosterEngine):
    st.header("Step 4: Roster Dashboard")

    # --- 1. GENERATION LOGIC (Triggered only if schedule is None) ---
    if state.master_schedule is None:
        raw_rows = []
        unavailable_map = defaultdict(list)
        
        # Invert the availability map for O(1) lookups by date
        for name, dates in state.unavailability.items():
            for d in dates:
                unavailable_map[str(d)].append(name)

        for idx, entry in enumerate(state.roster_dates):
            d_obj = entry['Date']
            if pd.isna(d_obj): continue
            
            # Create Description
            notes = [entry.get('Notes', '')]
            if entry.get('Combined'): notes.insert(0, "MSS Combined")
            if entry.get('HC'): notes.insert(0, "HC")
            desc = " / ".join([n for n in notes if n])
            
            row = {
                "Service Date": d_obj.strftime(AppConfig.DATE_FMT_DISPLAY),
                "_month_group": d_obj.strftime(AppConfig.DATE_FMT_MONTH),
                Roles.DETAILS: desc
            }
            
            # Assign Techs
            curr_crew = []
            unavailable_today = unavailable_map.get(str(d_obj), [])
            
            for role in Roles.get_tech_roles():
                person = engine.get_candidate(role, unavailable_today, curr_crew, idx)
                row[role.label] = person
                if person: curr_crew.append(person)
            
            row[Roles.CAM2.label] = "" # Manual fill usually
            
            # Assign Lead
            lead = engine.assign_lead(curr_crew, idx)
            row[Roles.LEAD.label] = lead
            
            raw_rows.append(row)
            engine.prev_crew = curr_crew # Update history for next iteration
        
        state.master_schedule = pd.DataFrame(raw_rows)

    # --- 2. EDITOR INTERFACE ---
    df_master = state.master_schedule
    
    # Define Layout columns
    display_cols = [Roles.DETAILS] + [r.label for r in Roles.get_tech_roles()] + [Roles.CAM2.label, Roles.LEAD.label]
    
    st.subheader("✏️ Roster Editor")
    st.caption("Edits made here update the 'Copy List' automatically.")

    has_edits = False
    
    # Group by Month for cleaner UI
    months = df_master['_month_group'].unique()
    
    for month in months:
        st.markdown(f"**{month}**")
        
        # Filter Logic
        mask = df_master['_month_group'] == month
        subset = df_master.loc[mask].set_index("Service Date")[display_cols]
        
        # Transposed Editor (Dates as columns)
        edited_transposed = st.data_editor(
            subset.T,
            use_container_width=True,
            key=f"edit_{month.replace(' ', '_')}"
        )
        
        # Reconstruction Logic (if changed)
        if not edited_transposed.equals(subset.T):
            reverted = edited_transposed.T.reset_index()
            # Update master dataframe
            for _, row in reverted.iterrows():
                # Find matching row index in master using Service Date & Month
                idx_master = df_master[
                    (df_master['Service Date'] == row['Service Date']) & 
                    (df_master['_month_group'] == month)
                ].index
                
                if not idx_master.empty:
                    df_master.loc[idx_master[0], display_cols] = row[display_cols].values
            has_edits = True

    if has_edits:
        state.master_schedule = df_master
        st.rerun()

    # --- 3. COPY VIEW ---
    st.markdown("---")
    st.subheader("📋 View for Copying (Select All)")
    st.info("Click inside a table, `Ctrl+A` (Select All), `Ctrl+C` (Copy), paste into Excel.")
    
    for month in months:
        mask = df_master['_month_group'] == month
        # Pass only the display columns to the renderer
        HtmlGenerator.render_month_block(
            month, 
            df_master.loc[mask, ["Service Date"] + display_cols]
        )

    # --- 4. EXPORT ACTIONS ---
    st.markdown("---")
    xc1, xc2, xc3 = st.columns([1, 2, 1])
    
    with xc1:
        if st.button("← Back to Availability"):
            state.stage = 3
            st.rerun()
            
    with xc2:
        if st.button("🔄 Regenerate Assignments", type="secondary"):
            state.master_schedule = None
            st.rerun()

    with xc3:
        if st.button("Start Over", type="primary"):
            state.reset()
            st.rerun()

# ==========================================
# 5. MAIN CONTROLLER
# ==========================================

def main():
    st.set_page_config(page_title=AppConfig.PAGE_TITLE, layout="wide")
    state = SessionState()
    
    # Load Data
    df_team = DataService.fetch_team_data()
    if df_team.empty:
        st.warning("No data found. Please check Google Sheet permissions.")
        return

    # Initialize Engine (Logic)
    all_names = sorted(df_team['name'].unique().tolist(), key=lambda x: str(x).lower())
    engine = RosterEngine(df_team)

    # Router
    if state.stage == 1:
        render_step_1_date_selection(state)
    elif state.stage == 2:
        render_step_2_details(state)
    elif state.stage == 3:
        render_step_3_unavailability(state, all_names)
    elif state.stage == 4:
        render_step_4_final(state, engine)

if __name__ == "__main__":
    main()
