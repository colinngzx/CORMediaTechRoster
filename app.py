import streamlit as st
import pandas as pd
import random
import calendar
from datetime import datetime, date
from collections import defaultdict
from typing import List, Dict, Tuple
from dataclasses import dataclass

# ==========================================
# 1. CONFIGURATION & STYLES (ORIGINAL)
# ==========================================

@dataclass(frozen=True)
class AppConfig:
    PAGE_TITLE: str = "SWS Roster Wizard"
    SHEET_ID: str = "1jh6ScfqpHe7rRN1s-9NYPsm7hwqWWLjdLKTYThRRGUo"
    PRIMARY_LEADS: Tuple[str, ...] = ("gavin", "ben", "mich lo") 
    ROLES: Tuple[Dict[str, str], ...] = (
        {"label": "Sound Crew",      "sheet_col": "sound"},
        {"label": "Projectionist",   "sheet_col": "projection"},
        {"label": "Stream Director", "sheet_col": "stream director"},
        {"label": "Cam 1",           "sheet_col": "camera"},
    )

CONFIG = AppConfig()
WELCOME_GID = "2080125013"

st.set_page_config(page_title=CONFIG.PAGE_TITLE, layout="wide")

STYLING_CSS = """
<style>
    .roster-header { background-color: #4f81bd; color: white; padding: 10px; text-align: center; font-weight: bold; border: 1px solid #385d8a; }
    table.custom-table { width: 100%; border-collapse: collapse; font-family: Calibri, Arial, sans-serif; font-size: 14px; }
    table.custom-table th { background-color: #dce6f1; border: 1px solid #8e8e8e; padding: 5px; color: #1f497d; }
    table.custom-table td { border: 1px solid #a6a6a6; padding: 5px; text-align: center; }
</style>
"""
st.markdown(STYLING_CSS, unsafe_allow_html=True)

# ==========================================
# 2. STATE & DATA LOADING
# ==========================================

if 'stage' not in st.session_state: st.session_state.stage = 1
if 'ministry' not in st.session_state: st.session_state.ministry = "Media Tech"
if 'roster_dates' not in st.session_state: st.session_state.roster_dates = []
if 'unavailability' not in st.session_state: st.session_state.unavailability = {}
if 'master_roster_df' not in st.session_state: st.session_state.master_roster_df = None

class DataLoader:
    @staticmethod
    @st.cache_data(ttl=900)
    def fetch_data(gid: str) -> pd.DataFrame:
        url = f"https://docs.google.com/spreadsheets/d/{CONFIG.SHEET_ID}/export?format=csv&gid={gid}"
        df = pd.read_csv(url).fillna("")
        df.columns = df.columns.str.strip().str.lower()
        return df

# ==========================================
# 3. ROSTER ENGINES (FIXED LOGIC)
# ==========================================

class MediaEngine:
    """Original logic for Media Tech."""
    def __init__(self, df):
        self.df = df
        self.load = defaultdict(int)
        self.lead_load = defaultdict(int)
        self.prev_crew = []

    def get_candidate(self, role_col, unavailable, current_crew):
        if role_col not in self.df.columns: return ""
        pool = self.df[self.df[role_col].astype(str).str.strip() != ""]['name'].tolist()
        # Rotation: Avoid last week if possible
        available = [p for p in pool if p not in unavailable and p not in current_crew and p not in self.prev_crew]
        if not available: available = [p for p in pool if p not in unavailable and p not in current_crew]
        if not available: return ""
        available.sort(key=lambda x: (self.load[x], random.uniform(0, 1)))
        sel = available[0]
        self.load[sel] += 1
        return sel

    def assign_lead(self, crew):
        primaries = [p for p in crew if any(pl.lower() in p.lower() for pl in CONFIG.PRIMARY_LEADS)]
        if primaries:
            primaries.sort(key=lambda x: self.lead_load[x])
            self.lead_load[primaries[0]] += 1
            return primaries[0]
        return ""

class WelcomeEngine:
    """New logic for Welcome Ministry: Couples & No consecutive streaks."""
    def __init__(self, df):
        self.df = df
        self.load = defaultdict(int)
        self.prev_crew = []

    def get_pool(self, role=None, gender=None):
        pool = self.df.copy()
        if role: pool = pool[pool[role.lower()].astype(str).str.lower().str.contains('yes')]
        if gender: pool = pool[pool['male'].astype(str).str.lower().str.contains('yes')]
        return pool

    def select_person(self, pool_df, unavailable, crew, force_rotate=True):
        # Filter availability
        names = pool_df['name'].tolist()
        available = [n for n in names if n not in unavailable and n not in crew]
        
        # FIXED: Valerie Penalty (Consecutive week block)
        if force_rotate:
            rotate_pool = [n for n in available if n not in self.prev_crew]
            if rotate_pool: available = rotate_pool

        if not available: return None
        available.sort(key=lambda x: (self.load[x], random.uniform(0, 1)))
        return available[0]

# ==========================================
# 4. APP STEPS
# ==========================================

def step_1():
    st.header("📅 Step 1: Ministry & Months")
    st.session_state.ministry = st.selectbox("Ministry", ["Media Tech", "Welcome Ministry"])
    col1, col2 = st.columns(2)
    year = col1.number_input("Year", value=2026)
    months = col2.multiselect("Months", list(calendar.month_name)[1:], default=["March", "April"])
    if st.button("Generate Dates"):
        m_map = {m: i for i, m in enumerate(calendar.month_name) if m}
        dates = []
        for m in months:
            _, days = calendar.monthrange(year, m_map[m])
            for d in range(1, days + 1):
                curr = date(year, m_map[m], d)
                if curr.weekday() == 6: dates.append({"Date": curr, "HC": False, "Combined": False, "Notes": ""})
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
    d_strs = [str(d['Date']) for d in st.session_state.roster_dates]
    with st.form("unav"):
        cols = st.columns(3)
        temp = {n: cols[i%3].multiselect(n, d_strs) for i, n in enumerate(names)}
        if st.form_submit_button("Generate Roster"):
            st.session_state.unavailability = temp
            st.session_state.master_roster_df = None
            st.session_state.stage = 4
            st.rerun()

def step_4(df_team):
    st.header(f"📋 Step 4: {st.session_state.ministry} Roster")
    
    if st.session_state.master_roster_df is None:
        data = []
        if st.session_state.ministry == "Media Tech":
            engine = MediaEngine(df_team)
            for meta in st.session_state.roster_dates:
                d_str = str(meta['Date'])
                unav = [n for n, dts in st.session_state.unavailability.items() if d_str in dts]
                row = {"Date": pd.to_datetime(meta['Date']).strftime("%d-%b"), "Month": pd.to_datetime(meta['Date']).strftime("%B %Y"), "Notes": meta['Notes']}
                crew = []
                for r in CONFIG.ROLES:
                    p = engine.get_candidate(r['sheet_col'], unav, crew)
                    row[r['label']] = p
                    if p: crew.append(p)
                row["Cam 2"] = ""
                row["Team Lead"] = engine.assign_lead(crew)
                data.append(row)
                engine.prev_crew = crew
        
        else: # WELCOME LOGIC: Pairs and No Streaks
            engine = WelcomeEngine(df_team)
            for meta in st.session_state.roster_dates:
                d_str = str(meta['Date'])
                unav = [n for n, dts in st.session_state.unavailability.items() if d_str in dts]
                row = {"Date": pd.to_datetime(meta['Date']).strftime("%d-%b"), "Month": pd.to_datetime(meta['Date']).strftime("%B %Y"), "Notes": meta['Notes']}
                crew = []
                
                # 1. Team Lead (Exclusive Pool)
                tl = engine.select_person(engine.get_pool(role="Team lead"), unav, crew)
                row["Team Lead"] = tl
                if tl: crew.append(tl); engine.load[tl] += 1
                
                # 2. Members + Couple Logic
                slots = ["Member 1", "Member 2", "Member 3", "Member 4"]
                for s in slots:
                    if s in row: continue
                    p = engine.select_person(engine.get_pool(), unav, crew)
                    if p:
                        row[s] = p; crew.append(p); engine.load[p] += 1
                        # Check for Couple ID (Column F)
                        c_id = df_team.loc[df_team['name'] == p, 'couple'].values[0]
                        if c_id and str(c_id).strip() != "":
                            partner_df = df_team[(df_team['couple'] == c_id) & (df_team['name'] != p)]
                            if not partner_df.empty:
                                partner_name = partner_df['name'].values[0]
                                if partner_name not in unav and partner_name not in crew:
                                    # Find next empty slot
                                    for next_s in slots:
                                        if next_s not in row:
                                            row[next_s] = partner_name
                                            crew.append(partner_name); engine.load[partner_name] += 1
                                            break
                data.append(row)
                engine.prev_crew = crew
        st.session_state.master_roster_df = pd.DataFrame(data)

    m_df = st.session_state.master_roster_df
    roles = [r['label'] for r in CONFIG.ROLES] + ["Cam 2", "Team Lead"] if st.session_state.ministry == "Media Tech" else ["Team Lead", "Member 1", "Member 2", "Member 3", "Member 4"]
    
    for month in m_df['Month'].unique():
        with st.expander(f"Edit {month}", expanded=True):
            sub = m_df[m_df['Month'] == month].copy().set_index("Date")
            view = sub[[c for c in roles if c in sub.columns]].T
            st.data_editor(view, use_container_width=True, key=f"ed_{month}")

    # ==========================================
    # 5. LIVE LOAD STATISTICS (FINAL STAGE)
    # ==========================================
    st.divider()
    st.subheader(f"📊 {st.session_state.ministry} Live Load Statistics")
    
    stats_data = []
    # Count occurrences in the current master_roster_df
    role_cols = [c for c in roles if c in m_df.columns]
    all_rostered = m_df[role_cols].values.flatten()
    counts = pd.Series(all_rostered).value_counts()
    
    for name in sorted(df_team['name'].unique()):
        if not name: continue
        total = int(counts.get(name, 0))
        stats_data.append({"Name": name, "Total Shifts": total})
    
    st.table(pd.DataFrame(stats_data).sort_values("Total Shifts", ascending=False))
    if st.button("Start Over"): st.session_state.stage = 1; st.rerun()

def main():
    gid = "0" if st.session_state.ministry == "Media Tech" else WELCOME_GID
    df_team = DataLoader.fetch_data(gid)
    if st.session_state.stage == 1: step_1()
    elif st.session_state.stage == 2: step_2()
    elif st.session_state.stage == 3: step_3(sorted(df_team['name'].unique()))
    elif st.session_state.stage == 4: step_4(df_team)

if __name__ == "__main__": main()
