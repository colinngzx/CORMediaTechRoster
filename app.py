import streamlit as st
import pandas as pd
import random
import calendar
import io
from datetime import datetime, date
from collections import defaultdict
from typing import List, Dict, Tuple, NamedTuple
from dataclasses import dataclass

# ==========================================
# 1. CONFIGURATION
# ==========================================

@dataclass(frozen=True)
class AppConfig:
    PAGE_TITLE: str = "SWS Roster Wizard"
    SHEET_ID: str = "1jh6ScfqpHe7rRN1s-9NYPsm7hwqWWLjdLKTYThRRGUo"
    SHEET_NAME: str = "Team"
    
    # Priority for Team Lead specifically
    PRIMARY_LEADS: Tuple[str, ...] = ("gavin", "ben", "mich lo")
    
    # Roster Roles
    ROLES: Tuple[Dict[str, str], ...] = (
        {"label": "Sound Crew",      "key": "sound"},
        {"label": "Projectionist",   "key": "projection"},
        {"label": "Stream Director", "key": "stream"},
        {"label": "Cam 1",           "key": "camera"},
    )

CONFIG = AppConfig()

st.set_page_config(page_title=CONFIG.PAGE_TITLE, layout="wide")

# ==========================================
# 2. HELPER CLASSES & FUNCTIONS
# ==========================================

class RosterDateSpec(NamedTuple):
    date_obj: date
    is_hc: bool
    is_combined: bool
    notes: str

    @property
    def display_details(self) -> str:
        parts = []
        if self.is_combined: parts.append("MSS Combined")
        if self.is_hc: parts.append("HC")
        if self.notes: parts.append(self.notes)
        return " / ".join(parts) if parts else ""

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
        
        for m_name in month_names:
            m_idx = month_map.get(m_name)
            if not m_idx: continue
            
            _, days_in_month = calendar.monthrange(year, m_idx)
            for day in range(1, days_in_month + 1):
                try:
                    curr = date(year, m_idx, day)
                    if curr.year == year and curr.weekday() == 6:  # Sunday
                        valid_dates.append(curr)
                except ValueError:
                    continue
        return sorted(valid_dates)

# ==========================================
# 3. ROSTER LOGIC ENGINE
# ==========================================

class RosterEngine:
    def __init__(self, df: pd.DataFrame):
        self.df = df
        self.team_names: List[str] = sorted(df['name'].unique().tolist())
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
        mask = (
            self.df['role 1'].str.contains(role_key, case=False, na=False) |
            self.df['role 2'].str.contains(role_key, case=False, na=False) |
            self.df['role 3'].str.contains(role_key, case=False, na=False)
        )
        candidates = self.df[mask]['name'].tolist()

        available_pool = [
            p for p in candidates 
            if p not in unavailable 
            and p not in current_crew 
            and p not in self.prev_week_crew
        ]

        # Soft constraint: allow working subsequent weeks if necessary
        if not available_pool:
            available_pool = [
                p for p in candidates 
                if p not in unavailable 
                and p not in current_crew
            ]

        if not available_pool:
            return ""

        random.shuffle(available_pool) 
        # Sort by Load ASC, then Recency
        available_pool.sort(key=lambda x: (self.tech_load.get(x, 0), self.last_worked_idx.get(x, -999)))
        
        selected = available_pool[0]
        self._update_stats(selected, "tech", week_idx)
        return selected

    def assign_lead(self, current_crew: List[str], unavailable: List[str], week_idx: int) -> str:
        crew_present = [p for p in current_crew if p]
        
        # 1. Primary Leads preference
        primaries = [p for p in crew_present if any(lead.lower() in p.lower() for lead in CONFIG.PRIMARY_LEADS)]
        
        if primaries:
            primaries.sort(key=lambda x: (self.lead_load.get(x, 0), self.last_worked_idx.get(x, -999)))
            selected = primaries[0]
            self._update_stats(selected, "lead", week_idx)
            return selected

        # 2. General Fallback
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

        return ""

    def get_stats(self) -> pd.DataFrame:
        data = []
        for name in self.team_names:
            tech = self.tech_load.get(name, 0)
            lead = self.lead_load.get(name, 0)
            # LOGIC CHANGE: Total includes only Tech, Lead is separate
            if tech + lead > 0:
                data.append({
                    "Name": name, 
                    "Tech Shifts": tech, 
                    "Lead Shifts": lead, 
                    "Total (Tech Only)": tech 
                })
        return pd.DataFrame(data).sort_values("Total (Tech Only)", ascending=False)

# ==========================================
# 4. DATA FETCHING
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
        st.error(f"Error reading Google Sheet: {e}")
        return pd.DataFrame()

# ==========================================
# 5. UI & APP FLOW
# ==========================================

def main():
    st.title("🎛️ SWS Media Roster Generator")
    
    if 'stage' not in st.session_state: st.session_state.stage = 1
    if 'roster_dates' not in st.session_state: st.session_state.roster_dates = []
    # Store unavailable dates per person: { "Name": ["2025-01-05", "2025-01-12"] }
    if 'unavailability_by_person' not in st.session_state: st.session_state.unavailability_by_person = {}
    
    df_team = fetch_roster_data()
    if df_team.empty:
        st.stop()
    
    all_names = sorted(df_team['name'].unique().tolist())

    # --- STEP 1: SELECT DATES ---
    if st.session_state.stage == 1:
        st.header("Step 1: Select Service Dates")
        col1, col2 = st.columns(2)
        with col1:
            def_year, def_months = DateUtils.get_default_window()
            year = st.number_input("Year", value=def_year, min_value=2024, max_value=2030)
        with col2:
            months = st.multiselect("Months", list(calendar.month_name)[1:], default=def_months)

        if st.button("Generate Date List"):
            dates = DateUtils.generate_sundays(year, months)
            st.session_state.roster_dates = [
                {"Date": d, "Combined": False, "HC": False, "Notes": ""} for d in dates
            ]
            st.session_state.stage = 2
            st.rerun()

    # --- STEP 2: CONFIGURE SERVICES ---
    elif st.session_state.stage == 2:
        st.header("Step 2: Service Details")
        st.info("Mark details. Use the '+' button at the bottom (or right click) to add extra dates manually.")
        
        df_dates = pd.DataFrame(st.session_state.roster_dates)
        
        # Enable dynamic rows
        edited_df = st.data_editor(
            df_dates,
            column_config={
                "Date": st.column_config.DateColumn("Service Date", format="DD-MMM", required=True),
                "Combined": st.column_config.CheckboxColumn("MSS Combined?", default=False),
                "HC": st.column_config.CheckboxColumn("Holy Communion?", default=False),
                "Notes": st.column_config.TextColumn("Notes (Optional)"),
            },
            num_rows="dynamic",
            use_container_width=True,
            hide_index=True
        )

        col_l, col_r = st.columns([1, 5])
        if col_l.button("← Back"):
            st.session_state.stage = 1
            st.rerun()
        if col_r.button("Next: Availability →"):
            valid_rows = []
            for r in edited_df.to_dict('records'):
                if pd.notnull(r['Date']): # ensure date exists
                    # Convert pandas timestamp to python date if necessary
                    if isinstance(r['Date'], pd.Timestamp):
                         r['Date'] = r['Date'].date()
                    valid_rows.append(r)
            
            st.session_state.roster_dates = valid_rows
            st.session_state.stage = 3
            st.rerun()

    # --- STEP 3: UNAVAILABILITY (BY NAME) ---
    elif st.session_state.stage == 3:
        st.header("Step 3: Unavailability")
        st.info("Select a person, then select the dates they are NOT available.")

        # Setup date options formatted nicely
        date_options = [r['Date'] for r in st.session_state.roster_dates]
        
        # We need a string label map for the multiselect
        # Map "YYYY-MM-DD" -> date_obj
        date_map = {str(d): d for d in date_options}
        date_labels = sorted(list(date_map.keys()))

        with st.form("avail_form_names"):
            # Initialize selections if not present
            if not st.session_state.unavailability_by_person:
                 st.session_state.unavailability_by_person = {name: [] for name in all_names}
            
            # Simple Expanders for grouping could be nice, but list is fine
            st.write("### Team Members")
            
            # Display dict to store user input temporarily
            user_selections = {}
            
            # Grid layout for names to save space
            cols = st.columns(3)
            for i, name in enumerate(all_names):
                with cols[i % 3]:
                    current_sel = st.session_state.unavailability_by_person.get(name, [])
                    # Convert current selection dates to strings for multiselect
                    default_vals = [str(d) for d in current_sel if str(d) in date_labels]

                    selected_strs = st.multiselect(
                        f"{name}",
                        options=date_labels,
                        default=default_vals,
                        format_func=lambda x: date_map[x].strftime("%d-%b"),
                        key=f"una_{i}"
                    )
                    user_selections[name] = selected_strs
            
            submitted = st.form_submit_button("Generate Roster")
            if submitted:
                # Save as lists of date strings
                st.session_state.unavailability_by_person = user_selections
                st.session_state.stage = 4
                st.rerun()
        
        if st.button("← Back"):
            st.session_state.stage = 2
            st.rerun()

    # --- STEP 4: FINAL DISPLAY & DOWNLOAD ---
    elif st.session_state.stage == 4:
        st.header("Step 4: Final Roster")
        
        # 0. TRANSFORMATION: Name->Dates  TO  Date->Names for the Engine
        unavailable_by_date_str = defaultdict(list)
        for name, unavailable_dates in st.session_state.unavailability_by_person.items():
            for d_str in unavailable_dates:
                unavailable_by_date_str[d_str].append(name)
        
        engine = RosterEngine(df_team)
        raw_schedule = []

        # 1. GENERATE
        for idx, r_data in enumerate(st.session_state.roster_dates):
            d_obj = r_data['Date']
            spec = RosterDateSpec(d_obj, r_data['HC'], r_data['Combined'], r_data['Notes'])
            
            # Look up who is unavailable for THIS specific date
            d_str_key = str(d_obj)
            unavailable_today = unavailable_by_date_str.get(d_str_key, [])
            
            current_crew = []
            
            date_entry = {
                "Service Dates": d_obj.strftime("%d-%b"),
                "_full_date": d_obj, # Hidden helper for sorting/grouping
                "Additional Details": spec.display_details
            }
            
            for role_conf in CONFIG.ROLES:
                person = engine.get_tech_candidate(role_conf['key'], unavailable_today, current_crew, idx)
                date_entry[role_conf['label']] = person
                if person: current_crew.append(person)
            
            # Hardcoded Cam 2
            date_entry["Cam 2"] = "" 

            t_lead = engine.assign_lead(current_crew, unavailable_today, idx)
            date_entry["Team Lead"] = t_lead
            
            raw_schedule.append(date_entry)
            engine.prev_week_crew = current_crew

        # 2. CREATE MASTER DATAFRAME (Transposed)
        df_schedule = pd.DataFrame(raw_schedule)
        
        # Extract headers and data
        col_headers = df_schedule['Service Dates'].tolist()
        
        # Drop helpers before transposing
        df_for_t = df_schedule.drop(columns=['Service Dates', '_full_date'])
        df_transposed = df_for_t.T
        df_transposed.columns = col_headers
        
        # Reorder rows
        desired_order = ["Additional Details", "Sound Crew", "Projectionist", "Stream Director", "Cam 1", "Cam 2", "Team Lead"]
        df_final_master = df_transposed.reindex(desired_order).fillna("")

        # 3. VISUAL DISPLAY - GROUPED BY MONTH
        # Helper to group the original dates
        dates_by_month = defaultdict(list)
        for entry in raw_schedule:
            d_obj = entry['_full_date']
            month_key = d_obj.strftime("%B %Y") # e.g. January 2025
            col_name = entry['Service Dates']
            dates_by_month[month_key].append(col_name)

        # Loop through months and display sliced dataframes
        for month_name, col_names in dates_by_month.items():
            st.subheader(month_name)
            # Slice the master dataframe to only current month's columns
            # Check overlap to be safe
            valid_cols = [c for c in col_names if c in df_final_master.columns]
            if valid_cols:
                st.dataframe(df_final_master[valid_cols], use_container_width=True)
            st.markdown("---")

        # 4. STATS
        with st.expander("Show Load Statistics", expanded=True):
            st.dataframe(engine.get_stats(), use_container_width=True)

        # 5. BUTTONS
        csv = df_final_master.to_csv().encode('utf-8')
        col1, col2 = st.columns(2)
        with col1:
             st.download_button("📥 Download Master CSV", csv, "sws_roster_master.csv", "text/csv")
        with col2:
            if st.button("Start Over"):
                st.session_state.stage = 1
                st.session_state.roster_dates = []
                st.session_state.unavailability_by_person = {}
                st.rerun()

if __name__ == "__main__":
    main()
