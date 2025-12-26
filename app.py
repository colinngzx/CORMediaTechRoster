import streamlit as st
import pandas as pd
import random
import calendar
from datetime import datetime, date
import io
from typing import List, Tuple

# ==========================================
# 1. CONFIGURATION
# ==========================================
CONFIG = {
    "PAGE_TITLE": "SWS Roster Wizard (Even Spread Logic)",
    "SHEET_ID": "1jh6ScfqpHe7rRN1s-9NYPsm7hwqWWLjdLKTYThRRGUo",
    "SHEET_NAME": "Team",
    "ROLES": [
        {"label": "Sound Crew",      "key": "sound"},
        {"label": "Projectionist",   "key": "projection"},
        {"label": "Stream Director", "key": "stream"},
        {"label": "Cam 1",           "key": "camera"},
    ],
    "PRIMARY_LEADS": ["gavin", "ben", "mich lo"], 
    "DEDICATED_LEAD": "darrell",                  
    "DEPRIORITIZED_WORKER": "darrell"             
}

# ==========================================
# 2. LOGIC LAYER
# ==========================================

class DateManager:
    @staticmethod
    def get_defaults() -> Tuple[int, List[str]]:
        now = datetime.now()
        curr_year = now.year + 1 if now.month == 12 else now.year
        months = []
        for i in range(1, 4):
            idx = now.month + i
            if idx > 12: idx -= 12
            months.append(calendar.month_name[idx])
        return curr_year, months

    @staticmethod
    def generate_dates(year: int, month_names: List[str]) -> List[date]:
        generated_dates = []
        m_map = {m: i for i, m in enumerate(calendar.month_name) if m}
        today = date.today()

        for m_name in month_names:
            m_idx = m_map.get(m_name)
            if not m_idx: continue
            _, days = calendar.monthrange(year, m_idx)
            for d in range(1, days + 1):
                try:
                    candidate = date(year, m_idx, d)
                    if (today - candidate).days > 180: candidate = date(year + 1, m_idx, d)
                    if candidate.weekday() == 6: generated_dates.append(candidate)
                except ValueError: continue
        return sorted(generated_dates)

class RosterEngine:
    def __init__(self, df: pd.DataFrame):
        self.df = df
        self.team_names = sorted(df['name'].unique().tolist())
        
        # Scoring and History
        self.tech_score = {name: 0 for name in self.team_names} 
        self.lead_score = {name: 0 for name in self.team_names}
        
        # NEW: Track the absolute week index when they last worked
        # Initialize with -999 so they seem like they haven't worked in ages (high priority)
        self.last_worked_index = {name: -999 for name in self.team_names}
        
        self.history_prev_week: List[str] = []

    def get_qualified_pool(self, role_key: str, unavailable: List[str], working_today: List[str]) -> List[str]:
        mask = (
            self.df['role 1'].str.contains(role_key, case=False, na=False) |
            self.df['role 2'].str.contains(role_key, case=False, na=False) |
            self.df['role 3'].str.contains(role_key, case=False, na=False)
        )
        candidates = self.df[mask]['name'].tolist()
        pool = [p for p in candidates if p not in unavailable and p not in working_today]
        fresh_pool = [p for p in pool if p not in self.history_prev_week]
        return fresh_pool if fresh_pool else pool

    def pick_tech(self, pool: List[str], current_week_idx: int) -> str:
        """
        Picks a person based on:
        1. Not being Darrell (Tier 2/Deprioritized)
        2. Lowest Total Shifts (Fairness)
        3. Lowest 'Last Worked Index' (Spacing/Gap management)
        """
        if not pool: return "NO FILL"
        
        # Initial shuffle to break ties randomly if everything else is equal
        random.shuffle(pool)
        
        def sort_key(person_name):
            # 1. Darrell Penalty
            is_deprioritized = 1 if person_name.lower() == CONFIG["DEPRIORITIZED_WORKER"].lower() else 0
            
            # 2. Total Shifts so far
            current_points = self.tech_score.get(person_name, 0)
            
            # 3. Recency Penalty (The week index they last worked)
            # Smaller number = Worked longer ago = High Priority
            last_idx = self.last_worked_index.get(person_name, -999)
            
            return (is_deprioritized, current_points, last_idx)

        pool.sort(key=sort_key)
        
        selected = pool[0]
        
        # Update Stats
        self.tech_score[selected] += 1
        self.last_worked_index[selected] = current_week_idx
        
        return selected

    def assign_lead(self, working_team: List[str], unavailable_list: List[str], current_week_idx: int) -> str:
        present_crew = [p for p in working_team if p != "NO FILL"]
        
        # A. Primary (Tier 1) - Double Hat
        primary_candidates = [p for p in present_crew if p.lower() in [x.lower() for x in CONFIG["PRIMARY_LEADS"]]]
        if primary_candidates:
            # Sort by Lead Score, then valid Tech Recency to spread the burden
            primary_candidates.sort(key=lambda x: (self.lead_score.get(x, 0), self.last_worked_index.get(x, 0)))
            selected = primary_candidates[0]
            self.lead_score[selected] += 1
            return selected

        # B. Dedicated (Tier 2) - Darrell
        dedicated = CONFIG["DEDICATED_LEAD"]
        is_dedicated_available = dedicated not in unavailable_list
        if is_dedicated_available:
            self.lead_score[dedicated] += 1
            # Mark him as working this week so he doesn't get pulled into tech immediately next week if we strictly used global logs
            self.last_worked_index[dedicated] = current_week_idx 
            return dedicated

        # C. Fallback (Tier 3)
        fallback_candidates = []
        for person in present_crew:
            is_auth = self.df.loc[self.df['name'] == person, 'team lead'].astype(str).str.contains("yes", case=False).any()
            if is_auth:
                fallback_candidates.append(person)
        
        if fallback_candidates:
            fallback_candidates.sort(key=lambda x: self.lead_score.get(x, 0))
            selected = fallback_candidates[0]
            self.lead_score[selected] += 1
            return selected

        return "⚠️ NO LEAD"

    def set_previous_workers(self, workers: List[str]):
        self.history_prev_week = workers

    def get_stats(self) -> pd.DataFrame:
        df = pd.DataFrame([
            {"Name": k, "Shifts": v, "Lead Badge": self.lead_score.get(k, 0)} 
            for k, v in self.tech_score.items() if (v > 0 or self.lead_score.get(k, 0) > 0)
        ])
        if not df.empty:
            return df.sort_values(["Shifts", "Lead Badge"], ascending=False)
        return pd.DataFrame()

# ==========================================
# 3. UI HELPER & STYLING
# ==========================================
@st.cache_data(ttl=60)
def fetch_data():
    url = f"https://docs.google.com/spreadsheets/d/{CONFIG['SHEET_ID']}/gviz/tq?tqx=out:csv&sheet={CONFIG['SHEET_NAME']}"
    try:
        df = pd.read_csv(url).fillna("")
        df.columns = df.columns.str.strip().str.lower()
        if 'status' in df.columns:
            df = df[(df['status'].str.lower() == 'active') | (df['status'] == '')]
        if 'name' in df.columns: df['name'] = df['name'].str.strip()
        return df
    except Exception as e:
        st.error(f"Error: {e}")
        return pd.DataFrame()

def apply_styling():
    st.markdown("""
        <style>
        .stApp, [data-testid="stAppViewContainer"], [data-testid="stHeader"] { background-color: #ffffff !important; }
        h1, h2, h3, h4, h5, h6, p, div, span, label, .stMarkdown { color: #000000 !important; }
        .stMultiSelect label, .stTextInput label, .stNumberInput label, .stSelectbox label { color: #000000 !important; font-weight: bold; }
        div[data-baseweb="select"] > div { background-color: #f8f9fa !important; color: #000000 !important; border: 1px solid #ccc; }
        div.stButton > button[kind="primary"] { background-color: #007AFF !important; color: white !important; }
        div.stButton > button p { color: white !important; }
        </style>
    """, unsafe_allow_html=True)

# ==========================================
# 4. MAIN APP
# ==========================================

def main():
    st.set_page_config(page_title=CONFIG["PAGE_TITLE"], layout="wide")
    apply_styling()
    
    if 'stage' not in st.session_state: st.session_state.stage = 1
    if 'roster_dates' not in st.session_state: st.session_state.roster_dates = []
    if 'event_details' not in st.session_state: st.session_state.event_details = pd.DataFrame()
    if 'unavailability' not in st.session_state: st.session_state.unavailability = {}

    df_team = fetch_data()
    if df_team.empty: st.stop()

    st.title("🧙‍♂️ Roster Wizard")
    st.markdown("---")

    # STAGE 1: DATES
    if st.session_state.stage == 1:
        st.subheader("1. Select Duration")
        d_year, d_months = DateManager.get_defaults()
        c1, c2 = st.columns([1, 2])
        y = c1.number_input("Year", 2024, 2030, d_year)
        m = c2.multiselect("Months", calendar.month_name[1:], default=d_months)
        
        st.markdown("<br>", unsafe_allow_html=True)
        if st.button("Next ➡️", type="primary"):
            st.session_state.roster_dates = DateManager.generate_dates(y, m)
            st.session_state.stage = 2
            st.rerun()

    # STAGE 2: REVIEW
    elif st.session_state.stage == 2:
        st.subheader("2. Review Dates")
        d_df = pd.DataFrame({"Dates": [d.strftime("%a, %d %b") for d in st.session_state.roster_dates]})
        st.dataframe(d_df, hide_index=True, use_container_width=True, height=200)
        
        st.markdown("<br>", unsafe_allow_html=True)
        if st.button("Confirm & Continue ➡️", type="primary"):
            st.session_state.event_details = pd.DataFrame({
                "Date": st.session_state.roster_dates,
                "Holy Communion": [False]*len(st.session_state.roster_dates),
                "Combined": [False]*len(st.session_state.roster_dates),
                "Notes": [""]*len(st.session_state.roster_dates)
            })
            st.session_state.stage = 3
            st.rerun()

    # STAGE 3: DETAILS
    elif st.session_state.stage == 3:
        st.subheader("3. Service Details")
        st.session_state.event_details = st.data_editor(
            st.session_state.event_details,
            column_config={"Date": st.column_config.DateColumn("Date", format="DD MMM", disabled=True)},
            hide_index=True, use_container_width=True
        )
        st.markdown("<br>", unsafe_allow_html=True)
        if st.button("Next ➡️", type="primary"):
            st.session_state.stage = 4
            st.rerun()

    # STAGE 4: AVAILABILITY
    elif st.session_state.stage == 4:
        st.subheader("4. Who is AWAY?")
        date_opts = {r['Date'].strftime("%d-%b"): r['Date'] for _, r in st.session_state.event_details.iterrows()}
        team_ua = {}
        
        cols = st.columns(3)
        team_names = sorted(df_team['name'].unique())
        for i, name in enumerate(team_names):
            with cols[i%3]:
                sel = st.multiselect(name, options=date_opts.keys(), key=f"ua_{name}")
                if sel: team_ua[name] = [date_opts[s] for s in sel]
        
        st.markdown("<br>", unsafe_allow_html=True)
        if st.button("✨ Generate Roster ➡️", type="primary"):
            final_ua = {}
            for name, dates in team_ua.items():
                for d in dates:
                    final_ua.setdefault(d, []).append(name)
            st.session_state.unavailability = final_ua
            st.session_state.stage = 5
            st.rerun()

    # STAGE 5: OUTPUT
    elif st.session_state.stage == 5:
        st.subheader("5. Final Roster")
        engine = RosterEngine(df_team)
        results = []
        ordered_events = st.session_state.event_details.sort_values("Date")

        # Use enumerate to get the week index for spacing logic
        for week_idx, (_, row) in enumerate(ordered_events.iterrows()):
            curr_date = row['Date']
            ua = st.session_state.unavailability.get(curr_date, [])
            working_today = []
            
            day_data = {
                "Month": curr_date.month,
                "Date": curr_date.strftime("%d-%b"),
                "Details": " ".join([x for x in ["HC" if row['Holy Communion'] else "", "Comb" if row['Combined'] else "", f"({row['Notes']})" if row['Notes'] else ""] if x])
            }

            # 1. FILL TECH ROLES
            for role_conf in CONFIG["ROLES"]:
                pool = engine.get_qualified_pool(role_conf["key"], ua, working_today)
                # Pass week_idx to enable "Time Since Last Shift" logic
                person = engine.pick_tech(pool, week_idx) 
                if person != "NO FILL": 
                    working_today.append(person)
                day_data[role_conf["label"]] = person
            
            # 2. DETERMINE LEAD
            # Pass week_idx to update Darrell's fatigue stats if he works
            lead_for_day = engine.assign_lead(working_today, ua, week_idx)
            
            day_data["Team Lead"] = lead_for_day
            
            engine.set_previous_workers(working_today)
            results.append(day_data)

        # DISPLAY
        final_df = pd.DataFrame(results)
        col_order = ["Date", "Details", "Team Lead"] + [r['label'] for r in CONFIG['ROLES']]
        
        csv_buffer = io.StringIO()
        is_first = True
        
        for m_idx, group in final_df.groupby("Month"):
            st.write(f"##### {calendar.month_name[m_idx]}")
            disp = group[col_order].set_index("Date").T.reset_index().rename(columns={"index": "Role"})
            
            styler = disp.style.set_properties(**{'text-align': 'center', 'background-color': '#fff', 'color': '#000', 'border-color': '#ddd'})
            styler = styler.applymap(lambda v: 'background-color: #e6f2ff; font-weight: bold; color: black', subset=['Role'])
            
            st.dataframe(styler, use_container_width=True, hide_index=True)
            
            if not is_first: csv_buffer.write("\n")
            disp.to_csv(csv_buffer, index=False)
            is_first = False

        st.divider()
        c1, c2 = st.columns([2,1])
        with c1:
            st.caption("Darrell only scheduled if Gavin, Ben, or Mich Lo are absent from Tech Crew.")
            st_df = engine.get_stats()
            if not st_df.empty:
               st.dataframe(st_df.set_index("Name").T, use_container_width=True)
        with c2:
            st.download_button("💾 Download CSV", csv_buffer.getvalue(), "roster.csv", "text/csv", type="primary")
            if st.button("🔄 Restart"):
                st.session_state.stage = 1
                st.rerun()

if __name__ == "__main__":
    main()
