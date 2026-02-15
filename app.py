import streamlit as st
import pandas as pd
import random
import calendar
from datetime import datetime, date
from collections import defaultdict

# --- CONFIGURATION ---
CONFIG_SHEET_ID = "1jh6ScfqpHe7rRN1s-9NYPsm7hwqWWLjdLKTYThRRGUo"
WELCOME_GID = "2080125013"
MEDIA_GID = "0"

st.set_page_config(page_title="Church Roster Wizard 2026", layout="wide")

# --- CUSTOM UI STYLING ---
st.markdown("""
    <style>
    .main { background-color: #f9f9fb; }
    .stDataFrame { border: 1px solid #e6e9ef; border-radius: 8px; }
    div[data-testid="stExpander"] { background-color: white; border-radius: 8px; }
    </style>
    """, unsafe_allow_html=True)

@st.cache_data(ttl=300)
def fetch_data(gid):
    try:
        url = f"https://docs.google.com/spreadsheets/d/{CONFIG_SHEET_ID}/export?format=csv&gid={gid}"
        df = pd.read_csv(url).fillna("")
        df.columns = [str(c).strip().lower() for c in df.columns]
        return df
    except Exception as e:
        st.error(f"Error connecting to Google Sheet: {e}")
        return pd.DataFrame()

# --- THE ENGINE: PARITY & ATTRIBUTES ---
class RosterEngine:
    def __init__(self, df_team):
        self.df = df_team
        self.load = defaultdict(int)
        self.prev_week_crew = set()

    def get_best(self, pool_names, unavailable, current_crew, req_male=False, req_senior=False):
        # 1. Base Availability
        candidates = [n for n in pool_names if n not in unavailable and n not in current_crew]
        
        # 2. Rotation: No Back-to-Back
        fresh_pool = [n for n in candidates if n not in self.prev_week_crew]
        final_pool = fresh_pool if fresh_pool else candidates
        
        if not final_pool: return None

        # 3. Attribute Logic (Welcome Ministry)
        if req_male:
            final_pool = [n for n in final_pool if self.df.loc[self.df['name'] == n, 'gender'].iloc[0].lower() == 'male']
        if req_senior:
            final_pool = [n for n in final_pool if self.df.loc[self.df['name'] == n, 'senior citizen'].iloc[0].lower() == 'yes']

        if not final_pool: return None

        # 4. Strict Parity (Max 1 shift difference)
        min_load = min(self.load[n] for n in final_pool)
        parity_pool = [n for n in final_pool if self.load[n] == min_load]
        
        return random.choice(parity_pool)

# --- APP WORKFLOW ---
if 'stage' not in st.session_state: st.session_state.stage = 1

def main():
    st.title("🛡️ SWS Media & Welcome Roster Wizard")

    # STAGE 1: MINISTRY & LOGIC CONFIG
    if st.session_state.stage == 1:
        st.header("1. Selection & Advanced Rules")
        st.session_state.ministry = st.selectbox("Ministry", ["Welcome Ministry", "Media Tech"])
        
        col1, col2 = st.columns(2)
        year = col1.number_input("Year", value=2026)
        months = col2.multiselect("Months", list(calendar.month_name)[1:], default=["March"])
        
        with st.expander("⚙️ Advanced Logic Rules (Toggle On/Off)"):
            st.info("These rules are enabled by default to ensure parity and diversity.")
            st.session_state.rule_parity = st.checkbox("Strict Parity (Max 1 shift diff)", value=True)
            st.session_state.rule_b2b = st.checkbox("No Back-to-Back Sundays", value=True)
            if st.session_state.ministry == "Welcome Ministry":
                st.session_state.rule_male = st.checkbox("At least 1 Male per team", value=True)
                st.session_state.rule_senior = st.checkbox("At least 1 Senior per team", value=True)
                st.session_state.rule_couple = st.checkbox("Keep Couples Together", value=True)

        if st.button("Proceed to Dates"):
            m_map = {m: i for i, m in enumerate(calendar.month_name) if m}
            dates = []
            for m in months:
                _, days = calendar.monthrange(year, m_map[m])
                for d in range(1, days + 1):
                    curr = date(year, m_map[m], d)
                    if curr.weekday() == 6:
                        dates.append({"Date": curr, "HC": False, "Combined": False, "Notes": ""})
            st.session_state.roster_dates = dates
            st.session_state.stage = 2
            st.rerun()

    # STAGE 2: SERVICE TYPES
    elif st.session_state.stage == 2:
        st.header("2. Service Details")
        st.info("Check HC/Combined to increase Welcome staffing (5 members vs 4).")
        df_dates = pd.DataFrame(st.session_state.roster_dates)
        edited = st.data_editor(df_dates, use_container_width=True, hide_index=True)
        if st.button("Proceed to Availability"):
            st.session_state.roster_dates = edited.to_dict('records')
            st.session_state.stage = 3
            st.rerun()

    # STAGE 3: UNAVAILABILITY
    elif st.session_state.stage == 3:
        gid = MEDIA_GID if st.session_state.ministry == "Media Tech" else WELCOME_GID
        df_team = fetch_data(gid)
        names = sorted([n for n in df_team['name'].unique() if n])
        st.header(f"3. {st.session_state.ministry} Unavailability")
        
        d_strs = [str(d['Date']) for d in st.session_state.roster_dates]
        temp_unav = {}
        cols = st.columns(3)
        for i, n in enumerate(names):
            temp_unav[n] = cols[i%3].multiselect(f"Unavailable: {n}", d_strs, key=f"u_{n}")
            
        if st.button("🚀 Generate Roster"):
            st.session_state.unavailability = temp_unav
            st.session_state.stage = 4
            st.rerun()

    # STAGE 4: FINAL GENERATION
    elif st.session_state.stage == 4:
        st.header(f"4. Finalized {st.session_state.ministry} Roster")
        gid = MEDIA_GID if st.session_state.ministry == "Media Tech" else WELCOME_GID
        df_team = fetch_data(gid)
        engine = RosterEngine(df_team)
        final_data = []

        for service in st.session_state.roster_dates:
            d_str = str(service['Date'])
            unav = [n for n, dts in st.session_state.unavailability.items() if d_str in dts]
            row = {"Date": service['Date'], "Notes": service['Notes']}
            week_crew = []

            # --- WELCOME MINISTRY ---
            if st.session_state.ministry == "Welcome Ministry":
                num_needed = 4 if (service['HC'] or service['Combined']) else 3
                l_pool = df_team[df_team['team lead'].astype(str).str.lower() == 'yes']['name'].tolist()
                m_pool = df_team[df_team['member'].astype(str).str.lower() == 'yes']['name'].tolist()

                # Lead
                lead = engine.get_best(l_pool, unav, week_crew)
                row["Team Lead"] = lead if lead else "Need Manual Entry"
                if lead: week_crew.append(lead); engine.load[lead] += 1
                
                # Members
                for i in range(num_needed):
                    m_label = f"Member {i+1}"
                    if m_label in row: continue

                    need_m = st.session_state.get('rule_male', False) and not any(df_team.loc[df_team['name'] == w, 'gender'].iloc[0].lower() == 'male' for w in week_crew)
                    need_s = st.session_state.get('rule_senior', False) and not any(df_team.loc[df_team['name'] == w, 'senior citizen'].iloc[0].lower() == 'yes' for w in week_crew)
                    
                    p = engine.get_best(m_pool, unav, week_crew, req_male=(i==0 and need_m), req_senior=(i==1 and need_s))
                    if p:
                        row[m_label] = p; week_crew.append(p); engine.load[p] += 1
                        # Couples Logic
                        if st.session_state.get('rule_couple', False):
                            c_id = df_team.loc[df_team['name'] == p, 'couple'].values[0]
                            if str(c_id).strip() != "":
                                partner = df_team[(df_team['couple'] == c_id) & (df_team['name'] != p)]['name'].values[0]
                                if partner not in unav and partner not in week_crew:
                                    for j in range(i+1, num_needed):
                                        next_label = f"Member {j+1}"
                                        if next_label not in row:
                                            row[next_label] = partner; week_crew.append(partner); engine.load[partner] += 1
                                            break

            # --- MEDIA TECH ---
            else:
                roles = {"Sound": "sound", "Projection": "projection", "Stream": "stream director", "Cam 1": "camera"}
                for label, col in roles.items():
                    pool = df_team[df_team[col].astype(str).str.lower() != ""]["name"].tolist()
                    p = engine.get_best(pool, unav, week_crew)
                    row[label] = p
                    if p: week_crew.append(p); engine.load[p] += 1
                
                row["Cam 2"] = "" # Requirement: Always blank
                leads_pool = ["ben", "gavin", "mich lo"]
                avail_lead = [n for n in week_crew if any(l in n.lower() for l in leads_pool)]
                row["Team Lead"] = random.choice(avail_lead) if avail_lead else ""

            final_roster.append(row)
            if st.session_state.get('rule_b2b', False): engine.prev_week_crew = set(week_crew)

        # Output UI
        st.data_editor(pd.DataFrame(final_roster), use_container_width=True, hide_index=True)
        
        st.divider()
        st.subheader("📊 Load Statistics (Shift Balance)")
        stats = pd.DataFrame([{"Name": n, "Shifts": engine.load[n]} for n in sorted(df_team['name'].unique()) if n])
        st.table(stats.sort_values("Shifts", ascending=False))
        
        if st.button("Start New Roster"):
            st.session_state.stage = 1
            st.rerun()

if __name__ == "__main__":
    main()
