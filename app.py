import streamlit as st
import pandas as pd
import random
import calendar
from datetime import date
from collections import defaultdict

# ==========================================
# 1. CONFIGURATION
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

# ==========================================
# 2. STATE MANAGEMENT
# ==========================================

def init_state():
    if 'stage' not in st.session_state: st.session_state.stage = 1
    if 'ministry' not in st.session_state: st.session_state.ministry = "Media Tech"
    if 'master_roster_df' not in st.session_state: st.session_state.master_roster_df = None
    if 'unavailability' not in st.session_state: st.session_state.unavailability = {}

def reset_state():
    st.session_state.master_roster_df = None
    st.session_state.unavailability = {}

# ==========================================
# 3. CORE ENGINE
# ==========================================

class RosterEngine:
    def __init__(self, df, ministry):
        self.df = df
        self.ministry = ministry
        self.cfg = MINISTRIES[ministry]
        self.load = defaultdict(int)
        self.prev_crew = []

    def get_pool(self, role_filter=None, gender_filter=None):
        pool = self.df.copy()
        if role_filter: pool = pool[pool[role_filter].astype(str).str.lower().str.contains('yes')]
        if gender_filter: pool = pool[pool[gender_filter].astype(str).str.lower().str.contains('yes')]
        return pool['name'].tolist()

    def select_best(self, pool, unavailable, current_crew):
        valid = [p for p in pool if p not in unavailable and p not in current_crew and p not in self.prev_crew]
        if not valid: valid = [p for p in pool if p not in unavailable and p not in current_crew]
        if not valid: return ""
        
        valid.sort(key=lambda x: (self.load[x], random.uniform(0, 1)))
        pick = valid[0]
        self.load[pick] += 1
        return pick

    def get_partner(self, name):
        couple_val = self.df[self.df['name'] == name]['couple'].values
        if len(couple_val) > 0 and str(couple_val[0]).strip() != "":
            couple_id = couple_val[0]
            partner = self.df[(self.df['couple'] == couple_id) & (self.df['name'] != name)]['name'].tolist()
            return partner[0] if partner else None
        return None

# ==========================================
# 4. UI STAGES
# ==========================================

def step_1():
    st.header("📅 Step 1: Ministry & Date Selection")
    new_min = st.selectbox("Select Ministry", list(MINISTRIES.keys()))
    if new_min != st.session_state.ministry:
        st.session_state.ministry = new_min
        reset_state()

    col1, col2 = st.columns(2)
    year = col1.number_input("Year", value=2026)
    months = col2.multiselect("Months", list(calendar.month_name)[1:], default=["January"])
    
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
    # Included 'Combined' as requested
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
    st.header("📋 Step 4: Roster Dashboard")
    cfg = MINISTRIES[st.session_state.ministry]
    
    if st.session_state.master_roster_df is None:
        engine = RosterEngine(df_team, st.session_state.ministry)
        data = []
        for meta in st.session_state.roster_dates:
            d_str = meta['Date'].strftime("%Y-%m-%d")
            unav = [n for n, dates in st.session_state.unavailability.items() if d_str in dates]
            note = f"{'HC ' if meta['HC'] else ''}{'Combined' if meta['Combined'] else ''}".strip()
            row = {"Date": meta['Date'].strftime("%d-%b"), "Month": meta['Date'].strftime("%B %Y"), "Notes": note}
            crew = []

            if st.session_state.ministry == "Welcome Ministry":
                # Constraint: Member 1 is ALWAYS Male
                male_pool = engine.get_pool(role_filter="member", gender_filter="male")
                m1 = engine.select_best(male_pool, unav, crew)
                row["Member 1"] = m1
                if m1: crew.append(m1)

                # Couple Logic: If M1 has a partner, they take Member 2
                partner = engine.get_partner(m1) if m1 else None
                if partner and partner not in unav:
                    row["Member 2"] = partner
                    crew.append(partner)
                
                # Fill remaining members
                for r in ["Member 2", "Member 3", "Member 4"]:
                    if r in row: continue
                    p = engine.select_best(engine.get_pool("member"), unav, crew)
                    row[r] = p
                    if p: 
                        crew.append(p)
                        # Check if this new person has a partner to add to the NEXT slot
                        pt = engine.get_partner(p)
                        if pt and pt not in unav and pt not in crew:
                            # We'll try to fit them in the next available member slot if possible
                            pass 

                # Team Lead
                row["Team Lead"] = engine.select_best(engine.get_pool("team lead"), unav, crew)
            else:
                # Media Tech Standard Logic
                for r in cfg["roles"]:
                    row[r] = engine.select_best(engine.get_pool(r.lower().replace(" crew","")), unav, crew)
                    if row[r]: crew.append(row[r])
                row["Cam 2"] = ""
                # Priority Lead logic
                lead_pool = [p for p in crew if any(pl in p.lower() for pl in cfg["primary_leads"])]
                row["Team Lead"] = lead_pool[0] if lead_pool else engine.select_best(engine.get_pool("team lead"), unav, crew)
            
            data.append(row)
            engine.prev_crew = crew
        st.session_state.master_roster_df = pd.DataFrame(data)

    # UI Editor
    master_df = st.session_state.master_roster_df
    display_cols = ["Notes"] + cfg["roles"] + cfg["extra_cols"]
    for m in master_df['Month'].unique():
        with st.expander(f"Edit {m}", expanded=True):
            sub = master_df[master_df['Month'] == m].copy().set_index("Date")
            edited = st.data_editor(sub[display_cols].T, use_container_width=True, key=f"ed_{m}")
            if not edited.equals(sub[display_cols].T):
                for d_col in edited.columns:
                    for r_idx in edited.index:
                        master_df.loc[master_df['Date'] == d_col, r_idx] = edited.at[r_idx, d_col]
                st.session_state.master_roster_df = master_df
                st.rerun()

    # --- LIVE LOAD STATISTICS (Case-Insensitive) ---
    st.markdown("---")
    st.subheader("📊 Live Load Statistics")
    canonical = {n.lower().strip(): n for n in df_team['name'].unique()}
    stats = defaultdict(lambda: {"Tech": 0, "Lead": 0})
    for _, r in master_df.iterrows():
        for col in display_cols:
            name = str(r.get(col, "")).lower().strip()
            if name in canonical:
                if col == "Team Lead": stats[canonical[name]]["Lead"] += 1
                else: stats[canonical[name]]["Tech"] += 1
    
    if stats:
        stat_data = [{"Name": n, "Shifts": d["Tech"], "Lead": d["Lead"], "Total": d["Tech"]+d["Lead"]} for n, d in stats.items()]
        st.table(pd.DataFrame(stat_data).sort_values("Total", ascending=False))

# ==========================================
# 5. MAIN
# ==========================================

def main():
    init_state()
    sheet_id = "1jh6ScfqpHe7rRN1s-9NYPsm7hwqWWLjdLKTYThRRGUo"
    url = f"https://docs.google.com/spreadsheets/d/{sheet_id}/export?format=csv&gid={MINISTRIES[st.session_state.ministry]['gid']}"
    df_team = pd.read_csv(url).fillna("")
    df_team.columns = df_team.columns.str.strip().str.lower()
    
    names = sorted([n for n in df_team['name'].unique() if str(n).strip()])
    if st.session_state.stage == 1: step_1()
    elif st.session_state.stage == 2: step_2()
    elif st.session_state.stage == 3: step_3(names)
    elif st.session_state.stage == 4: step_4(df_team)

if __name__ == "__main__": main()
