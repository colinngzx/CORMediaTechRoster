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

st.set_page_config(page_title="SWS Roster Wizard", layout="wide")

# --- CUSTOM CSS (Excel-like UI) ---
st.markdown("""
    <style>
    .stDataFrame { border: 1px solid #e6e9ef; border-radius: 5px; }
    [data-testid="stMetricValue"] { font-size: 1.2rem; color: #007bff; }
    .main { background-color: #f8f9fa; }
    </style>
    """, unsafe_allow_html=True)

@st.cache_data(ttl=600)
def fetch_data(gid):
    try:
        url = f"https://docs.google.com/spreadsheets/d/{CONFIG_SHEET_ID}/export?format=csv&gid={gid}"
        df = pd.read_csv(url).fillna("")
        df.columns = [str(c).strip().lower() for c in df.columns]
        return df
    except Exception as e:
        st.error(f"Error connecting to Spreadsheet: {e}")
        return pd.DataFrame()

class RosterEngine:
    def __init__(self, df_team):
        self.df = df_team
        self.load = defaultdict(int)
        self.prev_week_crew = set()

    def get_best(self, pool_names, unavailable, current_crew, req_male=False, req_senior=False):
        candidates = [n for n in pool_names if n not in unavailable and n not in current_crew]
        # No back-to-back (Valerie Rule)
        fresh_pool = [n for n in candidates if n not in self.prev_week_crew]
        final_pool = fresh_pool if fresh_pool else candidates
        
        if not final_pool: return None

        # Attribute Requirements
        if req_male:
            final_pool = [n for n in final_pool if self.df.loc[self.df['name'] == n, 'gender'].iloc[0].lower() == 'male']
        if req_senior:
            final_pool = [n for n in final_pool if self.df.loc[self.df['name'] == n, 'senior'].iloc[0].lower() == 'yes']

        if not final_pool: return None

        # Strict Parity (Max 1 shift difference)
        min_load = min(self.load[n] for n in final_pool)
        parity_pool = [n for n in final_pool if self.load[n] == min_load]
        return random.choice(parity_pool)

if 'stage' not in st.session_state: st.session_state.stage = 1

def main():
    st.title("🛡️ SWS Roster Wizard")

    if st.session_state.stage == 1:
        st.header("1. Ministry & Dates")
        st.session_state.ministry = st.selectbox("Ministry", ["Media Tech", "Welcome Ministry"])
        col1, col2 = st.columns(2)
        year = col1.number_input("Year", value=2026)
        months = col2.multiselect("Months", list(calendar.month_name)[1:], default=["March"])
        if st.button("Generate Sundays"):
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

    elif st.session_state.stage == 2:
        st.header("2. Service Settings")
        df_dates = pd.DataFrame(st.session_state.roster_dates)
        edited = st.data_editor(df_dates, use_container_width=True, hide_index=True)
        if st.button("Next"):
            st.session_state.roster_dates = edited.to_dict('records')
            st.session_state.stage = 3
            st.rerun()

    elif st.session_state.stage == 3:
        gid = MEDIA_GID if st.session_state.ministry == "Media Tech" else WELCOME_GID
        df_team = fetch_data(gid)
        names = sorted([n for n in df_team['name'].unique() if n])
        st.header(f"3. {st.session_state.ministry} Availability")
        d_strs = [str(d['Date']) for d in st.session_state.roster_dates]
        temp_unav = {}
        cols = st.columns(3)
        for i, n in enumerate(names):
            temp_unav[n] = cols[i%3].multiselect(f"Unav: {n}", d_strs, key=f"u_{n}")
        if st.button("Generate Final Roster"):
            st.session_state.unavailability = temp_unav
            st.session_state.stage = 4
            st.rerun()

    elif st.session_state.stage == 4:
        st.header(f"4. Finalized {st.session_state.ministry} Roster")
        gid = MEDIA_GID if st.session_state.ministry == "Media Tech" else WELCOME_GID
        df_team = fetch_data(gid)
        engine = RosterEngine(df_team)
        final_roster = []

        for service in st.session_state.roster_dates:
            d_str = str(service['Date'])
            unav = [n for n, dts in st.session_state.unavailability.items() if d_str in dts]
            row = {"Date": service['Date'], "Notes": service['Notes']}
            week_crew = []

            if st.session_state.ministry == "Welcome Ministry":
                # HC/Combined = 1 Lead + 4 Members; Regular = 1 Lead + 3 Members
                num_needed = 4 if (service['HC'] or service['Combined']) else 3
                l_pool = df_team[df_team['team lead'].str.lower() == 'yes']['name'].tolist()
                lead = engine.get_best(l_pool, unav, week_crew)
                row["Team Lead"] = lead
                if lead: week_crew.append(lead); engine.load[lead] += 1
                
                m_slots = [f"Member {i+1}" for i in range(num_needed)]
                m_pool = df_team[df_team['member'].str.lower() == 'yes']['name'].tolist()
                for i, s_label in enumerate(m_slots):
                    if s_label in row: continue
                    need_m = not any(df_team.loc[df_team['name'] == w, 'gender'].iloc[0].lower() == 'male' for w in week_crew)
                    need_s = not any(df_team.loc[df_team['name'] == w, 'senior'].iloc[0].lower() == 'yes' for w in week_crew)
                    p = engine.get_best(m_pool, unav, week_crew, req_male=(i==0 and need_m), req_senior=(i==1 and need_s))
                    if p:
                        row[s_label] = p; week_crew.append(p); engine.load[p] += 1
                        c_id = df_team.loc[df_team['name'] == p, 'couple'].values[0]
                        if str(c_id).strip() != "":
                            partner = df_team[(df_team['couple'] == c_id) & (df_team['name'] != p)]['name'].values[0]
                            if partner not in unav and partner not in week_crew:
                                for s_next in m_slots:
                                    if s_next not in row:
                                        row[s_next] = partner; week_crew.append(partner); engine.load[partner] += 1
                                        break
            else:
                roles = {"Sound": "sound", "Projection": "projection", "Stream": "stream director", "Cam 1": "camera"}
                for label, col_n in roles.items():
                    pool = df_team[df_team[col_n].astype(str).str.lower() != ""]["name"].tolist()
                    p = engine.get_best(pool, unav, week_crew)
                    row[label] = p
                    if p: week_crew.append(p); engine.load[p] += 1
                row["Cam 2"] = "" # Always blank
                leads = ["ben", "gavin", "mich lo"]
                avail_leads = [n for n in week_crew if any(l in n.lower() for l in leads)]
                row["Team Lead"] = random.choice(avail_leads) if avail_leads else ""

            final_roster.append(row)
            engine.prev_week_crew = set(week_crew)

        st.data_editor(pd.DataFrame(final_roster), use_container_width=True, hide_index=True)
        st.divider()
        st.subheader("📊 Load Stats")
        st.table(pd.DataFrame([{"Name": n, "Shifts": engine.load[n]} for n in sorted(df_team['name'].unique()) if n]).sort_values("Shifts", ascending=False))
        if st.button("Reset"): st.session_state.stage = 1; st.rerun()

if __name__ == "__main__": main()
