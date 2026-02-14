import streamlit as st
import pandas as pd
import random
import calendar
from datetime import datetime, date
from collections import defaultdict

# ==========================================
# 1. CONFIGURATION & STATE
# ==========================================

MINISTRIES = {
    "Media Tech": {
        "gid": "0",
        "roles": ["Sound Crew", "Projectionist", "Stream Director", "Cam 1"],
        "extra_cols": ["Cam 2", "Team Lead"],
        "primary_leads": ["gavin", "ben", "mich lo"]
    },
    "Welcome Ministry": {
        "gid": "2080125013",
        "roles": ["Member 1", "Member 2", "Member 3", "Member 4"],
        "extra_cols": ["Team Lead"],
        "primary_leads": []
    }
}

def init_state():
    if 'stage' not in st.session_state: st.session_state.stage = 1
    if 'ministry' not in st.session_state: st.session_state.ministry = "Media Tech"
    if 'master_roster_df' not in st.session_state: st.session_state.master_roster_df = None
    if 'unavailability' not in st.session_state: st.session_state.unavailability = {}
    if 'roster_dates' not in st.session_state: st.session_state.roster_dates = []

def reset_to_start():
    for key in list(st.session_state.keys()): del st.session_state[key]
    st.rerun()

# ==========================================
# 2. HARD-BLOCK ENGINE (Fixing Logic)
# ==========================================

class RosterEngine:
    def __init__(self, df):
        self.df = df
        self.load = defaultdict(int)

    def get_pool(self, role=None, gender=None, senior=None):
        pool = self.df.copy()
        if role:
            col_name = role.lower().replace(" crew", "").strip()
            if col_name in pool.columns:
                pool = pool[pool[col_name].astype(str).str.lower().str.contains('yes')]
            else: return []
        if gender: pool = pool[pool['male'].astype(str).str.lower().str.contains('yes')]
        if senior: pool = pool[pool['senior citizen'].astype(str).str.lower().str.contains('yes')]
        return pool['name'].tolist()

    def get_partner(self, name):
        row = self.df[self.df['name'] == name]
        if not row.empty and str(row['couple'].values[0]).strip():
            cid = row['couple'].values[0]
            partner = self.df[(self.df['couple'] == cid) & (self.df['name'] != name)]['name'].tolist()
            return partner[0] if partner else None
        return None

    def select_best(self, pool, unavailable, current_crew, force_tier=True):
        valid = [p for p in pool if p not in unavailable and p not in current_crew]
        if not valid: return ""
        
        # AGGRESSIVE EQUALIZATION: Tiered sorting by load
        if force_tier:
            min_load = min(self.load[p] for p in valid)
            valid = [p for p in valid if self.load[p] == min_load]

        random.shuffle(valid)
        return valid[0]

# ==========================================
# 3. UI NAVIGATION
# ==========================================

def nav_bar():
    c1, c2, _ = st.columns([1, 1, 4])
    if st.session_state.stage > 1:
        if c1.button("← Back"):
            st.session_state.stage -= 1
            st.rerun()
    if c2.button("🔄 Start Over"): reset_to_start()

def step_1():
    st.header("📅 Step 1: Ministry & Date Selection")
    st.session_state.ministry = st.selectbox("Select Ministry", list(MINISTRIES.keys()))
    col1, col2 = st.columns(2)
    year = col1.number_input("Year", value=date.today().year)
    all_months = list(calendar.month_name)[1:]
    curr_idx = date.today().month
    defaults = [all_months[(curr_idx + i) % 12] for i in range(3)]
    months = col2.multiselect("Months", all_months, default=defaults)
    
    if st.button("Generate Dates", type="primary"):
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
    nav_bar()

def step_2():
    st.header("⚙️ Step 2: Service Details (HC & Combined)")
    df = pd.DataFrame(st.session_state.roster_dates)
    edited = st.data_editor(df, use_container_width=True, num_rows="dynamic") # RESTORED COLUMNS
    if st.button("Next: Set Unavailability →"):
        st.session_state.roster_dates = edited.to_dict('records')
        st.session_state.stage = 3
        st.rerun()
    nav_bar()

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
    nav_bar()

def step_4(df_team):
    st.header("📋 Stage 4: Roster Dashboard")
    cfg = MINISTRIES[st.session_state.ministry]
    
    if st.session_state.master_roster_df is None:
        engine = RosterEngine(df_team)
        data = []
        for meta in st.session_state.roster_dates:
            d_str = str(meta['Date'])
            unav = [n for n, dts in st.session_state.unavailability.items() if d_str in dts]
            row = {"Date": pd.to_datetime(meta['Date']).strftime("%d-%b"), 
                   "Month": pd.to_datetime(meta['Date']).strftime("%B %Y"), 
                   "Notes": f"{'HC ' if meta['HC'] else ''}{'Combined' if meta['Combined'] else ''} {meta['Notes']}".strip()}
            crew = []

            if st.session_state.ministry == "Welcome Ministry":
                # 1. Lead First (Leaders cannot be members)
                tl = engine.select_best(engine.get_pool(role="team lead"), unav, crew)
                row["Team Lead"] = tl
                if tl: crew.append(tl)

                # 2. Member 1 (Male + Absolute Couple Check)
                m1 = ""
                m_pool = [p for p in engine.get_pool(gender="male") if p not in crew]
                for p in m_pool:
                    partner = engine.get_partner(p)
                    # Partner must be available AND not already the leader
                    if partner and partner not in unav and partner not in crew:
                        m1 = p; break
                
                if m1:
                    row["Member 1"] = m1; crew.append(m1); engine.load[m1] += 1
                    partner = engine.get_partner(m1)
                    row["Member 2"] = partner; crew.append(partner); engine.load[partner] += 1
                
                # 3. Fill remaining Members (max 4 if HC, else 3)
                max_slots = 4 if meta['HC'] else 3
                for i in range(1, max_slots + 1):
                    m_key = f"Member {i}"
                    if m_key in row or (meta['Combined'] and i > 2): continue # Combined limit
                    p = engine.select_best(engine.get_pool(), unav, crew)
                    row[m_key] = p
                    if p: crew.append(p); engine.load[p] += 1

            else: # Media Tech
                for r in cfg["roles"]: # RESTORED: Projectionist, Sound, etc.
                    p = engine.select_best(engine.get_pool(role=r), unav, crew)
                    row[r] = p
                    if p:
                        crew.append(p)
                        if r != "Stream Director": engine.load[p] += 1
                row["Cam 2"] = ""
                p_leads = [c for c in crew if any(pl in c.lower() for pl in cfg["primary_leads"])]
                row["Team Lead"] = p_leads[0] if p_leads else engine.select_best(engine.get_pool(role="team lead"), unav, crew)

            data.append(row)
        st.session_state.master_roster_df = pd.DataFrame(data)

    # UI Rendering
    m_df = st.session_state.master_roster_df
    roles = cfg["roles"] + cfg["extra_cols"]
    for m in m_df['Month'].unique():
        with st.expander(f"Edit {m}", expanded=True):
            sub = m_df[m_df['Month'] == m].copy().set_index("Date")
            view = sub[["Notes"] + roles].T
            edited = st.data_editor(view, use_container_width=True, key=f"e_{m}")
            if not edited.equals(view):
                for d_col in edited.columns:
                    for r_idx in edited.index: m_df.loc[m_df['Date'] == d_col, r_idx] = edited.at[r_idx, d_col]
                st.session_state.master_roster_df = m_df; st.rerun()

    # Live Stats (Leaders ignored in Total Load)
    st.markdown("---")
    st.subheader("📊 Live Load Statistics")
    n_map = {n.lower().strip(): n for n in df_team['name'].unique()}
    stats = defaultdict(lambda: {"Regular": 0, "Lead": 0})
    for _, r in m_df.iterrows():
        for col in roles:
            val = str(r.get(col, "")).lower().strip()
            if val in n_map:
                if col == "Team Lead": stats[n_map[val]]["Lead"] += 1
                elif col != "Stream Director": stats[n_map[val]]["Regular"] += 1
    
    if stats:
        st.table(pd.DataFrame([{"Name": k, "Shifts": v["Regular"], "Lead": v["Lead"], "Total": v["Regular"]} 
                               for k, v in stats.items()]).sort_values("Total", ascending=False))
    nav_bar()

def main():
    init_state()
    url = f"https://docs.google.com/spreadsheets/d/1jh6ScfqpHe7rRN1s-9NYPsm7hwqWWLjdLKTYThRRGUo/export?format=csv&gid={MINISTRIES[st.session_state.ministry]['gid']}"
    df_team = pd.read_csv(url).fillna("")
    df_team.columns = df_team.columns.str.strip().str.lower()
    names = sorted([n for n in df_team['name'].unique() if str(n).strip()])
    
    if st.session_state.stage == 1: step_1()
    elif st.session_state.stage == 2: step_2()
    elif st.session_state.stage == 3: step_3(names)
    elif st.session_state.stage == 4: step_4(df_team)

if __name__ == "__main__": main()
