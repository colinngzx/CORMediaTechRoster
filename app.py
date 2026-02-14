import streamlit as st
import pandas as pd
import random
import calendar
from datetime import datetime, date
from collections import defaultdict
from typing import List, Dict, Tuple
from dataclasses import dataclass

# ==========================================
# 1. CONFIGURATION & STYLES
# ==========================================

@dataclass(frozen=True)
class AppConfig:
    PAGE_TITLE: str = "SWS Roster Wizard"
    SHEET_ID: str = "1jh6ScfqpHe7rRN1s-9NYPsm7hwqWWLjdLKTYThRRGUo"
    PRIMARY_LEADS: Tuple[str, ...] = ("gavin", "ben", "mich lo") 
    
    # Ministry-Specific Configurations
    MINISTRIES: Dict = None

# Initialize configurations
MINISTRIES = {
    "Media Tech": {
        "gid": "0",
        "roles": (
            {"label": "Sound Crew",      "sheet_col": "sound"},
            {"label": "Projectionist",   "sheet_col": "projection"},
            {"label": "Stream Director", "sheet_col": "stream director"},
            {"label": "Cam 1",           "sheet_col": "camera"},
        ),
        "extra_cols": ["Cam 2", "Team Lead"]
    },
    "Welcome Ministry": {
        "gid": "2080125013",
        "roles": (
            {"label": "Team Lead", "sheet_col": "team lead"},
            {"label": "Member 1",  "sheet_col": "member"},
            {"label": "Member 2",  "sheet_col": "member"},
            {"label": "Member 3",  "sheet_col": "member"},
            {"label": "Member 4",  "sheet_col": "member"},
        ),
        "extra_cols": []
    }
}

CONFIG = AppConfig()

st.set_page_config(page_title=CONFIG.PAGE_TITLE, layout="wide", initial_sidebar_state="expanded")

# Your Original Excel-like CSS
st.markdown("""
<style>
    .roster-header { background-color: #4f81bd; color: white; padding: 10px; text-align: center; font-weight: bold; border: 1px solid #385d8a; }
    table.custom-table { width: 100%; border-collapse: collapse; font-family: Calibri, Arial, sans-serif; font-size: 14px; }
    table.custom-table th { background-color: #dce6f1; border: 1px solid #8e8e8e; padding: 5px; color: #1f497d; }
    table.custom-table td { border: 1px solid #a6a6a6; padding: 5px; text-align: center; }
    .date-row { background-color: #f2f2f2; font-weight: bold; }
</style>
""", unsafe_allow_html=True)

# ==========================================
# 2. STATE MANAGEMENT
# ==========================================

class SessionManager:
    @staticmethod
    def init():
        defaults = {
            'stage': 1,
            'ministry': "Media Tech",
            'roster_dates': [],
            'unavailability_by_person': {},
            'master_roster_df': None,
        }
        for key, val in defaults.items():
            if key not in st.session_state:
                st.session_state[key] = val

    @staticmethod
    def reset():
        for key in list(st.session_state.keys()):
            del st.session_state[key]
        SessionManager.init()

# ==========================================
# 3. DATA & UTILS
# ==========================================

class DataLoader:
    @staticmethod
    @st.cache_data(ttl=900)
    def fetch_data(ministry_name: str) -> pd.DataFrame:
        gid = MINISTRIES[ministry_name]["gid"]
        url = f"https://docs.google.com/spreadsheets/d/{CONFIG.SHEET_ID}/export?format=csv&gid={gid}"
        try:
            df = pd.read_csv(url).fillna("")
            df.columns = df.columns.str.strip().str.lower()
            return df
        except Exception as e:
            st.error(f"⚠️ Data Error: {e}")
            return pd.DataFrame()

class DateUtils:
    @staticmethod
    def get_upcoming_window():
        now = datetime.now()
        target_year = 2026 # Forcing 2026 as per user instruction
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
            _, days = calendar.monthrange(year, m_idx)
            for day in range(1, days + 1):
                curr = date(year, m_idx, day)
                if curr.weekday() == 6: valid_dates.append(curr)
        return sorted(valid_dates)

# ==========================================
# 4. ROSTER ENGINE
# ==========================================

class RosterEngine:
    def __init__(self, people_df: pd.DataFrame, ministry_name: str):
        self.df = people_df
        self.ministry = ministry_name
        self.team_names = sorted([n for n in self.df['name'].unique() if str(n).strip() != ""], key=lambda x: str(x).lower())
        self.tech_load = defaultdict(int)
        self.lead_load = defaultdict(int)
        self.prev_week_crew = []

    def get_candidate(self, role_col: str, unavailable: List[str], current_crew: List[str], is_hc_or_comb: bool) -> str:
        # Filter people marked with 'yes' for that role
        candidates = self.df[self.df[role_col].astype(str).str.lower() == 'yes']['name'].tolist()
        
        # Primary filter
        available = [p for p in candidates if p not in unavailable and p not in current_crew and p not in self.prev_week_crew]
        if not available: # Soft fallback
            available = [p for p in candidates if p not in unavailable and p not in current_crew]
        
        if not available: return ""

        # Load balancing
        available.sort(key=lambda x: (self.tech_load[x], random.uniform(0, 1)))
        
        # Diversity logic for Welcome Ministry (Bonus logic)
        if self.ministry == "Welcome Ministry":
            # Prioritize Male/Seniors if not present in crew yet
            has_male = any(self.df[self.df['name']==c]['male'].str.lower().item()=='yes' for c in current_crew if c in self.team_names)
            if not has_male:
                males = [a for a in available if str(self.df[self.df['name']==a]['male'].iloc[0]).lower() == 'yes']
                if males: available = males

        selected = available[0]
        self.tech_load[selected] += 1
        return selected

    def assign_lead(self, current_crew: List[str]) -> str:
        if not current_crew: return ""
        # Media Tech specific primary leads
        if self.ministry == "Media Tech":
            primaries = [p for p in current_crew if any(pl.lower() in p.lower() for pl in CONFIG.PRIMARY_LEADS)]
            if primaries:
                primaries.sort(key=lambda x: self.lead_load[x])
                self.lead_load[primaries[0]] += 1
                return primaries[0]

        # General lead logic
        capable = [p for p in current_crew if str(self.df[self.df['name']==p]['team lead'].iloc[0]).lower() == 'yes']
        if capable:
            capable.sort(key=lambda x: self.lead_load[x])
            self.lead_load[capable[0]] += 1
            return capable[0]
        return ""

# ==========================================
# 5. UI COMPONENTS
# ==========================================

def render_step_1():
    st.header("Step 1: Selection & Period")
    st.session_state.ministry = st.selectbox("Select Ministry", ["Media Tech", "Welcome Ministry"])
    with st.container(border=True):
        col1, col2 = st.columns(2)
        def_year, def_months = DateUtils.get_upcoming_window()
        year = col1.number_input("Year", value=def_year)
        months = col2.multiselect("Months", list(calendar.month_name)[1:], default=def_months)

        if st.button("Generate Dates", type="primary"):
            dates = DateUtils.generate_sundays(year, months)
            st.session_state.roster_dates = [{"Date": d, "Combined": False, "HC": False, "Notes": ""} for d in dates]
            st.session_state.stage = 2
            st.rerun()

def render_step_2():
    st.header("Step 2: Service Details")
    col_d, col_b = st.columns([3, 1])
    new_date = col_d.date_input("Manual Date Add", value=None, label_visibility="collapsed")
    if col_b.button("➕ Add Date"):
        if new_date:
            st.session_state.roster_dates.append({"Date": new_date, "Combined": False, "HC": False, "Notes": ""})
            st.session_state.roster_dates.sort(key=lambda x: str(x['Date']))
            st.rerun()

    df_dates = pd.DataFrame(st.session_state.roster_dates)
    if not df_dates.empty: df_dates['Date'] = pd.to_datetime(df_dates['Date']).dt.date
    
    edited = st.data_editor(df_dates, use_container_width=True, num_rows="dynamic", key="date_editor")
    
    c1, c2 = st.columns([1, 4])
    if c1.button("← Back"): st.session_state.stage = 1; st.rerun()
    if c2.button("Next: Availability →", type="primary"):
        st.session_state.roster_dates = edited.to_dict('records')
        st.session_state.stage = 3; st.rerun()

def render_step_3(all_names):
    st.header("Step 3: Unavailability")
    date_strs = [d['Date'].strftime("%Y-%m-%d") for d in st.session_state.roster_dates]
    
    with st.form("unav_form"):
        cols = st.columns(3)
        temp = {}
        for i, name in enumerate(all_names):
            with cols[i % 3]:
                temp[name] = st.multiselect(name, options=date_strs, default=st.session_state.unavailability_by_person.get(name, []))
        if st.form_submit_button("Generate Roster", type="primary"):
            st.session_state.unavailability_by_person = temp
            st.session_state.master_roster_df = None
            st.session_state.stage = 4; st.rerun()
    if st.button("← Back"): st.session_state.stage = 2; st.rerun()

def render_step_4(df_team):
    st.header("Step 4: Roster Dashboard")
    min_config = MINISTRIES[st.session_state.ministry]
    
    if st.session_state.master_roster_df is None:
        engine = RosterEngine(df_team, st.session_state.ministry)
        rows = []
        for idx, meta in enumerate(st.session_state.roster_dates):
            d = meta['Date']
            d_str = d.strftime("%Y-%m-%d")
            unav = [name for name, dates in st.session_state.unavailability_by_person.items() if d_str in dates]
            
            row = {"Service Date": d.strftime("%d-%b"), "_month": d.strftime("%B %Y"), 
                   "Details": f"{'HC' if meta['HC'] else ''} {'Combined' if meta['Combined'] else ''} {meta['Notes']}".strip()}
            
            crew = []
            for r in min_config["roles"]:
                p = engine.get_candidate(r['sheet_col'], unav, crew, meta['HC'] or meta['Combined'])
                row[r['label']] = p
                if p: crew.append(p)
            
            if "Cam 2" in min_config["extra_cols"]: row["Cam 2"] = ""
            row["Team Lead"] = engine.assign_lead(crew)
            rows.append(row)
            engine.prev_week_crew = crew
        st.session_state.master_roster_df = pd.DataFrame(rows)

    master_df = st.session_state.master_roster_df
    row_order = ["Details"] + [r['label'] for r in min_config["roles"]] + min_config["extra_cols"]
    
    # Transposed Editor
    for month in master_df['_month'].unique():
        with st.expander(f"Edit {month}", expanded=True):
            sub = master_df[master_df['_month'] == month].copy().set_index("Service Date")
            view = sub[row_order].T
            edited_view = st.data_editor(view, use_container_width=True, key=f"ed_{month}")
            if not edited_view.equals(view):
                for d_col in edited_view.columns:
                    for r_row in edited_view.index:
                        master_df.loc[master_df['Service Date'] == d_col, r_row] = edited_view.at[r_row, d_col]
                st.session_state.master_roster_df = master_df
                st.rerun()

    # Footer
    st.markdown("---")
    c1, c2, c3 = st.columns(3)
    if c1.button("← Back"): st.session_state.stage = 3; st.rerun()
    if c2.button("🔄 Regenerate"): st.session_state.master_roster_df = None; st.rerun()
    if c3.button("Start Over"): SessionManager.reset(); st.rerun()

def main():
    SessionManager.init()
    df_team = DataLoader.fetch_data(st.session_state.ministry)
    if df_team.empty: return
    
    all_names = sorted([n for n in df_team['name'].unique() if str(n).strip() != ""], key=lambda x: str(x).lower())

    if st.session_state.stage == 1: render_step_1()
    elif st.session_state.stage == 2: render_step_2()
    elif st.session_state.stage == 3: render_step_3(all_names)
    elif st.session_state.stage == 4: render_step_4(df_team)

if __name__ == "__main__":
    main()
