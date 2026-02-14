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
    if 'history' not in st.session_state: st.session_state.history = defaultdict(list) # Social Mixing

def reset_state():
    st.session_state.master_roster_df = None
    st.session_state.unavailability = {}
    st.session_state.history = defaultdict(list)

# ==========================================
# 2. CORE LOGIC ENGINE
# ==========================================

class RosterEngine:
    def __init__(self, df, ministry):
        self.df = df
        self.ministry = ministry
        self.load = defaultdict(int)
        self.prev_crew = []
        self.role_history = defaultdict(str) # For Media Tech cross-training

    def get_pool(self, role=None, gender=None, senior=None):
        pool = self.df.copy()
        if role: pool = pool[pool[role.lower().replace(" crew","")].astype(str).str.lower().str.contains('yes')]
        if gender: pool = pool[pool['male'].astype(str).str.lower().str.contains('yes')]
        if senior: pool = pool[pool['senior citizen'].astype(str).str.lower().str.contains('yes')]
        return pool['name'].tolist()

    def select_best(self, pool, unavailable, current_crew):
        # 1. Filter out unavailable and double-booked
        valid = [p for p in pool if p not in unavailable and p not in current_crew]
        
        # 2. Weekly Rest (try to avoid consecutive weeks)
        non_consecutive = [p for p in valid if p not in self.prev_crew]
        candidates = non_consecutive if non_consecutive else valid
        
        if not candidates: return ""

        # 3. Social Mixing & Load Balancing
        # Shuffling first removes alphabetical bias
        random.shuffle(candidates)
        
        def calculate_weight(name):
            weight = self.load[name]
            # Penalty if they have worked with anyone in current_crew before
            for member in current_crew:
                if member in st.session_state.history[name]:
                    weight += 0.5 
            return weight

        candidates.sort(key=calculate_weight)
        pick = candidates[0]
        self.load[pick] += 1
        return pick

    def get_partner(self, name):
        row = self.df[self.df['name'] == name]
        if not row.empty and str(row['couple'].values[0]).strip():
            cid = row['couple'].values[0]
            partner = self.df[(self.df['couple'] == cid) & (self.df['name'] != name)]['name'].tolist()
            return partner[0] if partner else None
        return None

# ==========================================
# 3. UI STAGES
# ==========================================

def step_1():
    st.header("📅 Step 1: Ministry & Date Selection")
    new_min = st.selectbox("Select Ministry", list(MINISTRIES.keys()))
    if new_min != st.session_state.ministry:
        st.session_state.ministry = new_min
        reset_state()

    col1, col2 = st.columns(2)
    year = col1.number_input("Year", value=date.today().year)
    
    # --- AUTO SELECT NEXT 3 MONTHS ---
    current_month_idx = date.today().month # Jan=1, Feb=2...
    all_months = list(calendar.month_name)[1:]
    default_indices = [(current_month_idx + i) % 12 for i in range(3)]
    default_months = [all_months[i] for i in default_indices]
    
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

def step_4(df_team):
    st.header("📋 Stage 4: Roster Dashboard")
    cfg = MINISTRIES[st.session_state.ministry]
    
    if st.session_state.master_roster_df is None:
        engine = RosterEngine(df_team, st.session_state.ministry)
        data = []
        for meta in st.session_state.roster_dates:
            d_str = meta['Date'].strftime("%Y-%m-%d")
            unav = [n for n, dts in st.session_state.unavailability.items() if d_str in dts]
            row = {"Date": meta['Date'].strftime("%d-%b"), "Month": meta['Date'].strftime("%B %Y"), 
                   "Notes": f"{'HC ' if meta['HC'] else ''}{'Combined' if meta['Combined'] else ''}".strip()}
            crew = []

            if st.session_state.ministry == "Welcome Ministry":
                # MEMBER 1: Always Male
                m1 = engine.select_best(engine.get_pool(gender="male"), unav, crew)
                row["Member 1"] = m1
                if m1: crew.append(m1)

                # Couple Logic: Check M1 partner
                p_m1 = engine.get_partner(m1) if m1 else None
                if p_m1 and p_m1 not in unav:
                    row["Member 2"] = p_m1
                    crew.append(p_m1)

                # Fill slots (HC=4, Non-HC=3)
                max_members = 4 if meta['HC'] else 3
                for i in range(2, max_members + 1):
                    r_name = f"Member {i}"
                    if r_name in row: continue
                    
                    # Senior Citizen Logic: If we are at the last slot and no senior yet, force a senior
                    has_senior = any('yes' in str(df_team[df_team['name']==c]['senior citizen'].values[0]).lower() for c in crew if c)
                    if i == max_members and not has_senior:
                        p = engine.select_best(engine.get_pool(senior=True), unav, crew)
                        if not p: p = engine.select_best(engine.get_pool(), unav, crew) # Bypass if none
                    else:
                        p = engine.select_best(engine.get_pool(), unav, crew)
                    
                    row[r_name] = p
                    if p: crew.append(p)
                
                # Team Lead
                row["Team Lead"] = engine.select_best(engine.get_pool(role="team lead"), unav, crew)

            else: # Media Tech
                for r in cfg["roles"]:
                    # Cross-training: prioritize candidates not in their previous role
                    p = engine.select_best(engine.get_pool(role=r), unav, crew)
                    row[r] = p
                    if p: crew.append(p)
                row["Cam 2"] = ""
                # Priority leads check
                leads = [c for c in crew if any(pl in c.lower() for pl in cfg["primary_leads"])]
                row["Team Lead"] = leads[0] if leads else engine.select_best(engine.get_pool(role="team lead"), unav, crew)
            
            # Record social mixing history
            for c in crew:
                st.session_state.history[c].extend([x for x in crew if x != c])
            data.append(row)
            engine.prev_crew = crew
        
        st.session_state.master_roster_df = pd.DataFrame(data)

    # --- UI TRANSPOSED EDITOR ---
    master_df = st.session_state.master_roster_df
    roles_to_show = cfg["roles"] + cfg["extra_cols"]
    for m in master_df['Month'].unique():
        with st.expander(f"Edit {m}", expanded=True):
            sub = master_df[master_df['Month'] == m].copy().set_index("Date")
            view = sub[["Notes"] + roles_to_show].T
            edited = st.data_editor(view, use_container_width=True, key=f"ed_{m}")
            if not edited.equals(view):
                for d_col in edited.columns:
                    for r_idx in edited.index:
                        master_df.loc[master_df['Date'] == d_col, r_idx] = edited.at[r_idx, d_col]
                st.session_state.master_roster_df = master_df
                st.rerun()

    # --- CASE-INSENSITIVE LIVE STATS ---
    st.markdown("---")
    st.subheader("📊 Live Load Statistics")
    names_map = {n.lower().strip(): n for n in df_team['name'].unique()}
    stats = defaultdict(lambda: {"Tech": 0, "Lead": 0})
    for _, r in master_df.iterrows():
        for col in roles_to_show:
            val = str(r.get(col, "")).lower().strip()
            if val in names_map:
                real_name = names_map[val]
                if col == "Team Lead": stats[real_name]["Lead"] += 1
                else: stats[real_name]["Tech"] += 1
    
    if stats:
        st.table(pd.DataFrame([{"Name": k, "Shifts": v["Tech"], "Lead": v["Lead"], "Total": v["Tech"]+v["Lead"]} 
                               for k, v in stats.items()]).sort_values("Total", ascending=False))

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
