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
# 2. CORE ENGINE (STRICT BALANCING)
# ==========================================
class UnifiedEngine:
    def __init__(self, df_team):
        self.df = df_team
        self.load = defaultdict(int)
        self.last_week_crew = set()

    def get_best_candidate(self, pool_names, unavailable, current_crew):
        # 1. Basic Availability
        candidates = [n for n in pool_names if n not in unavailable and n not in current_crew]
        
        # 2. Rotation Constraint (No back-to-back weeks)
        non_consecutive = [n for n in candidates if n not in self.last_week_crew]
        final_pool = non_consecutive if non_consecutive else candidates
        
        if not final_pool:
            return None

        # 3. LEAST LOADED (The Balancing Fix)
        # We only look at candidates who have the minimum number of shifts
        min_shifts = min(self.load[n] for n in final_pool)
        best_candidates = [n for n in final_pool if self.load[n] == min_shifts]
        
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
        st.header("📅 Step 1: Selection")
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
                        # RESTORED: Added 'Combined' column here
                        dates.append({"Date": curr, "HC": False, "Combined": False, "Notes": ""})
            st.session_state.roster_dates = dates
            st.session_state.stage = 2
            st.rerun()

    # --- STAGE 2: SERVICE DETAILS ---
    elif st.session_state.stage == 2:
        st.header("⚙️ Step 2: Service Details")
        df_dates = pd.DataFrame(st.session_state.roster_dates)
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
            temp_unav[n] = cols[i%3].multiselect(f"{n}", d_strs, key=f"un_{n}")
            
        if st.button("Generate Final Roster"):
            st.session_state.unavailability = temp_unav
            st.session_state.stage = 4
            st.rerun()

    # --- STAGE 4: FINAL ROSTER & STATS ---
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
            week_crew = []

            if st.session_state.ministry == "Welcome Ministry":
                # HC LOGIC: Either HC or Combined = 4 members. Else = 3.
                is_full_team = service['HC'] or service['Combined']
                num_members = 4 if is_full_team else 3
                
                # 1. Team Lead
                lead_pool = df_team[df_team['team lead'].str.lower() == 'yes']['name'].tolist()
                lead = engine.get_best_candidate(lead_pool, unav, week_crew)
                row["Team Lead"] = lead
                if lead: 
                    week_crew.append(lead)
                    engine.load[lead] += 1
                
                # 2. Members + Couple Logic
                slots = [f"Member {i+1}" for i in range(num_members)]
                for s in slots:
                    if s in row: continue
                    m_pool = df_team[df_team['member'].str.lower() == 'yes']['name'].tolist()
                    p = engine.get_best_candidate(m_pool, unav, week_crew)
                    if p:
                        row[s] = p
                        week_crew.append(p)
                        engine.load[p] += 1
                        # Couple Check
                        c_val = df_team.loc[df_team['name'] == p, 'couple'].values[0]
                        if c_val != "":
                            partner = df_team[(df_team['couple'] == c_val) & (df_team['name'] != p)]['name'].values[0]
                            if partner not in unav and partner not in week_crew:
                                for next_s in slots:
                                    if next_s not in row:
                                        row[next_s] = partner
                                        week_crew.append(partner)
                                        engine.load[partner] += 1
                                        break
            
            else: # Media Tech Logic
                roles = {"Sound Crew": "sound", "Projectionist": "projection", "Stream Director": "stream director", "Cam 1": "camera"}
                for label, col in roles.items():
                    pool = df_team[df_team[col].astype(str).str.lower() != ""]["name"].tolist()
                    p = engine.get_best_candidate(pool, unav, week_crew)
                    row[label] = p
                    if p: 
                        week_crew.append(p)
                        engine.load[p] += 1
                
                # Lead for Media
                media_leads = ["ben", "gavin", "mich lo"]
                avail_leads = [n for n in week_crew if any(l in n.lower() for l in media_leads)]
                row["Team Lead"] = random.choice(avail_leads) if avail_leads else ""

            final_roster.append(row)
            engine.last_week_crew = set(week_crew)

        # Output Table
        m_df = pd.DataFrame(final_roster)
        st.dataframe(m_df, use_container_width=True)

        # Statistics Table (The Proof)
        st.divider()
        st.subheader("📊 Final Duty Counts (Verification)")
        stats = [{"Name": n, "Total Shifts": engine.load[n]} for n in sorted(df_team['name'].unique())]
        st.table(pd.DataFrame(stats).sort_values("Total Shifts", ascending=False))
        
        if st.button("Start Over"):
