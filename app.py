import streamlit as st
import pandas as pd
import random
import calendar
import io
from datetime import datetime, date
from typing import List, Dict, Optional, Tuple, NamedTuple
from dataclasses import dataclass

# ==========================================
# 1. CONFIGURATION ISO (Immutable Config)
# ==========================================

@dataclass(frozen=True)
class AppConfig:
    PAGE_TITLE: str = "SWS Roster Wizard"
    SHEET_ID: str = "1jh6ScfqpHe7rRN1s-9NYPsm7hwqWWLjdLKTYThRRGUo"
    SHEET_NAME: str = "Team"
    
    # Logic Weights
    PRIMARY_LEADS: Tuple[str, ...] = ("gavin", "ben", "mich lo")
    DEDICATED_LEAD: str = "darrell"
    DEPRIORITIZED_WORKER: str = "darrell"
    
    # Roster Roles Mapping
    ROLES: Tuple[Dict[str, str], ...] = (
        {"label": "Sound Crew",      "key": "sound"},
        {"label": "Projectionist",   "key": "projection"},
        {"label": "Stream Director", "key": "stream"},
        {"label": "Cam 1",           "key": "camera"},
    )

CONFIG = AppConfig()

# ==========================================
# 2. DATA MODELS & UTILS
# ==========================================

class RosterDateSpec(NamedTuple):
    """Immutable specification for a single service date."""
    date_obj: date
    is_hc: bool
    is_combined: bool
    notes: str

    @property
    def display_details(self) -> str:
        parts = []
        if self.is_hc: parts.append("HC")
        if self.is_combined: parts.append("Comb")
        if self.notes: parts.append(f"({self.notes})")
        return " ".join(parts)

class DateUtils:
    @staticmethod
    def get_default_window() -> Tuple[int, List[str]]:
        now = datetime.now()
        # Suggest next month context
        target_year = now.year + 1 if now.month == 12 else now.year
        suggested_months = []
        for i in range(1, 4):
            idx = (now.month + i - 1) % 12 + 1
            suggested_months.append(calendar.month_name[idx])
        return target_year, suggested_months

    @staticmethod
    def generate_sundays(year: int, month_names: List[str]) -> List[date]:
        """Generates a list of Sunday dates for given months/year."""
        valid_dates = []
        month_map = {m: i for i, m in enumerate(calendar.month_name) if m}
        today = date.today()

        for m_name in month_names:
            m_idx = month_map.get(m_name)
            if not m_idx: continue
            
            _, days_in_month = calendar.monthrange(year, m_idx)
            for day in range(1, days_in_month + 1):
                try:
                    curr = date(year, m_idx, day)
                    # Handle year wrap-around logic if needed (simple check here)
                    if (today - curr).days > 180: 
                        curr = date(year + 1, m_idx, day)
                    
                    if curr.weekday() == 6:  # 6 = Sunday
                        valid_dates.append(curr)
                except ValueError:
                    continue
        return sorted(valid_dates)

# ==========================================
# 3. LOGIC ENGINE (The Brain)
# ==========================================

class RosterEngine:
    def __init__(self, df: pd.DataFrame):
        self.df = df
        # Normalize names once intended for fast lookup
        self.team_names: List[str] = sorted(df['name'].unique().tolist())
        
        # State Tracking
        self.tech_load: Dict[str, int] = {name: 0 for name in self.team_names}
        self.lead_load: Dict[str, int] = {name: 0 for name in self.team_names}
        self.last_worked_idx: Dict[str, int] = {name: -999 for name in self.team_names}
        
        # Context of the immediate previous week (for strict rules)
        self.prev_week_crew: List[str] = []

    def _update_stats(self, person: str, role_type: str, week_idx: int):
        """Updates internal load balancing counters."""
        if role_type == "tech":
            self.tech_load[person] = self.tech_load.get(person, 0) + 1
        elif role_type == "lead":
            self.lead_load[person] = self.lead_load.get(person, 0) + 1
        
        self.last_worked_idx[person] = week_idx

    def get_tech_candidate(self, role_key: str, unavailable: List[str], current_crew: List[str], week_idx: int) -> str:
        """Finds the best candidate for a specific tech role based on weighted attributes."""
        # 1. Filter by Skill
        mask = (
            self.df['role 1'].str.contains(role_key, case=False, na=False) |
            self.df['role 2'].str.contains(role_key, case=False, na=False) |
            self.df['role 3'].str.contains(role_key, case=False, na=False)
        )
        candidates = self.df[mask]['name'].tolist()

        # 2. Filter by Availability
        available_pool = [
            p for p in candidates 
            if p not in unavailable 
            and p not in current_crew 
            and p not in self.prev_week_crew # Strict no back-to-back
        ]

        if not available_pool:
            # Fallback: Relax back-to-back rule if absolutely necessary
            available_pool = [
                p for p in candidates 
                if p not in unavailable 
                and p not in current_crew
            ]

        if not available_pool:
            return "NO FILL"

        # 3. Weighted Sorting (The "Magic")
        # Sort Criteria:
        # A. Is Deprioritized? (Put at bottom)
        # B. Total Shift Count (Ascending - give to person with least work)
        # C. Recency (Ascending - give to person who worked longest ago (lowest index))
        random.shuffle(available_pool) # Shuffle first to break pure ties
        
        def sort_strategy(name: str):
            is_deprioritized = 1 if name.lower() == CONFIG.DEPRIORITIZED_WORKER.lower() else 0
            load = self.tech_load.get(name, 0)
            recency = self.last_worked_idx.get(name, -999)
            return (is_deprioritized, load, recency)

        available_pool.sort(key=sort_strategy)
        
        selected = available_pool[0]
        self._update_stats(selected, "tech", week_idx)
        return selected

    def assign_lead(self, current_crew: List[str], unavailable: List[str], week_idx: int) -> str:
        """Determines the Team Lead based on hierarchical tiers."""
        crew_present = [p for p in current_crew if p != "NO FILL"]

        # Tier 1: Primary Leads (Double Hatting)
        # We prefer someone already on the team to lead
        primaries = [p for p in crew_present if p.lower() in [x.lower() for x in CONFIG.PRIMARY_LEADS]]
        if primaries:
            # Pick the primary lead who has led the least
            primaries.sort(key=lambda x: (self.lead_load.get(x, 0), self.last_worked_idx.get(x, 0)))
            selected = primaries[0]
            self._update_stats(selected, "lead", week_idx)
            return selected

        # Tier 2: Dedicated Lead Availability
        # If no primary lead is on tech duty, check the dedicated lead (e.g., Darrell)
        dedicated = CONFIG.DEDICATED_LEAD
        if dedicated not in unavailable and dedicated not in crew_present:
            self._update_stats(dedicated, "lead", week_idx)
            return dedicated

        # Tier 3: General Authorized Leads (Fallback)
        # Check if anyone else on the current crew is authorized to lead
        fallbacks = []
        for person in crew_present:
            is_auth = self.df.loc[self.df['name'] == person, 'team lead'].astype(str).str.contains("yes", case=False).any()
            if is_auth:
                fallbacks.append(person)
        
        if fallbacks:
            fallbacks.sort(key=lambda x: self.lead_load.get(x, 0))
            selected = fallbacks[0]
            self._update_stats(selected, "lead", week_idx)
            return selected

        return "⚠️ NO LEAD"

    def get_statistics_df(self) -> pd.DataFrame:
        data = []
        for name in self.team_names:
            tech_count = self.tech_load.get(name, 0)
            lead_count = self.lead_load.get(name, 0)
            if tech_count > 0 or lead_count > 0:
                data.append({"Name": name, "Tech Shifts": tech_count, "Leads": lead_count})
        
        if not data: return pd.DataFrame()
        return pd.DataFrame(data).sort_values("Tech Shifts", ascending=False)

# ==========================================
# 4. DATA ACCESS LAYER
# ==========================================

@st.cache_data(ttl=600)
def fetch_roster_data() -> pd.DataFrame:
    try:
        url = f"https://docs.google.com/spreadsheets/d/{CONFIG.SHEET_ID}/gviz/tq?tqx=out:csv&sheet={CONFIG.SHEET_NAME}"
        df = pd.read_csv(url).fillna("")
        
        # Clean Columns
        df.columns = df.columns.str.strip().str.lower()
        if 'status' in df.columns:
            df = df[(df['status'].str.lower() == 'active') | (df['status'] == '')]
        if 'name' in df.columns: 
            df['name'] = df['name'].str.strip()
            
        return df
    except Exception as e:
        st.error(f"Failed to fetch Google Sheet data. Error: {e}")
        return pd.DataFrame()

# ==========================================
# 5. UI COMPONENTS (Views)
# ==========================================

def init_session_state():
    """Centralized Session State Initialization"""
    defaults = {
        'stage': 1,
        'roster_dates': [],      # List[date]
        'event_details': pd.DataFrame(),
        'unavailability': {},    # Dict[date_str, List[str]]
    }
    for key, val in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = val

def apply_clean_theme():
    # Only minimal CSS for Primary Button visibility, relying on Dark Mode otherwise
    st.markdown("""
        <style>
        div.stButton > button[kind="primary"] { 
            background-color: #007AFF !important; 
            color: white !important;
            border: none;
        }
        </style>
    """, unsafe_allow_html=True)

# --- Stage Renderers ---

def render_step_1_dates():
    st.subheader("1. Select Duration")
    cur_year, cur_months = DateUtils.get_default_window()
    
    col1, col2 = st.columns([1, 2])
    with col1:
        year_sel = st.number_input("Year", 2024, 2030, cur_year)
    with col2:
        month_sel = st.multiselect("Months", calendar.month_name[1:], default=cur_months)

    st.markdown("<br>", unsafe_allow_html=True)
    if st.button("Generate Dates ➡️", type="primary"):
        if not month_sel:
            st.warning("Please select at least one month.")
            return
        
        dates = DateUtils.generate_sundays(year_sel, month_sel)
        st.session_state.roster_dates = dates
        
        # Pre-seed the Event Details DataFrame
        st.session_state.event_details = pd.DataFrame({
            "Date": dates,
            "Holy Communion": [False] * len(dates),
            "Combined": [False] * len(dates),
            "Notes": [""] * len(dates)
        })
        
        st.session_state.stage = 2
        st.rerun()

def render_step_2_details():
    st.subheader("2. Manage Service Dates & Details")
    st.info("You can ADD or DELETE rows below. Mark special services as needed.")
    
    # We use data_editor with num_rows="dynamic" to allow adding/deleting
    edited_df = st.data_editor(
        st.session_state.event_details,
        column_config={
            "Date": st.column_config.DateColumn(
                "Date", 
                format="DD MMM YYYY", 
                required=True,
                help="Double-click to change date"
            ),
            "Holy Communion": st.column_config.CheckboxColumn("Holy Communion", default=False),
            "Combined": st.column_config.CheckboxColumn("Combined Service", default=False),
            "Notes": st.column_config.TextColumn("Notes", default=""),
        },
        hide_index=True,
        use_container_width=True,
        num_rows="dynamic", # <--- THIS ENABLES ADD/REMOVE
        height=400
    )
    
    # Save edits to session state immediately
    st.session_state.event_details = edited_df

    st.markdown("<br>", unsafe_allow_html=True)
    c1, c2 = st.columns([1, 5])
    
    if c1.button("⬅ Back"):
        st.session_state.stage = 1
        st.rerun()
        
    if c2.button("Next: Availability ➡️", type="primary"):
        # VALIDATION: Remove rows where Date might be empty/NaT if user messed up
        clean_df = st.session_state.event_details.dropna(subset=['Date'])
        
        # Ensure booleans are False, not NaN (happens when adding new rows)
        clean_df['Holy Communion'] = clean_df['Holy Communion'].fillna(False)
        clean_df['Combined'] = clean_df['Combined'].fillna(False)
        clean_df['Notes'] = clean_df['Notes'].fillna("")
        
        # Update State and Sync Dates
        st.session_state.event_details = clean_df
        # We must sync the master list of dates for the next step (Availability)
        st.session_state.roster_dates = clean_df['Date'].tolist()
        
        st.session_state.stage = 3
        st.rerun()

def render_step_3_availability(df_team: pd.DataFrame):
    st.subheader("3. Who is Away?")
    st.caption("Select dates where team members are UNAVAILABLE.")
    
    # Create mapping for Date -> Readable String
    date_map = {d: d.strftime("%d-%b") for d in st.session_state.roster_dates}
    formatted_options = list(date_map.values())
    
    temp_unavailability = {}
    team_names = sorted(df_team['name'].unique())
    
    # Grid Layout for names
    cols = st.columns(3)
    for idx, name in enumerate(team_names):
        with cols[idx % 3]:
            sel_display_dates = st.multiselect(
                label=name, 
                options=formatted_options,
                key=f"ua_{name}"
            )
            if sel_display_dates:
                # Convert Display Date back to Real Date Logic
                # (Simple approach: find keys by value)
                real_dates = [k for k, v in date_map.items() if v in sel_display_dates]
                temp_unavailability[name] = real_dates

    st.markdown("<br>", unsafe_allow_html=True)
    c1, c2 = st.columns([1, 5])
    if c1.button("⬅ Back"):
        st.session_state.stage = 2
        st.rerun()
    
    if c2.button("✨ Generate Roster ➡️", type="primary"):
        # Invert Dictionary: stored as Date -> List[Names] for easier lookup in Engine
        final_ua_map = {}
        for name, dates in temp_unavailability.items():
            for d in dates:
                final_ua_map.setdefault(d, []).append(name)
        
        st.session_state.unavailability = final_ua_map
        st.session_state.stage = 4
        st.rerun()

def render_step_4_output(df_team: pd.DataFrame):
    st.subheader("4. Final Roster")
    
    engine = RosterEngine(df_team)
    schedule_data = []
    
    # Process Roster Logic
    # Sort events by date just in case
    events_df = st.session_state.event_details.sort_values("Date")
    
    for week_idx, row in events_df.iterrows():
        d_obj = row['Date'] # This is a python date object
        ua_list = st.session_state.unavailability.get(d_obj, [])
        
        # Logic Loop Variables
        todays_crew: List[str] = []
        
        # Build Spec
        spec = RosterDateSpec(
            date_obj=d_obj,
            is_hc=row.get('Holy Communion', False),
            is_combined=row.get('Combined', False),
            notes=row.get('Notes', "")
        )
        
        row_output = {
            "Month": d_obj.month,
            "Date": d_obj.strftime("%d-%b"),
            "Details": spec.display_details
        }

        # 1. Assign Tech Roles
        for role in CONFIG.ROLES:
            person = engine.get_tech_candidate(role['key'], ua_list, todays_crew, week_idx)
            if person != "NO FILL":
                todays_crew.append(person)
            row_output[role['label']] = person
        
        # 2. Assign Lead
        lead = engine.assign_lead(todays_crew, ua_list, week_idx)
        row_output["Team Lead"] = lead
        
        # 3. Update History for Next Loop
        engine.prev_week_crew = todays_crew # Updates strictly for next iteration
        
        schedule_data.append(row_output)

    # Rendering Results
    final_df = pd.DataFrame(schedule_data)
    
    # CSV Buffer
    csv_buff = io.StringIO()
    
    # Display by Month
    cols_order = ["Date", "Details", "Team Lead"] + [r['label'] for r in CONFIG.ROLES]
    
    is_first_chunk = True
    for mnth_idx, group in final_df.groupby("Month"):
        st.markdown(f"##### {calendar.month_name[mnth_idx]}")
        
        # Pivot for readability (Rows = Roles, Cols = Dates)
        display_table = group[cols_order].set_index("Date").T.reset_index().rename(columns={"index": "Role"})
        st.dataframe(display_table, use_container_width=True, hide_index=True)
        
        # Add to CSV
        if not is_first_chunk: csv_buff.write("\n")
        display_table.to_csv(csv_buff, index=False)
        is_first_chunk = False
        
    st.divider()
    
    # Footer Stats & Actions
    c1, c2 = st.columns([2, 1])
    with c1:
        st.caption("Auto-balancing Logic: Prioritizes those with fewer shifts and handles back-to-back prevention.")
        stats = engine.get_statistics_df()
        if not stats.empty:
            with st.expander("View Shift Statistics"):
                st.dataframe(stats, use_container_width=True, hide_index=True)

    with c2:
        st.download_button(
            label="💾 Download CSV",
            data=csv_buff.getvalue(),
            file_name=f"roster_{datetime.now().strftime('%Y%m%d')}.csv",
            mime="text/csv",
            type="primary"
        )
        if st.button("🔄 Start Over"):
            st.session_state.stage = 1
            st.rerun()

# ==========================================
# 6. APP ENTRY POINT
# ==========================================

def main():
    st.set_page_config(page_title=CONFIG.PAGE_TITLE, layout="wide")
    init_session_state()
    apply_clean_theme()
    
    st.title("🧙‍♂️ Roster Wizard")
    st.markdown("---")

    # Fetch Data
    df_team = fetch_roster_data()
    if df_team.empty:
        st.error("Could not load team data. Checks logs.")
        st.stop()
        
    # Routing
    if st.session_state.stage == 1:
        render_step_1_dates()
    elif st.session_state.stage == 2:
        render_step_2_details()
    elif st.session_state.stage == 3:
        render_step_3_availability(df_team)
    elif st.session_state.stage == 4:
        render_step_4_output(df_team)

if __name__ == "__main__":
    main()
