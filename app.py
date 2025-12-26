import streamlit as st
import pandas as pd
import random
import calendar
import io
from datetime import datetime, date
from typing import List, Dict, Tuple, NamedTuple
from dataclasses import dataclass

# ==========================================
# 1. CONFIGURATION
# ==========================================

@dataclass(frozen=True)
class AppConfig:
    PAGE_TITLE: str = "SWS Roster Wizard"
    # Google Sheet ID provided in previous instructions
    SHEET_ID: str = "1jh6ScfqpHe7rRN1s-9NYPsm7hwqWWLjdLKTYThRRGUo"
    SHEET_NAME: str = "Team"
    
    # Priority for Team Lead specifically
    PRIMARY_LEADS: Tuple[str, ...] = ("gavin", "ben", "mich lo")
    
    # Ordered list of roles to generate. 
    # Label is how it looks in the final table. Key is how we find it in the Google Sheet.
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
        """Formats the 'Additional Details' row string"""
        parts = []
        if self.is_combined: parts.append("MSS Combined")
        if self.is_hc: parts.append("HC") # "HC" or "Holy Communion"
        if self.notes: parts.append(self.notes)
        return " / ".join(parts) if parts else ""

class DateUtils:
    @staticmethod
    def get_default_window() -> Tuple[int, List[str]]:
        now = datetime.now()
        target_year = now.year + 1 if now.month == 12 else now.year
        suggested_months = []
        # Suggest next 3 months
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
                    if curr.year == year and curr.weekday() == 6:  # 6 = Sunday
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
        # Normalize names to avoid case issues
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
        # 1. Filter people who have this skill
        mask = (
            self.df['role 1'].str.contains(role_key, case=False, na=False) |
            self.df['role 2'].str.contains(role_key, case=False, na=False) |
            self.df['role 3'].str.contains(role_key, case=False, na=False)
        )
        candidates = self.df[mask]['name'].tolist()

        # 2. Exclude unavailable, already scheduling this week, or worked last week
        available_pool = [
            p for p in candidates 
            if p not in unavailable 
            and p not in current_crew 
            and p not in self.prev_week_crew
        ]

        # 3. Soft constraint: If pool is empty, allow people who worked last week
        if not available_pool:
            available_pool = [
                p for p in candidates 
                if p not in unavailable 
                and p not in current_crew
            ]

        if not available_pool:
            return "" # No one available

        # 4. Selection Logic: Minimize Load, then Minimize Recency. Shuffle for tie-breaking.
        random.shuffle(available_pool) 
        available_pool.sort(key=lambda x: (self.tech_load.get(x, 0), self.last_worked_idx.get(x, -999)))
        
        selected = available_pool[0]
        self._update_stats(selected, "tech", week_idx)
        return selected

    def assign_lead(self, current_crew: List[str], unavailable: List[str], week_idx: int) -> str:
        crew_present = [p for p in current_crew if p] # Filter out empty strings
        
        # 1. Check if a "Primary Lead" is already in the crew (preferred)
        primaries = [p for p in crew_present if any(lead.lower() in p.lower() for lead in CONFIG.PRIMARY_LEADS)]
        
        if primaries:
            # Pick primary with lowest lead load
            primaries.sort(key=lambda x: (self.lead_load.get(x, 0), self.last_worked_idx.get(x, -999)))
            selected = primaries[0]
            self._update_stats(selected, "lead", week_idx)
            return selected

        # 2. Fallback: Anyone in the crew marked as "Yes" for Team Lead in Sheet
        fallbacks = []
        for person in crew_present:
            # Check sheet for 'team lead' == 'yes'
            is_auth = self.df.loc[self.df['name'] == person, 'team lead'].astype(str).str.contains("yes", case=False).any()
            if is_auth:
                fallbacks.append(person)
        
        if fallbacks:
            fallbacks.sort(key=lambda x: self.lead_load.get(x, 0))
            selected = fallbacks[0]
            self._update_stats(selected, "lead", week_idx)
            return selected

        return "" # No lead found

    def get_stats(self) -> pd.DataFrame:
        data = []
        for name in self.team_names:
            tech = self.tech_load.get(name, 0)
            lead = self.lead_load.get(name, 0)
            if tech + lead > 0:
                data.append({"Name": name, "Tech": tech, "Lead": lead, "Total": tech+lead})
        return pd.DataFrame(data).sort_values("Total", ascending=False)

# ==========================================
# 4. DATA FETCHING
# ==========================================

@st.cache_data(ttl=600)
def fetch_roster_data() -> pd.DataFrame:
    try:
        url = f"https://docs.google.com/spreadsheets/d/{CONFIG.SHEET_ID}/gviz/tq?tqx=out:csv&sheet={CONFIG.SHEET_NAME}"
        df = pd.read_csv(url).fillna("")
        df.columns = df.columns.str.strip().str.lower() # Normalize cols
        
        # Filter for active members
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
    
    # Init Session State
    if 'stage' not in st.session_state: st.session_state.stage = 1
    if 'roster_dates' not in st.session_state: st.session_state.roster_dates = []
    if 'unavailability' not in st.session_state: st.session_state.unavailability = {}
    
    # Load Data
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
            # Pre-fill structure for step 2
            st.session_state.roster_dates = [
                {"Date": d, "Combined": False, "HC": False, "Notes": ""} for d in dates
            ]
            st.session_state.stage = 2
            st.rerun()

    # --- STEP 2: CONFIGURE SERVICES ---
    elif st.session_state.stage == 2:
        st.header("Step 2: Service Details")
        st.info("Mark combined services, Holy Communion, or add special notes (e.g., 'Ablaze').")
        
        # We use data_editor to allow quick inline editing
        df_dates = pd.DataFrame(st.session_state.roster_dates)
        
        edited_df = st.data_editor(
            df_dates,
            column_config={
                "Date": st.column_config.DateColumn("Service Date", format="DD-MMM", disabled=True),
                "Combined": st.column_config.CheckboxColumn("MSS Combined?", default=False),
                "HC": st.column_config.CheckboxColumn("Holy Communion?", default=False),
                "Notes": st.column_config.TextColumn("Notes (Optional)"),
            },
            hide_index=True,
            use_container_width=True
        )

        col_l, col_r = st.columns([1, 5])
        if col_l.button("← Back"):
            st.session_state.stage = 1
            st.rerun()
        if col_r.button("Next: Availability →"):
            # Save back to session state in correct format
            st.session_state.roster_dates = edited_df.to_dict('records')
            st.session_state.stage = 3
            st.rerun()

    # --- STEP 3: UNAVAILABILITY ---
    elif st.session_state.stage == 3:
        st.header("Step 3: Unavailability")
        st.info("Select who is NOT available for specific dates.")

        # Initialize unavailability dict if new dates
        for r in st.session_state.roster_dates:
            d_str = str(r['Date'])
            if d_str not in st.session_state.unavailability:
                st.session_state.unavailability[d_str] = []

        # Create a UI form
        with st.form("avail_form"):
            for i, r_data in enumerate(st.session_state.roster_dates):
                d_obj = r_data['Date']
                d_str = str(d_obj)
                date_label = d_obj.strftime("%d-%b (%A)")
                
                st.multiselect(
                    f"{date_label}",
                    options=all_names,
                    key=f"na_{i}",
                    default=st.session_state.unavailability.get(d_str, [])
                )
            
            submitted = st.form_submit_button("Generate Roster")
            if submitted:
                # Update session state from widgets
                for i, r_data in enumerate(st.session_state.roster_dates):
                    d_str = str(r_data['Date'])
                    st.session_state.unavailability[d_str] = st.session_state[f"na_{i}"]
                st.session_state.stage = 4
                st.rerun()
        
        if st.button("← Back"):
            st.session_state.stage = 2
            st.rerun()

    # --- STEP 4: GENERATION & DISPLAY ---
    elif st.session_state.stage == 4:
        st.header("Step 4: Final Roster")
        
        # 1. Run the Algo
        engine = RosterEngine(df_team)
        raw_schedule = [] # List of dicts, one for each date

        # We will build the roster date by date
        for idx, r_data in enumerate(st.session_state.roster_dates):
            d_obj = r_data['Date']
            spec = RosterDateSpec(d_obj, r_data['HC'], r_data['Combined'], r_data['Notes'])
            
            unavailable = st.session_state.unavailability.get(str(d_obj), [])
            current_crew = []
            
            # Dictionary for this specific date column
            date_entry = {
                "Service Dates": d_obj.strftime("%d-%b"), # Column Header Lookalike
                "Additional Details": spec.display_details
            }
            
            # Assign Roles
            for role_conf in CONFIG.ROLES:
                person = engine.get_tech_candidate(role_conf['key'], unavailable, current_crew, idx)
                date_entry[role_conf['label']] = person
                if person: current_crew.append(person)
            
            # HARDCODED: Add Empty Cam 2 Row (as per screenshot requirement)
            date_entry["Cam 2"] = "" 

            # Assign Team Lead
            t_lead = engine.assign_lead(current_crew, unavailable, idx)
            date_entry["Team Lead"] = t_lead
            
            raw_schedule.append(date_entry)
            
            # Update history for next iteration
            engine.prev_week_crew = current_crew

        # 2. TRANSPOSE LOGIC (The crucial part for your requested format)
        
        # Create standard dataframe first
        df_schedule = pd.DataFrame(raw_schedule)
        
        # Transpose: Set Date as index then unstack, or just Transpose directly
        # Format desired: Rows = Roles, Cols = Dates
        
        # We need to set the index to something that won't be a row in the final output
        # Actually, let's just Transpose the whole thing and clean up headers
        
        # Extract the dates to be headers
        date_headers = df_schedule['Service Dates'].tolist()
        
        # Drop the 'Service Dates' column from data, as it will become headers
        df_t = df_schedule.drop(columns=['Service Dates']).T
        
        # Assign columns
        df_t.columns = date_headers
        
        # Reorder rows to match screenshot exactly:
        # 1. Additional Details
        # 2. Sound Crew
        # 3. Projectionist
        # 4. Stream Director
        # 5. Cam 1
        # 6. Cam 2
        # 7. Team Lead
        desired_order = [
            "Additional Details", 
            "Sound Crew", 
            "Projectionist", 
            "Stream Director", 
            "Cam 1", 
            "Cam 2", 
            "Team Lead"
        ]
        
        # Reindex checks if col exists (incase config changed), fill_value for empty Cam 2
        df_final_display = df_t.reindex(desired_order).fillna("")

        # 3. Display
        st.dataframe(df_final_display, use_container_width=True)
        
        # Stats below
        with st.expander("Show Load Statistics"):
            st.dataframe(engine.get_stats(), use_container_width=True)

        # 4. Download
        csv = df_final_display.to_csv().encode('utf-8')
        col1, col2 = st.columns(2)
        with col1:
             st.download_button(
                "📥 Download CSV",
                csv,
                "sws_roster_transposed.csv",
                "text/csv",
                key='download-csv'
            )
        with col2:
            if st.button("Start Over"):
                st.session_state.stage = 1
                st.session_state.roster_dates = []
                st.rerun()

if __name__ == "__main__":
    main()
