import streamlit as st
import pandas as pd
import random
import calendar
from datetime import datetime, date, timedelta
from collections import defaultdict

# ==========================================
# 1. CONFIGURATION & STATE
# ==========================================

MINISTRIES = {
    "Media Tech": {
        "gid": "0",
        "roles": ["Sound Crew", "Projectionist", "Stream Director", "Cam 1"],
        "extra_cols": ["Cam 2", "Team Lead"],
        "primary_leads": ["gavin", "ben", "mich lo"],
        "stats_exclude": ["Stream Director"] # NEW: Exclude from load count
    },
    "Welcome Ministry": {
        "gid": "2080125013",
        "roles": ["Member 1", "Member 2", "Member 3", "Member 4"],
        "extra_cols": ["Team Lead"],
        "primary_leads": [],
        "stats_exclude": []
    }
}

def init_state():
    if 'stage' not in st.session_state: st.session_state.stage = 1
    if 'ministry' not in st.session_state: st.session_state.ministry = "Media Tech"
    if 'master_roster_df' not in st.session_state: st.session_state.master_roster_df = None
    if 'unavailability' not in st.session_state: st.session_state.unavailability = {}
    if 'roster_dates' not in st.session_state: st.session_state.roster_dates = []
    if 'pairing_history' not in st.session_state: st.session_state.pairing_history = defaultdict(set)

def reset_to_start():
    for key in list(st.session_state.keys()): del st.session_state[key]
    st.rerun()

# ==========================================
# 2. UPDATED ENGINE (Strong Equalization)
# ==========================================

class RosterEngine:
    def __init__(self, df, ministry_name):
        self.df = df
        self.ministry_name = ministry_name
        self.load = defaultdict(int)
        self.prev_week_crew = []

    def get_pool(self, role=None, gender=None, senior=None):
        pool = self.df.copy()
        if role: 
            col = role.lower().replace(" crew", "")
            if col in pool.columns: pool = pool[pool[col].astype(str).str.lower().str.contains('yes')]
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

    def select_best(self, pool, unavailable, current_crew, force_couple=False):
        valid = [p for p in pool if p not in unavailable and p not in current_crew]
        
        # STICKY COUPLE LOGIC: If picking someone with a partner, partner MUST be available
        if force_couple:
            refined = []
            for p in valid:
                partner = self.get_partner(p)
                if partner and (partner in unavailable or partner in current_crew): continue
                refined.append(p)
            valid = refined

        if not valid: return ""

        # Weighting: Priority 1 is Shift Equalization (Multiplied by 100 for extreme bias)
        def get_weight(name):
            return (self.load[name] * 100) + (10 if name in self.prev_week_crew else 0)

        random.shuffle(valid) # Remove alphabetical bias
        valid.sort(key=get_weight)
        
        pick = valid[0]
        # Only increment load if not excluded (e.g., Stream Director)
        return pick

# ==========================================
# 3. UI NAVIGATION & STAGES
# ==========================================

def nav_bar():
    c1, c2, _ = st.columns([1, 1, 4])
    if st.session_state.stage > 1:
        if c1.button("← Back", use_container_width=True):
            st.session_state.stage -= 1
            st.rerun()
    if c2.button("🔄 Start Over", use_container_width=True): reset_to_start()

def step_1():
    st.header("📅 Step 1: Ministry & Date Selection")
    st.session_state.ministry = st.selectbox("Select Ministry", list(MINISTRIES.keys()))
    
    col1, col2 = st.columns(2)
    year = col1.number_input("Year", value=date.today().year)
    
    # Auto-select next 3 months (Mar, Apr, May for Feb 14)
    all_months = list(calendar.month_name)[1:]
    current_idx = date.today().month # Feb = 2
    default_indices = [(current_idx + i) % 12 for i in range(3)]
    default_months = [all_months[i] for i in default_indices]
    
    months = col2.multiselect("Months", all_months, default=default_months)
    
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
    st.header("⚙️ Step 2: Service Details")
    st.info("Right-click rows to add/remove specific service dates.")
    df = pd.DataFrame(st.session_state.roster_dates)
    edited = st.data_editor(df, use_container_width=True, num_rows="dynamic")
    if st.button("Next: Set Unavailability →"):
        st.session_state.roster_dates = edited.to_dict('records')
        st.session_state.stage = 3
        st.rerun()
    nav_bar()

def step_3(names):
    st.header("❌ Step 3: Unavailability")
    d_strs = [str(d['Date']) for d in st.session_state.roster_dates]
    with st.form("unav_form"):
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
        engine = RosterEngine(df_team, st.session_state.ministry)
        data = []
        for meta in st.session_state.roster_dates:
            d_str = str(meta['Date'])
            unav = [n for n, dts in st.session_state.unavailability.items() if d_str in dts]
            row = {"Date": pd.to_datetime(meta['Date']).strftime("%d-%b"), "Month": pd.to_datetime(meta['Date']).strftime("%B %Y"), 
                   "Notes": f"{'HC ' if meta['HC'] else ''}{'Combined' if meta['Combined'] else ''}".strip()}
            crew = []

            if st.session_state.ministry == "Welcome Ministry":
                # MEMBER 1 (Male + Force Couple check)
                m1 = engine.select_best(engine.get_pool(gender="male"), unav, crew, force_couple=True)
                row["Member 1"] = m1; crew.append(m1) if m1 else None
                engine.load[m1] += 1 if m1 else 0

                # Auto-Assign Partner to Member 2
                pt = engine.get_partner(m1) if m1 else None
                if pt:
                    row["Member 2"] = pt; crew.append(pt)
                    engine.load[pt] += 1

                # Rest of the members (scaling)
                max_s = 4 if meta['HC'] else 3
                for i in range(2, max_s + 1):
                    r_name = f"Member {i}"
                    if r_name in row: continue
                    # Senior Rule
                    is_last = (i == max_s)
                    has_sr = any('yes' in str(df_team[df_team['name']==c]['senior citizen'].values[0]).lower() for c in crew if c)
                    p = engine.select_best(engine.get_pool(senior=True), unav, crew) if (is_last and not has_sr) else ""
                    if not p: p = engine.select_best(engine.get_pool(), unav, crew)
                    row[r_name] = p; crew.append(p) if p else None
                    engine.load[p] += 1 if p else 0
                
                tl = engine.select_best(engine.get_pool(role="team lead"), unav, crew)
                row["Team Lead"] = tl; engine.load[tl] += 1 if tl else 0
            else:
                for r in cfg["roles"]:
                    p = engine.select_best(engine.get_pool(role=r), unav, crew)
                    row[r] = p; crew.append(p) if p else None
                    # EXCLUDE "Stream Director" from load count
                    if r not in cfg["stats_exclude"]: engine.load[p] += 1 if p else 0
                
                row["Cam 2"] = ""
                leads = [c for c in crew if any(pl in c.lower() for pl in cfg["primary_leads"])]
                tl = leads[0] if leads else engine.select_best(engine.get_pool(role="team lead"), unav, crew)
                row["Team Lead"] = tl; engine.load[tl] += 1 if tl else 0
            
            data.append(row)
            engine.prev_week_crew = crew
        st.session_state.master_roster_df = pd.DataFrame(data)

    # --- UI RENDERING (Transposed Editor) ---
    m_df = st.session_state.master_roster_df
    display_roles = cfg["roles"] + cfg["extra_cols"]
    for m in m_df['Month'].unique():
        with st.expander(f"Edit {m}", expanded=True):
            sub = m_df[m_df['Month'] == m].copy().set_index("Date")
            view = sub[["Notes"] + display_roles].T
            edited = st.data_editor(view, use_container_width=True, key=f"editor_{m}")
            if not edited.equals(view):
                for d_col in edited.columns:
                    for r_idx in edited.index: m_df.loc[m_df['Date'] == d_col, r_idx] = edited.at[r_idx, d_col]
                st.session_state.master_roster_df = m_df; st.rerun()

    # --- CASE-INSENSITIVE LIVE STATS (With Exclusions) ---
    st.markdown("---")
    st.subheader("📊 Live Load Statistics")
    n_map = {n.lower().strip(): n for n in df_team['name'].unique()}
    stats = defaultdict(lambda: {"Regular": 0, "Lead": 0})
    for _, r in m_df.iterrows():
        for col in display_roles:
            val = str(r.get(col, "")).lower().strip()
            if val in n_map and col not in cfg["stats_exclude"]:
                if col == "Team Lead": stats[n_map[val]]["Lead"] += 1
                else: stats[n_map[val]]["Regular"] += 1
    
    if stats:
        st.table(pd.DataFrame([{"Name": k, "Shifts": v["Regular"], "Lead": v["Lead"], "Total": v["Regular"]+v["Lead"]} 
                               for k, v in stats.items()]).sort_values("Total", ascending=False))
    nav_bar()

# ==========================================
# 4. MAIN
# ==========================================

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
