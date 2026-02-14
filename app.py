import streamlit as st
import pandas as pd
import random
import calendar
from datetime import datetime, date
from collections import defaultdict
from dataclasses import dataclass
from typing import List, Dict, Tuple

# ==========================================
# 1. CONFIGURATION
# ==========================================

@dataclass
class MinistryProfile:
    name: str
    gid: str
    is_welcome: bool = False
    primary_leads: Tuple[str, ...] = () 
    roles: List[Dict[str, str]] = None

MEDIA_PROFILE = MinistryProfile(
    name="Media Tech",
    gid="0", 
    primary_leads=("gavin", "ben", "mich lo"),
    roles=[
        {"label": "Sound Crew",      "sheet_col": "sound"},
        {"label": "Projectionist",   "sheet_col": "projection"},
        {"label": "Stream Director", "sheet_col": "stream director"},
        {"label": "Cam 1",           "sheet_col": "camera"},
    ]
)

WELCOME_PROFILE = MinistryProfile(
    name="Welcome Ministry",
    gid="2080125013",
    is_welcome=True
)

SHEET_ID = "1jh6ScfqpHe7rRN1s-9NYPsm7hwqWWLjdLKTYThRRGUo"

st.set_page_config(page_title="SWS Roster Wizard", layout="wide")

# ==========================================
# 2. CORE UTILS
# ==========================================

def init_state():
    if 'stage' not in st.session_state: st.session_state.stage = 0
    if 'selected_ministry' not in st.session_state: st.session_state.selected_ministry = None
    if 'roster_dates' not in st.session_state: st.session_state.roster_dates = []
    if 'unavailability' not in st.session_state: st.session_state.unavailability = {}
    if 'master_df' not in st.session_state: st.session_state.master_df = None

@st.cache_data(ttl=600)
def fetch_data(gid: str):
    url = f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/export?format=csv&gid={gid}"
    try:
        df = pd.read_csv(url).fillna("")
        df.columns = df.columns.str.strip().str.lower()
        return df
    except:
        return pd.DataFrame()

# ==========================================
# 3. WELCOME ENGINE (SCENARIO B: STRICT)
# ==========================================

class WelcomeEngine:
    def __init__(self, df: pd.DataFrame):
        self.df = df
        self.total_load = defaultdict(int)
        self.prev_week_crew = []

    def get_ui_name(self, name):
        if not name: return ""
        row = self.df[self.df['name'] == name].iloc[0]
        tags = []
        if str(row.get('male', '')).lower() == 'yes': tags.append("M")
        if str(row.get('senior citizen', '')).lower() == 'yes': tags.append("S")
        return f"{name} ({', '.join(tags)})" if tags else name

    def generate(self, dates_meta, unav_map):
        roster_rows = []
        # STRICT POOLS
        leads_pool = self.df[self.df['team lead'].astype(str).str.lower() == 'yes']['name'].tolist()
        members_pool = self.df[self.df['member'].astype(str).str.lower() == 'yes']['name'].tolist()

        for meta in dates_meta:
            d_obj = meta['Date']
            d_str = d_obj.strftime("%Y-%m-%d")
            team_size = 5 if meta.get('HC', False) else 4
            unav = unav_map.get(d_str, [])
            crew = []
            row_data = {"Service Date": d_obj.strftime("%d-%b"), "_month": d_obj.strftime("%B %Y")}

            # 1. Leader Slot (Strictly from leads_pool)
            avail_l = [l for l in leads_pool if l not in unav and l not in self.prev_week_crew]
            if not avail_l: avail_l = [l for l in leads_pool if l not in unav]
            if avail_l:
                avail_l.sort(key=lambda x: (self.total_load[x], random.uniform(0, 1)))
                leader = avail_l[0]
                row_data["Team Lead"] = self.get_ui_name(leader)
                crew.append(leader)
                self.total_load[leader] += 1

            # 2. Member Slots (Strictly from members_pool)
            while len(crew) < team_size:
                needs_m = not any(self.df[self.df['name']==p]['male'].str.lower().item()=='yes' for p in crew if p in members_pool)
                needs_s = not any(self.df[self.df['name']==p]['senior citizen'].str.lower().item()=='yes' for p in crew if p in members_pool)
                
                pool = [n for n in members_pool if n not in crew and n not in unav and n not in self.prev_week_crew]
                if not pool: pool = [n for n in members_pool if n not in crew and n not in unav]
                if not pool: break

                def score(n):
                    s = self.total_load[n]
                    r = self.df[self.df['name'] == n].iloc[0]
                    if needs_m and str(r.get('male','')).lower()=='yes': s -= 10
                    if needs_s and str(r.get('senior citizen','')).lower()=='yes': s -= 10
                    return (s, random.uniform(0,1))

                pool.sort(key=score)
                pick = pool[0]
                
                # Couple logic
                row = self.df[self.df['name'] == pick].iloc[0]
                c_id = str(row.get('couple','')).strip()
                partner = ""
                if c_id:
                    p_row = self.df[(self.df['couple'].astype(str)==c_id) & (self.df['name']!=pick)]
                    partner = p_row['name'].iloc[0] if not p_row.empty else ""

                if partner and len(crew) + 2 > team_size:
                    singles = [p for p in pool if not str(self.df[self.df['name']==p]['couple'].iloc[0]).strip()]
                    if not singles: break
                    pick = singles[0]
                    partner = ""

                row_data[f"Member {len(crew)}"] = self.get_ui_name(pick)
                crew.append(pick)
                self.total_load[pick] += 1
                if partner:
                    row_data[f"Member {len(crew)}"] = self.get_ui_name(partner)
                    crew.append(partner)
                    self.total_load[partner] += 1

            self.prev_week_crew = crew
            roster_rows.append(row_data)
        return pd.DataFrame(roster_rows)

# ==========================================
# 4. MAIN APP UI
# ==========================================

def main():
    init_state()
    if st.session_state.stage == 0:
        st.title("⛪ SWS Roster Wizard")
        c1, c2 = st.columns(2)
        if c1.button("📹 Media Tech", use_container_width=True):
            st.session_state.selected_ministry = MEDIA_PROFILE
            st.session_state.stage = 1; st.rerun()
        if c2.button("🤝 Welcome Ministry", use_container_width=True):
            st.session_state.selected_ministry = WELCOME_PROFILE
            st.session_state.stage = 1; st.rerun()
    else:
        profile = st.session_state.selected_ministry
        df = fetch_data(profile.gid)
        if st.sidebar.button("← Switch Ministry"):
            for k in ['stage','master_df','roster_dates','unavailability']: st.session_state[k] = None if k!='stage' else 0
            st.rerun()

        if st.session_state.stage == 1:
            st.header(f"Dates: {profile.name}")
            col1, col2 = st.columns(2)
            year = col1.number_input("Year", value=2026)
            months = col2.multiselect("Months", list(calendar.month_name)[1:], default=[calendar.month_name[date.today().month+1]])
            if st.button("Generate Sundays"):
                m_idx = {m: i for i, m in enumerate(calendar.month_name)}
                st.session_state.roster_dates = [{"Date": date(year, m_idx[m], d), "HC": False} 
                                               for m in months for d in range(1, calendar.monthrange(year, m_idx[m])[1]+1) 
                                               if date(year, m_idx[m], d).weekday() == 6]
                st.session_state.stage = 2; st.rerun()

        elif st.session_state.stage == 2:
            st.header("Service Details")
            st.session_state.roster_dates = st.data_editor(st.session_state.roster_dates, use_container_width=True)
            if st.button("Next"): st.session_state.stage = 3; st.rerun()

        elif st.session_state.stage == 3:
            st.header("Availability")
            names = sorted(df['name'].unique())
            dates = [d['Date'].strftime("%Y-%m-%d") for d in st.session_state.roster_dates]
            with st.form("unav"):
                cols = st.columns(3)
                for i, name in enumerate(names):
                    with cols[i%3]: st.multiselect(name, options=dates, key=f"un_{name}")
                if st.form_submit_button("Generate Roster"):
                    st.session_state.unavailability = {d: [n for n in names if d in st.session_state.get(f"un_{n}", [])] for d in dates}
                    st.session_state.stage = 4; st.rerun()

        elif st.session_state.stage == 4:
            st.header("Final Roster Dashboard")
            if st.session_state.master_df is None:
                if profile.is_welcome:
                    st.session_state.master_df = WelcomeEngine(df).generate(st.session_state.roster_dates, st.session_state.unavailability)
                else:
                    st.warning("Media logic integration pending final profile check.")
            
            st.data_editor(st.session_state.master_df, use_container_width=True)
            if st.button("Start Over"):
                st.session_state.stage = 0; st.session_state.master_df = None; st.rerun()

if __name__ == "__main__":
    main()
