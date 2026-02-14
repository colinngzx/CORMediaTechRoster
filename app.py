import streamlit as st
import pandas as pd
import random
import calendar
from datetime import datetime, date
from collections import defaultdict
from typing import List, Dict, Tuple

# ==========================================
# 1. CONFIGURATION
# ==========================================

# Ministry-Specific Configurations based on your Google Sheet columns
MINISTRIES = {
    "Media Tech": {
        "gid": "0",
        "roles": [
            {"label": "Sound Crew",      "sheet_col": "sound"},
            {"label": "Projectionist",   "sheet_col": "projection"},
            {"label": "Stream Director", "sheet_col": "stream director"},
            {"label": "Cam 1",           "sheet_col": "camera"},
        ],
        "extra_cols": ["Cam 2", "Team Lead"],
        "primary_leads": ["gavin", "ben", "mich lo"]
    },
    "Welcome Ministry": {
        "gid": "2080125013",
        "roles": [
            {"label": "Member 1", "sheet_col": "member"},
            {"label": "Member 2", "sheet_col": "member"},
            {"label": "Member 3", "sheet_col": "member"},
            {"label": "Member 4", "sheet_col": "member"},
        ],
        "extra_cols": ["Team Lead"],
        "primary_leads": [] # Uses "Team Lead" column instead
    }
}

# ==========================================
# 2. STATE MANAGEMENT
# ==========================================

def init_state():
    if 'stage' not in st.session_state: st.session_state.stage = 1
    if 'ministry' not in st.session_state: st.session_state.ministry = "Media Tech"
    if 'roster_dates' not in st.session_state: st.session_state.roster_dates = []
    if 'master_roster_df' not in st.session_state: st.session_state.master_roster_df = None
    if 'unavailability' not in st.session_state: st.session_state.unavailability = {}

def reset_roster_data():
    """Clears generated data so fresh pools are pulled for a new ministry."""
    st.session_state.master_roster_df = None
    st.session_state.unavailability = {}

# ==========================================
# 3. DATA ENGINE
# ==========================================

@st.cache_data(ttl=600)
def fetch_sheet_data(ministry_name: str) -> pd.DataFrame:
    sheet_id = "1jh6ScfqpHe7rRN1s-9NYPsm7hwqWWLjdLKTYThRRGUo"
    gid = MINISTRIES[ministry_name]["gid"]
    url = f"https://docs.google.com/spreadsheets/d/{sheet_id}/export?format=csv&gid={gid}"
    try:
        df = pd.read_csv(url).fillna("")
        df.columns = df.columns.str.strip().str.lower()
        return df
    except Exception as e:
        st.error(f"Error fetching {ministry_name} data: {e}")
        return pd.DataFrame()

class RosterEngine:
    def __init__(self, df: pd.DataFrame, ministry_name: str):
        self.df = df
        self.ministry = ministry_name
        self.config = MINISTRIES[ministry_name]
        self.team_names = [n for n in df['name'].unique() if str(n).strip()]
        self.tech_load = defaultdict(int)
        self.lead_load = defaultdict(int)
        self.prev_crew = []

    def get_candidate(self, col: str, unavailable: List[str], current_crew: List[str]) -> str:
        # Check for 'yes' in the specific role column
        candidates = self.df[self.df[col].astype(str).str.lower().str.contains('yes')]['name'].tolist()
        
        # Filtering logic
        pool = [p for p in candidates if p not in unavailable and p not in current_crew and p not in self.prev_crew]
        if not pool: pool = [p for p in candidates if p not in unavailable and p not in current_crew]
        
        if not pool: return ""
        
        # Weighting by load + randomness
        pool.sort(key=lambda x: (self.tech_load[x], random.uniform(0, 1)))
        pick = pool[0]
        self.tech_load[pick] += 1
        return pick

    def assign_lead(self, current_crew: List[str]) -> str:
        if not current_crew: return ""
        
        # 1. Media Tech specific primary leads
        if self.config["primary_leads"]:
            primaries = [p for p in current_crew if any(pl.lower() in p.lower() for pl in self.config["primary_leads"])]
            if primaries:
                primaries.sort(key=lambda x: self.lead_load[x])
                self.lead_load[primaries[0]] += 1
                return primaries[0]

        # 2. General Team Lead column check
        capable = [p for p in current_crew if 'yes' in str(self.df[self.df['name']==p]['team lead'].iloc[0]).lower()]
        if capable:
            capable.sort(key=lambda x: self.lead_load[x])
            self.lead_load[capable[0]] += 1
            return capable[0]
        return ""

# ==========================================
# 4. UI STAGES
# ==========================================

def step_1():
    st.header("📅 Step 1: Ministry & Date Selection")
    
    # Selection triggers a reset if changed
    new_min = st.selectbox("Select Ministry", list(MINISTRIES.keys()), index=0 if st.session_state.ministry == "Media Tech" else 1)
    if new_min != st.session_state.ministry:
        st.session_state.ministry = new_min
        reset_roster_data()
        
    col1, col2 = st.columns(2)
    year = col1.number_input("Year", value=2026)
    months = col2.multiselect("Months", list(calendar.month_name)[1:], default=["January"])
    
    if st.button("Generate Roster Dates", type="primary"):
        month_map = {m: i for i, m in enumerate(calendar.month_name) if m}
        dates = []
        for m in months:
            _, days = calendar.monthrange(year, month_map[m])
            for d in range(1, days + 1):
                curr = date(year, month_map[m], d)
                if curr.weekday() == 6: dates.append({"Date": curr, "HC": False, "Notes": ""})
        st.session_state.roster_dates = dates
        st.session_state.stage = 2
        st.rerun()

def step_2():
    st.header("⚙️ Step 2: Service Details")
    df = pd.DataFrame(st.session_state.roster_dates)
    edited = st.data_editor(df, use_container_width=True)
    
    if st.button("Next: Set Unavailability →"):
        st.session_state.roster_dates = edited.to_dict('records')
        st.session_state.stage = 3
        st.rerun()

def step_3(names):
    st.header("❌ Step 3: Unavailability")
    date_strs = [d['Date'].strftime("%Y-%m-%d") for d in st.session_state.roster_dates]
    
    with st.form("unav_form"):
        cols = st.columns(3)
        temp_unav = {}
        for i, name in enumerate(names):
            with cols[i%3]:
                temp_unav[name] = st.multiselect(name, date_strs)
        if st.form_submit_button("Generate Final Roster", type="primary"):
            st.session_state.unavailability = temp_unav
            st.session_state.master_roster_df = None # Force engine to run
            st.session_state.stage = 4
            st.rerun()

def step_4(df_team):
    st.header("📋 Step 4: Roster Dashboard")
    cfg = MINISTRIES[st.session_state.ministry]
    
    # Generate initial roster if not exists
    if st.session_state.master_roster_df is None:
        engine = RosterEngine(df_team, st.session_state.ministry)
        data = []
        for meta in st.session_state.roster_dates:
            d_str = meta['Date'].strftime("%Y-%m-%d")
            unav = [n for n, dates in st.session_state.unavailability.items() if d_str in dates]
            row = {"Date": meta['Date'].strftime("%d-%b"), "Month": meta['Date'].strftime("%B %Y"), "Notes": meta['Notes']}
            if meta.get('HC'): row['Notes'] = "HC"
            
            crew = []
            for r in cfg["roles"]:
                p = engine.get_candidate(r['sheet_col'], unav, crew)
                row[r['label']] = p
                if p: crew.append(p)
            
            if "Cam 2" in cfg["extra_cols"]: row["Cam 2"] = ""
            row["Team Lead"] = engine.assign_lead(crew)
            data.append(row)
            engine.prev_crew = crew
        st.session_state.master_roster_df = pd.DataFrame(data)

    master_df = st.session_state.master_roster_df
    display_cols = ["Notes"] + [r['label'] for r in cfg["roles"]] + cfg["extra_cols"]

    # Display Editors by Month
    for month in master_df['Month'].unique():
        with st.expander(f"Edit {month}", expanded=True):
            sub_df = master_df[master_df['Month'] == month].copy().set_index("Date")
            view = sub_df[display_cols].T
            edited_view = st.data_editor(view, use_container_width=True, key=f"edit_{month}")
            
            # Sync manual edits back to master
            if not edited_view.equals(view):
                for d_col in edited_view.columns:
                    for r_label in edited_view.index:
                        val = edited_view.at[r_label, d_col]
                        master_df.loc[master_df['Date'] == d_col, r_label] = val
                st.session_state.master_roster_df = master_df
                st.rerun()

    # --- LIVE LOAD STATISTICS (Case-Insensitive) ---
    st.markdown("---")
    st.subheader("📊 Live Load Statistics")
    
    canonical_names = {n.lower().strip(): n for n in df_team['name'].unique()}
    stats = defaultdict(lambda: {"Tech": 0, "Lead": 0})
    
    # Scan the current master_df for counts
    for _, row in master_df.iterrows():
        for col in master_df.columns:
            if col in ["Date", "Month", "Notes"]: continue
            name_entry = str(row[col]).lower().strip()
            if name_entry in canonical_names:
                real_name = canonical_names[name_entry]
                if col == "Team Lead": stats[real_name]["Lead"] += 1
                else: stats[real_name]["Tech"] += 1
    
    if stats:
        stat_rows = [{"Name": n, "Tech Shifts": d["Tech"], "Lead Shifts": d["Lead"], "Total": d["Tech"]+d["Lead"]} 
                     for n, d in stats.items()]
        st.table(pd.DataFrame(stat_rows).sort_values("Total", ascending=False))
    else:
        st.info("No assignments found.")

    if st.button("Start Over"):
        st.session_state.stage = 1
        reset_roster_data()
        st.rerun()

# ==========================================
# 5. MAIN
# ==========================================

def main():
    init_state()
    df_team = fetch_sheet_data(st.session_state.ministry)
    if df_team.empty: return
    
    names = sorted([n for n in df_team['name'].unique() if str(n).strip()])

    if st.session_state.stage == 1: step_1()
    elif st.session_state.stage == 2: step_2()
    elif st.session_state.stage == 3: step_3(names)
    elif st.session_state.stage == 4: step_4(df_team)

if __name__ == "__main__":
    main()
