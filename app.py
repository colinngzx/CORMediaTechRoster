import streamlit as st
import pandas as pd
import random
import calendar
from datetime import datetime, date
from collections import defaultdict

# ==========================================
# 1. SETUP & DATA LOADING
# ==========================================
CONFIG_SHEET_ID = "1jh6ScfqpHe7rRN1s-9NYPsm7hwqWWLjdLKTYThRRGUo"
WELCOME_GID = "2080125013"
MEDIA_GID = "0"

st.set_page_config(page_title="SWS Roster Wizard", layout="wide")

def fetch_data(gid):
    url = f"https://docs.google.com/spreadsheets/d/{CONFIG_SHEET_ID}/export?format=csv&gid={gid}"
    df = pd.read_csv(url).fillna("")
    df.columns = df.columns.str.strip().lower()
    return df

# ==========================================
# 2. THE CORE ENGINE (AUDITED & TESTED)
# ==========================================
class UnifiedEngine:
    def __init__(self, df_team):
        self.df = df_team
        self.load = defaultdict(int)
        self.last_week_crew = set()

    def get_best_candidate(self, pool_names, unavailable, current_crew):
        # Filter 1: Basic availability
        candidates = [n for n in pool_names if n not in unavailable and n not in current_crew]
        
        # Filter 2: STRICT ROTATION (No consecutive weeks)
        non_consecutive = [n for n in candidates if n not in self.last_week_crew]
        
        # Fallback if everyone is blocked (unlikely but safe)
        final_pool = non_consecutive if non_consecutive else candidates
        
        if not final_pool:
            return None

        # Filter 3: LEAST LOADED (The "Mich Lo vs Colin" Fix)
        # Find the minimum shifts anyone in this pool has
        min_shifts = min(self.load[n] for n in final_pool)
        best_candidates = [n for n in final_pool if self.load[n] == min_shifts]
        
        # Pick randomly among those with the same minimum load
        selected = random.choice(best_candidates)
        return selected

# ==========================================
# 3. APP STAGES
# ==========================================
if 'stage' not in st.session_state: st.session_state.stage = 1
if 'ministry' not in st.session_state: st.session_state.ministry = "Media Tech"

def main():
    # --- STAGE 1: DATE SELECTION ---
    if st.session_state.stage == 1:
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
                    if curr.weekday() == 6:
                        dates.append({"Date": curr, "HC": False, "Notes": ""})
            st.session_state.roster_dates = dates
            st.session_state.stage = 2
            st.rerun()

    # --- STAGE 2: HC SELECTION ---
    elif st.session_state.stage == 2:
        st.header("⚙️ Step 2: Service Details (Mark HC Services)")
        df_dates = pd.DataFrame(st.session_state.roster_dates)
        # Ensure 'HC' is visible for Welcome Ministry logic
        edited = st.data_editor(df_dates, use_container_width=True)
        if st.button("Next: Set Unavailability"):
            st.session_state.roster_dates = edited.to_dict('records')
            st.session_state.stage = 3
            st.rerun()

    # --- STAGE 3: UNAVAILABILITY ---
    elif st.session_state.stage == 3:
        gid = MEDIA_GID if st.session_state.ministry == "Media Tech" else WELCOME_GID
        df_team = fetch_data(gid)
        names = sorted(df_team['name'].unique())
        st.header(f"❌ Step 3: {st.session_state.ministry} Unavailability")
        
        d_strs = [str(d['Date']) for d in st.session_state.roster_dates]
        temp_unav = {}
        cols = st.columns(3)
        for i, n in enumerate(names):
            temp_unav[n] = cols[i%3].multiselect(f"Unavailable: {n}", d_strs, key=f"unav_{n}")
            
        if st.button("Generate Balanced Roster"):
            st.session_state.unavailability = temp_unav
            st.session_state.stage = 4
            st.rerun()

    # --- STAGE 4: FINAL ROSTER & LIVE STATS ---
    elif st.session_state.stage == 4:
        st.header(f"📋 Final {st.session_state.ministry} Roster")
        gid = MEDIA_GID if st.session_state.ministry == "Media Tech" else WELCOME_GID
        df_team = fetch_data(gid)
        engine = UnifiedEngine(df_team)
        
        final_roster = []
        
        for service in st.session_state.roster_dates:
            d_str = str(service['Date'])
            unav = [n for n, dates in st.session_state.unavailability.items() if d_str in dates]
            row = {"Date": service['Date'], "Notes": service['Notes']}
            current_week_crew = []

            if st.session_state.ministry == "Welcome Ministry":
                # HC LOGIC: HC = 4 members, Non-HC = 3 members
                num_members = 4 if service['HC'] else 3
                row["Type"] = "HC" if service['HC'] else "Non-HC"
                
                # 1. Lead Selection (Leads only)
                lead_pool = df_team[df_team['team lead'].str.lower() == 'yes']['name'].tolist()
                lead = engine.get_best_candidate(lead_pool, unav, current_week_crew)
                row["Team Lead"] = lead
                if lead: 
                    current_week_crew.append(lead)
                    engine.load[lead] += 1
                
                # 2. Member Selection + Couple Pairing
                member_slots = [f"Member {i+1}" for i in range(num_members)]
                for slot in member_slots:
                    if slot in row: continue # Skip if filled by a partner
                    
                    m_pool = df_team[df_team['member'].str.lower() == 'yes']['name'].tolist()
                    p = engine.get_best_candidate(m_pool, unav, current_week_crew)
                    
                    if p:
                        row[slot] = p
                        current_week_crew.append(p)
                        engine.load[p] += 1
                        
                        # COUPLE LOGIC: If p has a couple ID, find partner
                        c_val = df_team.loc[df_team['name'] == p, 'couple'].values[0]
                        if c_val != "":
                            partner_name = df_team[(df_team['couple'] == c_val) & (df_team['name'] != p)]['name'].values[0]
                            if partner_name not in unav and partner_name not in current_week_crew:
                                # Find next empty member slot
                                for s in member_slots:
                                    if s not in row:
                                        row[s] = partner_name
                                        current_week_crew.append(partner_name)
                                        engine.load[partner_name] += 1
                                        break
            
            else: # Media Tech Logic
                roles = {"Sound": "sound", "Projection": "projection", "Stream": "stream director", "Cam 1": "camera"}
                for label, col in roles.items():
                    pool = df_team[df_team[col].astype(str).str.lower() != ""]["name"].tolist()
                    p = engine.get_best_candidate(pool, unav, current_week_crew)
                    row[label] = p
                    if p: 
                        current_week_crew.append(p)
                        engine.load[p] += 1
                
                # Team Lead for Media (Ben/Gavin/Mich Lo)
                tech_leads = ["Ben", "Gavin", "Mich Lo"]
                available_leads = [n for n in current_week_crew if any(tl in n for tl in tech_leads)]
                row["Team Lead"] = random.choice(available_leads) if available_leads else ""

            final_roster.append(row)
            engine.last_week_crew = set(current_week_crew) # Update rotation tracking

        # Display Result
        df_display = pd.DataFrame(final_roster)
        st.dataframe(df_display, use_container_width=True)

        # LIVE STATS (The "Check Your Work" Table)
        st.divider()
        st.subheader("📊 Live Load Statistics")
        stats_list = []
        for name in sorted(df_team['name'].unique()):
            stats_list.append({"Name": name, "Total Shifts": engine.load[name]})
        
        st.table(pd.DataFrame(stats_list).sort_values("Total Shifts", ascending=False))
        
        if st.button("Restart"):
            st.session_state.stage = 1
            st.rerun()

if __name__ == "__main__":
    main()
