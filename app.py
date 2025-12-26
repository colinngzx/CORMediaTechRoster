import streamlit as st
import pandas as pd
import random
import calendar
import io
from datetime import datetime, date, timedelta
from typing import List, Dict, Optional, Tuple, NamedTuple
from dataclasses import dataclass

# ==========================================
# 1. CONFIGURATION (Immutable Config)
# ==========================================

@dataclass(frozen=True)
class AppConfig:
    PAGE_TITLE: str = "SWS Roster Wizard"
    # Replace this ID if you change your Google Sheet
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
        return " - ".join(parts)

class DateUtils:
    @staticmethod
    def get_default_window() -> Tuple[int, List[str]]:
        now = datetime.now()
        target_year = now.year + 1 if now.month == 12 else now.year
        suggested_months = []
        for i in range(1, 4):
            idx = (now.month + i - 1) % 12 + 1
            suggested_months.append(calendar.month_name[idx])
        return target_year, suggested_months

    @staticmethod
    def generate_sundays(year: int, month_names: List[str]) -> List[date]:
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
                    # Simple check for year wrap around if dates are in past
                    if curr.year == year and curr.weekday() == 6:  # 6 = Sunday
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
        self.team_names: List[str] = sorted(df['name'].unique().tolist())
        
        # State Tracking
        self.tech_load: Dict[str, int] = {name: 0 for name in self.team_names}
        self.lead_load: Dict[str, int] = {name: 0 for name in self.team_names}
        self.last_worked_idx: Dict[str, int] = {name: -999 for name in self.team_names}
        self.prev_week_crew: List[str] = []

    def _update_stats(self, person: str, role_type: str, week_idx: int):
        if role_type == "tech":
            self.tech_load[person] = self.tech_load.get(person, 0) + 1
        elif role_type == "lead":
            self.lead_load[person] = self.lead_load.get(person, 0) + 1
        self.last_worked_idx[person] = week_idx

    def get_tech_candidate(self, role_key: str, unavailable: List[str], current_crew: List[str], week_idx: int) -> str:
        # 1. Filter by Skill
        mask = (
            self.df['role 1'].str.contains(role_key, case=False, na=False) |
            self.df['role 2'].str.contains(role_key, case=False, na=False) |
            self.df['role 3'].str.contains(role_key, case=False, na=False)
        )
        candidates = self.df[mask]['name'].tolist()

        # 2. Filter by Availability and Rules
        available_pool = [
            p for p in candidates 
            if p not in unavailable 
            and p not in current_crew 
            and p not in self.prev_week_crew # Rule: No back-to-back weeks
        ]

        if not available_pool:
            # Fallback: Allow back-to-back if desperate
            available_pool = [
                p for p in candidates 
                if p not in unavailable 
                and p not in current_crew
            ]

        if not available_pool:
            return "NO FILL"

        # 3. Weighted Sorting
        random.shuffle(available_pool) 
        
        def sort_strategy(name: str):
            # Move deprioritized workers to bottom
            is_deprioritized = 1 if name.lower() == CONFIG.DEPRIORITIZED_WORKER.lower() else 0
            load = self.tech_load.get(name, 0)
            recency = self.last_worked_idx.get(name, -999)
            return (is_deprioritized, load, recency)

        available_pool.sort(key=sort_strategy)
        
        selected = available_pool[0]
        self._update_stats(selected, "tech", week_idx)
        return selected

    def assign_lead(self, current_crew: List[str], unavailable: List[str], week_idx: int) -> str:
        crew_present = [p for p in current_crew if p != "NO FILL"]

        # Tier 1: Primary Leads (Double Hatting)
        primaries = [p for p in crew_present if p.lower() in [x.lower() for x in CONFIG.PRIMARY_LEADS]]
        if primaries:
            primaries.sort(key=lambda x: (self.lead_load.get(x, 0), self.last_worked_idx.get(x, 0)))
            selected = primaries[0]
            self._update_stats(selected, "lead", week_idx)
            return selected

        # Tier 2: Dedicated Lead Availability (Darrell Logic)
        dedicated = CONFIG.DEDICATED_LEAD
        # LOGIC: If 'dedicated' is in 'crew_present', he is already working Tech.
        # The check below (dedicated not in crew_present) prevents him from leading if he is on sound/tech.
        if dedicated not in unavailable and dedicated not in crew_present:
            self._update_stats(dedicated, "lead", week_idx)
            return dedicated

        # Tier 3: General Authorized Leads (Fallback)
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
                data.append({"Name": name, "Tech Shifts": tech_count, "Lead Shifts": lead_count})
        
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
# 5. UI COMPONENTS
# ==========================================

def init_session_state():
    defaults = {
        'stage': 1,
        'roster_dates': [],      
        'event_details': pd.DataFrame(),
        'unavailability': {},    
    }
    for key, val in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = val

# --- STEP 1: DATE SELECTION ---
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
        
        # Initialize the DataFrame with proper columns
        st.session_state.event_details = pd.DataFrame({
            "Date": dates,
            "Holy Communion": [False] * len(dates),
            "Combined": [False] * len(dates),
            "Notes": [""] * len(dates)
        })
        
        st.session_state.stage = 2
        st.rerun()

# --- STEP 2: EVENT DETAILS (LIST VIEW) ---
def render_step_2_details():
    st.subheader("2. Event Details")
    st.write("Customize services (e.g., mark Communion, Combined MSS).")

    # Use a copy to iterate, but update session_state directly
    # We use st.data_editor? No, user prefers list style
    
    df = st.session_state.event_details
    dates_to_drop = []

    # Headers for the List
    h1, h2, h3, h4 = st.columns([2, 1, 1, 3])
    h1.info("Date")
    h2.info("Holy Comm.")
    h3.info("Combined")
    h4.info("Notes")
    st.divider()

    for i, row in df.iterrows():
        d_obj = row['Date'] # Timestamp
        d_str = d_obj.strftime("%d-%b-%Y")
        
        c1, c2, c3, c4 = st.columns([2, 1, 1, 3])
        c1.write(f"**{d_str}**")
        
        # KEY CHANGES: Interactive Widgets updating Session State
        new_hc = c2.checkbox("HC", value=row['Holy Communion'], key=f"hc_{i}", label_visibility="collapsed")
        new_comb = c3.checkbox("Comb", value=row['Combined'], key=f"comb_{i}", label_visibility="collapsed")
        new_note = c4.text_input("Note", value=row['Notes'], key=f"note_{i}", label_visibility="collapsed", placeholder="Optional")
        
        # Update immediately
        st.session_state.event_details.at[i, 'Holy Communion'] = new_hc
        st.session_state.event_details.at[i, 'Combined'] = new_comb
        st.session_state.event_details.at[i, 'Notes'] = new_note
        st.divider()

    # ADD / REMOVE Logic
    st.markdown("#### modify dates")
    xc1, xc2 = st.columns(2)
    
    with xc1:
        # Date Dropdown Removal (Requested Feature)
        date_options = df["Date"].dt.strftime("%d-%b-%Y").tolist()
        dates_to_remove = st.multiselect("Select dates to remove:", options=date_options)
        if st.button("🗑️ Remove Selected"):
            if dates_to_remove:
                mask = ~df["Date"].dt.strftime("%d-%b-%Y").isin(dates_to_remove)
                st.session_state.event_details = df[mask].reset_index(drop=True)
                st.rerun()

    with xc2:
        new_date_input = st.date_input("Add a date", value=None)
        if st.button("➕ Add Date"):
            if new_date_input:
                new_ts = pd.Timestamp(new_date_input)
                if new_ts not in st.session_state.event_details["Date"].values:
                    new_row = pd.DataFrame([{
                        "Date": new_ts, "Holy Communion": False, "Combined": False, "Notes": ""
                    }])
                    st.session_state.event_details = pd.concat([df, new_row], ignore_index=True).sort_values(by="Date").reset_index(drop=True)
                    st.rerun()

    # Navigation
    st.markdown("<br>", unsafe_allow_html=True)
    col_back, col_next = st.columns([1, 5])
    if col_back.button("⬅ Back"):
        st.session_state.stage = 1
        st.rerun()
    if col_next.button("Confirm Settings ➡️", type="primary"):
        st.session_state.roster_dates = st.session_state.event_details['Date'].tolist()
        st.session_state.stage = 3
        st.rerun()

# --- STEP 3: AVAILABILITY ---
def render_step_3_availability(df_team: pd.DataFrame):
    st.subheader("3. Team Availability")
    st.caption("Select dates where team members are **AWAY**.")
    
    date_map = {d: d.strftime("%d-%b") for d in st.session_state.roster_dates}
    formatted_options = list(date_map.values())
    
    temp_unavailability = {}
    team_names = sorted(df_team['name'].unique())
    
    cols = st.columns(3)
    for idx, name in enumerate(team_names):
        with cols[idx % 3]:
            # Simple multiselect for dates away
            sel_display_dates = st.multiselect(name, options=formatted_options, key=f"ua_{name}")
            if sel_display_dates:
                real_dates = [k for k, v in date_map.items() if v in sel_display_dates]
                temp_unavailability[name] = real_dates

    st.markdown("<br>", unsafe_allow_html=True)
    c1, c2 = st.columns([1, 5])
    if c1.button("⬅ Back"):
        st.session_state.stage = 2
        st.rerun()
    if c2.button("✨ Generate Roster ➡️", type="primary"):
        # Convert to dictionary Date -> List[Names]
        final_ua_map = {}
        for name, dates in temp_unavailability.items():
            for d in dates:
                final_ua_map.setdefault(d, []).append(name)
        st.session_state.unavailability = final_ua_map
        st.session_state.stage = 4
        st.rerun()

# --- STEP 4: OUTPUT ---
def render_step_4_output(df_team: pd.DataFrame):
    st.subheader("4. Final Roster")
    
    engine = RosterEngine(df_team)
    schedule_data = []
    events_df = st.session_state.event_details.sort_values("Date")
    
    for week_idx, row in events_df.iterrows():
        d_obj = row['Date']
        ua_list = st.session_state.unavailability.get(d_obj, [])
        todays_crew: List[str] = []
        
        spec = RosterDateSpec(
            date_obj=d_obj,
            is_hc=row.get('Holy Communion', False),
            is_combined=row.get('Combined', False),
            notes=row.get('Notes', "")
        )
        
        row_output = {
            "Month": d_obj.month,
            "Date": d_obj.strftime("%d-%b"),
            "Services": spec.display_details
        }

        # 1. Tech Roles
        for role in CONFIG.ROLES:
            person = engine.get_tech_candidate(role['key'], ua_list, todays_crew, week_idx)
            if person != "NO FILL":
                todays_crew.append(person)
            row_output[role['label']] = person
        
        # 2. Team Lead (Includes logic to skip Darrell if he is already in todays_crew)
        lead = engine.assign_lead(todays_crew, ua_list, week_idx)
        row_output["Team Lead"] = lead
        engine.prev_week_crew = todays_crew 
        
        schedule_data.append(row_output)

    final_df = pd.DataFrame(schedule_data)
    
    # Render Tables
    csv_buff = io.StringIO()
    cols_order = ["Date", "Services", "Team Lead"] + [r['label'] for r in CONFIG.ROLES]
    
    is_first = True
    for mnth_idx, group in final_df.groupby("Month"):
        st.markdown(f"**{calendar.month_name[mnth_idx]}**")
        display_table = group[cols_order].reset_index(drop=True)
        st.dataframe(display_table, use_container_width=True, hide_index=True)
        
        if not is_first: csv_buff.write("\n")
        display_table.to_csv(csv_buff, index=False)
        is_first = False
        
    st.divider()
    
    # Footer
    c1, c2 = st.columns([2, 1])
    with c1:
        # Dropdown Stats ID
        with st.expander("📊 View Workload Statistics"):
            stats = engine.get_statistics_df()
            if not stats.empty:
                st.dataframe(stats, use_container_width=True, hide_index=True)
            else:
                st.info("No stats available.")

    with c2:
        st.download_button(
            "💾 Download CSV",
            data=csv_buff.getvalue(),
            file_name=f"roster_{datetime.now().strftime('%Y%m%d')}.csv",
            mime="text/csv",
            type="primary"
        )
        if st.button("🔄 Start Over"):
            st.session_state.stage = 1
            st.rerun()

# ==========================================
# 6. MAIN
# ==========================================

def main():
    st.set_page_config(page_title=CONFIG.PAGE_TITLE, layout="wide", page_icon="🧙‍♂️")
    init_session_state()
    
    st.title("🧙‍♂️ Roster Wizard")
    
    # Load Data
    with st.spinner("Connecting to Headquarters..."):
        df_team = fetch_roster_data()
    
    if df_team.empty:
        st.error("Could not load team data from Google Sheets.")
        st.stop()
        
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
