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

st.set_page_config(page_title="SWS Roster Wizard Pro", layout="wide")

def fetch_data(gid):
    try:
        url = f"https://docs.google.com/spreadsheets/d/{CONFIG_SHEET_ID}/export?format=csv&gid={gid}"
        df = pd.read_csv(url).fillna("")
        df.columns = [str(c).strip().lower() for c in df.columns]
        return df
    except Exception as e:
        st.error(f"Spreadsheet connection error: {e}")
        return pd.DataFrame()

# ==========================================
# 2. THE ENGINE (AUDITED FOR BALANCE)
# ==========================================
class RosterEngine:
    def __init__(self, df_team):
        self.df = df_team
        self.load = defaultdict(int)
        self.prev_week_crew = set()

    def get_best_candidate(self, pool_names, unavailable, current_crew):
        # Filter available (Not unav, Not already in today's crew)
        candidates = [n for n in pool_names if n not in unavailable and n not in current_crew]
        
        # Hard Rotation: No back-to-back weeks
        fresh_pool = [n for n in candidates if n not in self.prev_week_crew]
        
        # If everyone is blocked by the rotation, fall back to the candidates
        final_pool = fresh_pool if fresh_pool else candidates
        
        if not final_pool:
            return None

        # STRICT BALANCING: Find person with the absolute lowest shift count
        min_duty_count = min(self.load[n] for n in final_pool)
        best_candidates = [n for n in final_pool if self.load[n] == min_duty_count]
        
        # If there's a tie, pick randomly among the least-loaded
        return random.choice(best_candidates)

# ==========================================
# 3. APP STAGES
# ==========================================
if 'stage' not in st.session_state: st.session_state.stage = 1
if 'ministry' not in st.session_state: st.session_state.ministry = "Media Tech"

def main():
    # --- STAGE 1: GENERATE SUNDAYS ---
    if st.session_state.stage == 1:
        st.header("📅 Step 1: Selection")
        st.session_state.ministry = st.selectbox("Ministry", ["Media Tech", "Welcome Ministry"])
        col1, col2 = st.columns(2)
        year = col1.number_input("Year", value=2026)
        months = col2.multiselect("Months", list(calendar.month_name)[1:], default=["March", "April"])
        
        if st.button("Generate Roster Dates"):
            m_map = {m: i for i, m in enumerate(calendar.month_name) if m}
            dates = []
            for m in months:
                _, days = calendar.monthrange(year, m_map[m])
                for d in range(1, days + 1):
                    curr = date(year, m_map[m], d)
                    if curr.weekday() == 6:
                        # ALL 3 FLAGS: HC, Combined, and Notes
                        dates.append({"Date": curr, "HC": False, "Combined": False, "Notes": ""})
            st.session_state.roster_dates = dates
            st.session_state.stage = 2
            st.rerun()

    # --- STAGE 2: DEFINE SERVICE TYPES ---
    elif st.session_state.stage == 2:
        st.header("⚙️ Step 2: Service Details")
        st.info("Check 'HC' for Holy Communion or 'Combined' for Special Services.")
        df_dates = pd.DataFrame(st.session_state.roster_dates)
        edited = st.data_editor(df_dates, use_container_width=True)
        if st.button("Proceed to Unavailability"):
            st.session_state.roster_dates = edited.to_dict('records')
            st.session_state.stage = 3
            st.rerun()

    # --- STAGE 3: UNAVAILABILITY ---
    elif st.session_state.stage == 3:
        gid = MEDIA_GID if st.session_state.ministry == "Media Tech" else WELCOME_GID
        df_team = fetch_data(gid)
        if df_team.empty: return
        
        names = sorted(df_team['name'].unique())
        st.header(f"❌ Step 3: {st.session_state.ministry} Unavailability")
        
        d_strs = [str(d['Date']) for d in st.session_state.roster_dates]
        temp_unav = {}
        cols = st.columns(3)
        for i, n in enumerate(names):
            temp_unav[n] = cols[i%3].multiselect(f"Unavailable: {n}", d_strs, key=f"un_{n}")
            
        if st.button("🚀 Generate Final Roster"):
            st.session_state.unavailability = temp_unav
            st.session_state.stage = 4
            st.rerun()

    # --- STAGE 4: FINAL ROSTER & STATS ---
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
            week_crew = []

            if st.session_state.ministry == "Welcome Ministry":
                # HC LOGIC: HC/Combined = 4 members, else 3
                num_members = 4 if (service['HC'] or service['Combined']) else 3
                
                # 1. Lead (Team lead pool only)
                leads = df_team[df_team['team lead'].str.lower() == 'yes']['name'].tolist()
                sel_lead = engine.get_best_candidate(leads, unav, week_crew)
                row["Team Lead"] = sel_lead
                if sel_lead: 
                    week_crew.append(sel_lead)
                    engine.load[sel_lead] += 1
                
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
                        
                        # Couple ID Check (Column F)
                        c_id = df_team.loc[df_team['name'] == p, 'couple'].values[0]
                        if str(c_id).strip() != "":
                            partner = df_team[(df_team['couple'] == c_id) & (df_team['name'] != p)]['name'].values[0]
                            if partner not in unav and partner not in week_crew:
                                for s_next in slots:
                                    if s_next not in row:
                                        row[s_next] = partner
                                        week_crew.append(partner)
                                        engine.load[partner] += 1
                                        break
            
            else: # Media Tech
                roles = {"Sound": "sound", "Projection": "projection", "Stream": "stream director", "Cam 1": "camera"}
                for label, col in roles.items():
                    pool = df_team[df_team[col].astype(str).str.lower() != ""]["name"].tolist()
                    p = engine.get_best_candidate(pool, unav, week_crew)
                    row[label] = p
                    if p: 
                        week_crew.append(p)
                        engine.load[p] += 1
                
                leads = ["ben", "gavin", "mich lo"]
                avail_leads = [n for n in week_crew if any(l in n.lower() for l in leads)]
                row["Team Lead"] = random.choice(avail_leads) if avail_leads else ""

            final_roster.append(row)
            engine.prev_week_crew = set(week_crew)

        st.dataframe(pd.DataFrame(final_roster), use_container_width=True)
        
        # BALANCING VERIFICATION
        st.divider()
        st.subheader("📊 Load Balancing Audit")
        stats_df = pd.DataFrame([{"Name": n, "Shifts": engine.load[n]} for n in sorted(df_team['name'].unique())])
        st.table(stats_df.sort_values("Shifts", ascending=False))
        
        if st.button("Reset App"):
            st.session_state.stage = 1
            st.rerun()

if __name__ == "__main__":
    main()
