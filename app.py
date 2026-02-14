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
# 2. THE CORE ENGINE (FIXED ROTATION)
# ==========================================
class RosterEngine:
    def __init__(self, df_team):
        self.df = df_team
        self.load = defaultdict(int)
        self.prev_week_crew = set()

    def get_best_candidate(self, pool_names, unavailable, current_crew):
        # 1. Filter out unavailable and those already rostered today
        candidates = [n for n in pool_names if n not in unavailable and n not in current_crew]
        
        # 2. Strict Rotation: No back-to-back weeks if possible
        rotating_pool = [n for n in candidates if n not in self.prev_week_crew]
        final_pool = rotating_pool if rotating_pool else candidates # Fallback if pool is empty
        
        if not final_pool:
            return None

        # 3. Balancing: Select person with the absolute lowest shift count
        min_load = min(self.load[n] for n in final_pool)
        best_candidates = [n for n in final_pool if self.load[n] == min_load]
        
        selected = random.choice(best_candidates)
        return selected

# ==========================================
# 3. APP STAGES
# ==========================================
if 'stage' not in st.session_state: st.session_state.stage = 1
if 'ministry' not in st.session_state: st.session_state.ministry = "Media Tech"

def main():
    # STAGE 1: SELECTION
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
                    if curr.weekday() == 6: # Sunday
                        dates.append({"Date": curr, "HC": False, "Combined": False, "Notes": ""})
            st.session_state.roster_dates = dates
            st.session_state.stage = 2
            st.rerun()

    # STAGE 2: SERVICE DETAILS (FIXED: Added Combined Column)
    elif st.session_state.stage == 2:
        st.header("⚙️ Step 2: Service Details")
        df_dates = pd.DataFrame(st.session_state.roster_dates)
        edited = st.data_editor(df_dates, use_container_width=True)
        if st.button("Next: Set Unavailability"):
            st.session_state.roster_dates = edited.to_dict('records')
            st.session_state.stage = 3
            st.rerun()

    # STAGE 3: UNAVAILABILITY
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

    # STAGE 4: FINAL ROSTER
    elif st.session_state.stage == 4:
        st.header(f"📋 Final {st.session_state.ministry} Roster")
        gid = MEDIA_GID if st.session_state.ministry == "Media Tech" else WELCOME_GID
        df_team = fetch_data(gid)
        engine = RosterEngine(df_team)
        
        final_roster = []
        
        for service in st.session_state.roster_dates:
            d_str = str(service['Date'])
            unav = [n for n, dates in st.session_state.unavailability.items() if d_str in dates]
            row = {"Date": service['Date'], "Notes": service['Notes']}
            current_week_crew = []

            if st.session_state.ministry == "Welcome Ministry":
                # HC Logic: 4 members for HC, 3 for Non-HC
                num_members = 4 if service['HC'] else 3
                row["Type"] = "HC" if service['HC'] else "Non-HC"
                
                # 1. Lead
                lead_pool = df_team[df_team['team lead'].str.lower() == 'yes']['name'].tolist()
                lead = engine.get_best_candidate(lead_pool, unav, current_week_crew)
                row["Team Lead"] = lead
                if lead: 
                    current_week_crew.append(lead)
                    engine.load[lead] += 1
                
                # 2. Members + Couple Pairing
                member_slots = [f"Member {i+1}" for i in range(num_members)]
                for slot in member_slots:
                    if slot in row: continue
                    
                    m_pool = df_team[df_team['member'].str.lower() == 'yes']['name'].tolist()
                    p = engine.get_best_candidate(m_pool, unav, current_week_crew)
                    
                    if p:
                        row[slot] = p
                        current_week_crew.append(p)
                        engine.load[p] += 1
                        
                        # Couple Check
                        c_val = df_team.loc[df_team['name'] == p, 'couple'].values[0]
                        if str(c_val).strip() != "":
                            partner = df_team[(df_team['couple'] == c_val) & (df_team['name'] != p)]['name'].values[0]
                            if partner not in unav and partner not in current_week_crew:
                                for s in member_slots:
                                    if s not in row:
                                        row[s] = partner
                                        current_week_crew.append(partner)
                                        engine.load[partner] += 1
                                        break
            
            else: # Media Tech
                roles = {"Sound Crew": "sound", "Projectionist": "projection", "Stream Director": "stream director", "Cam 1": "camera"}
                for label, col in roles.items():
                    pool = df_team[df_team[col].astype(str).str.lower() != ""]["name"].tolist()
                    p = engine.get_best_candidate(pool, unav, current_week_crew)
                    row[label] = p
                    if p: 
                        current_week_crew.append(p)
                        engine.load[p] += 1
                
                # Media Lead (Gavin/Ben/Mich Lo)
                tech_leads = ["ben", "gavin", "mich lo"]
                avail_leads = [n for n in current_week_crew if any(tl in n.lower() for tl in tech_leads)]
                row["Team Lead"] = random.choice(avail_leads) if avail_leads else ""

            final_roster.append(row)
            engine.prev_week_crew = set(current_week_crew)

        # Output
        df_res = pd.DataFrame(final_roster)
        st.dataframe(df_res, use_container_width=True)

        st.divider()
        st.subheader("📊 Balancing Verification Statistics")
        stats = pd.DataFrame([{"Name": n, "Total Shifts": engine.load[n]} for n in sorted(df_team['name'].unique())])
        st.table(stats.sort_values("Total Shifts", ascending=False))
        
        if st.button("Start Over"):
            st.session_state.stage = 1
            st.rerun()

if __name__ == "__main__":
    main()
