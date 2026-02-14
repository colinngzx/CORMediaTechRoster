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
    # Persistent memory for mixing
    if 'pairing_history' not in st.session_state: st.session_state.pairing_history = defaultdict(set)
    if 'role_history' not in st.session_state: st.session_state.role_history = defaultdict(list)

def reset_to_start():
    for key in list(st.session_state.keys()):
        del st.session_state[key]
    st.rerun()

# ==========================================
# 2. UPDATED ENGINE (Equalization & Mixing)
# ==========================================

class RosterEngine:
    def __init__(self, df, ministry):
        self.df = df
        self.ministry = ministry
        self.load = defaultdict(int)
        self.prev_week_crew = []

    def get_pool(self, role=None, gender=None, senior=None):
        pool = self.df.copy()
        # Robust column mapping to prevent KeyErrors
        if role: 
            col = role.lower().replace(" crew", "")
            if col in pool.columns:
                pool = pool[pool[col].astype(str).str.lower().str.contains('yes')]
        if gender: pool = pool[pool['male'].astype(str).str.lower().str.contains('yes')]
        if senior: pool = pool[pool['senior citizen'].astype(str).str.lower().str.contains('yes')]
        return pool['name'].tolist()

    def select_best(self, pool, unavailable, current_crew, role_pref=None):
        valid = [p for p in pool if p not in unavailable and p not in current_crew]
        if not valid: return ""

        # Weighting Logic for Equalization & Mixing
        def get_weight(name):
            # 1. Base Load (Priority 1: Jenny vs Happy Sum)
            weight = self.load[name] * 10 
            # 2. Role Rotation (Media Tech)
            if role_pref and name in st.session_state.role_history and st.session_state.role_history[name][-1:] == [role_pref]:
                weight += 5
            # 3. Social Mixing (Avoid same pairings)
            for partner in current_crew:
                if partner in st.session_state.pairing_history[name]:
                    weight += 2
            # 4. Weekly Rest
            if name in self.prev_week_crew:
                weight += 3
            return weight

        # Shuffle to remove alphabetical bias
        random.shuffle(valid)
        valid.sort(key=get_weight)
        
        pick = valid[0]
        self.load[pick] += 1
        if role_pref: st.session_state.role_history[pick].append(role_pref)
        return pick

    def get_partner(self, name):
        row = self.df[self.df['name'] == name]
        if not row.empty and str(row['couple'].values[0]).strip():
            cid = row['couple'].values[0]
            partner = self.df[(self.df['couple'] == cid) & (self.df['name'] != name)]['name'].tolist()
            return partner[0] if partner else None
        return None

# ==========================================
# 3. UI STEPS
# ==========================================

def nav_buttons():
    col1, col2, _ = st.columns([1, 1, 4])
    if st.session_state.stage > 1:
        if col1.button("← Back"):
            st.session_state.stage -= 1
            st.rerun()
    if col2.button("🔄 Start Over"):
        reset_to_start()

def step_1():
    st.header("📅 Step 1: Ministry & Date Selection")
    st.session_state.ministry = st.selectbox("Select Ministry", list(MINISTRIES.keys()), 
                                            index=list(MINISTRIES.keys()).index(st.session_state.ministry))

    col1, col2 = st.columns(2)
    year = col1.number_input("Year", value=date.today().year)
    
    # Auto-select next 3 months
    current_date = date.today()
    all_months = list(calendar.month_name)[1:]
    default_months = []
    for i in range(1, 4):
        future = current_date + timedelta(days=32 * i)
        default_months.append(all_months[future.month - 1])
    
    months = col2.multiselect("Months", all_months, default=default_months)
    
    if st.button("Generate Dates", type="primary"):
        month_map = {m: i for i, m in enumerate(calendar.month_name) if m}
        dates = []
        for m in months:
            _, days = calendar.monthrange(year, month_map[m])
            for d in range(1, days + 1):
                curr = date(year, month_map[m], d)
                if curr.weekday() == 6: dates.append({"Date": curr, "HC": False, "Combined": False, "Notes": ""})
        st.session_state.roster_dates = dates
        st.session_state.stage = 2
        st.rerun()
    nav_buttons()

def step_2():
    st.header("⚙️ Step 2: Service Details")
    st.info("You can add/remove dates by right-clicking rows in the table.")
    df = pd.DataFrame(st.session_state.roster_dates)
    # Enable dynamic rows
    edited = st.data_editor(df, use_container_width=True, num_rows="dynamic")
    if st.button("Next: Set Unavailability →"):
        st.session_state.roster_dates = edited.to_dict('records')
        st.session_state.stage = 3
        st.rerun()
    nav_buttons()

def step_3(names):
    st.header("❌ Step 3: Unavailability")
    date_strs = [str(d['Date']) for d in st.session_state.roster_dates]
    with st.form("unav"):
        cols = st.columns(3)
        temp = {}
        for i, n in enumerate(names):
            with cols[i%3]: temp[n] = st.multiselect(n, date_strs)
        if st.form_submit_button("Generate Roster"):
            st.session_state.unavailability = temp
            st.session_state.master_roster_df = None
            st.session_state.stage = 4
            st.rerun()
    nav_buttons()

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
                # MEMBER 1: Male
                m1 = engine.select_best(engine.get_pool(gender="male"), unav, crew)
                row["Member 1"] = m1; crew.append(m1) if m1 else None
                # Partner Logic
                pt = engine.get_partner(m1) if m1 else None
                if pt and pt not in unav: row["Member 2"] = pt; crew.append(pt)
                # Scaling logic
                slots = ["Member 2", "Member 3", "Member 4"] if meta['HC'] else ["Member 2", "Member 3"]
                for s in slots:
                    if s in row: continue
                    # Forced Senior Citizen logic
                    is_last = (s == slots[-1])
                    has_senior = any('yes' in str(df_team[df_team['name']==c]['senior citizen'].values[0]).lower() for c in crew if c)
                    p = ""
                    if is_last and not has_senior:
                        p = engine.select_best(engine.get_pool(senior=True), unav, crew)
                    if not p: p = engine.select_best(engine.get_pool(), unav, crew)
                    row[s] = p; crew.append(p) if p else None
                row["Team Lead"] = engine.select_best(engine.get_pool(role="team lead"), unav, crew)
            else:
                for r in cfg["roles"]:
                    p = engine.select_best(engine.get_pool(role=r), unav, crew, role_pref=r)
                    row[r] = p; crew.append(p) if p else None
                row["Cam 2"] = ""
                leads = [c for c in crew if any(pl in c.lower() for pl in cfg["primary_leads"])]
                row["Team Lead"] = leads[0] if leads else engine.select_best(engine.get_pool(role="team lead"), unav, crew)
            
            # Record pairings
            for c in crew:
                if c: st.session_state.pairing_history[c].update([x for x in crew if x and x != c])
            data.append(row)
            engine.prev_week_crew = crew
        st.session_state.master_roster_df = pd.DataFrame(data)

    # Transposed Editor
    m_df = st.session_state.master_roster_df
    display_cols = ["Notes"] + cfg["roles"] + cfg["extra_cols"]
    for m in m_df['Month'].unique():
        with st.expander(f"Edit {m}", expanded=True):
            sub = m_df[m_df['Month'] == m].copy().set_index("Date")
            view = sub[display_cols].T
            edited = st.data_editor(view, use_container_width=True, key=f"ed_{m}")
            if not edited.equals(view):
                for d_col in edited.columns:
                    for r_idx in edited.index:
                        m_df.loc[m_df['Date'] == d_col, r_idx] = edited.at[r_idx, d_col]
                st.session_state.master_roster_df = m_df
                st.rerun()

    # Case-Insensitive Stats
    st.markdown("---")
    st.subheader("📊 Live Load Statistics")
    n_map = {n.lower().strip(): n for n in df_team['name'].unique()}
    stats = defaultdict(lambda: {"Tech": 0, "Lead": 0})
    for _, r in m_df.iterrows():
        for col in display_cols:
            val = str(r.get(col, "")).lower().strip()
            if val in n_map:
                if col == "Team Lead": stats[n_map[val]]["Lead"] += 1
                else: stats[n_map[val]]["Tech"] += 1
    if stats:
        st.table(pd.DataFrame([{"Name": k, "Shifts": v["Tech"], "Lead": v["Lead"], "Total": v["Tech"]+v["Lead"]} 
                               for k, v in stats.items()]).sort_values("Total", ascending=False))
    nav_buttons()

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
