import streamlit as st
import pandas as pd
import random
import calendar
from datetime import datetime, date, timedelta
import io
from typing import List, Dict, Optional, Tuple

# ==========================================
# 1. CONFIGURATION & CONSTANTS
# ==========================================
CONFIG = {
    "PAGE_TITLE": "SWS Roster Wizard",
    "SHEET_ID": "1jh6ScfqpHe7rRN1s-9NYPsm7hwqWWLjdLKTYThRRGUo",
    "SHEET_NAME": "Team",
    "ROLES": [
        {"label": "Sound Crew",      "key": "sound",      "type": "tech"},
        {"label": "Projectionist",   "key": "projection", "type": "tech"},
        {"label": "Stream Director", "key": "stream",     "type": "tech"},
        {"label": "Cam 1",           "key": "camera",     "type": "tech"},
        {"label": "Cam 2",           "key": "cam_2",      "type": "tech"}, # Optional placeholder
        {"label": "Team Lead",       "key": "team lead",  "type": "lead"}
    ]
}

# ==========================================
# 2. UTILITY CLASSES (LOGIC LAYER)
# ==========================================

class DateManager:
    """Handles smart defaults for date selection"""
    
    @staticmethod
    def get_defaults() -> Tuple[int, List[str]]:
        """Calculates default year and next 3 months based on today."""
        now = datetime.now()
        curr_year = now.year
        curr_month = now.month

        # Logic: If Dec (12), default to next year
        default_year = curr_year + 1 if curr_month == 12 else curr_year
        
        # Next 3 months logic
        months = []
        for i in range(1, 4):
            idx = curr_month + i
            if idx > 12: idx -= 12
            months.append(calendar.month_name[idx])
            
        return default_year, months

    @staticmethod
    def generate_dates(year: int, month_names: List[str]) -> List[date]:
        """Generates Sundays, handling local year rollovers intelligently."""
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
                    
                    # SMART LOGIC: If user selected Jan, but year is still set to 
                    # previous year (e.g., config is old), bump year if date is > 180 days in past.
                    if (today - candidate).days > 180:
                        candidate = date(year + 1, m_idx, d)
                        
                    if candidate.weekday() == 6: # Sunday
                        generated_dates.append(candidate)
                except ValueError:
                    continue # Invalid date
                    
        return sorted(generated_dates)

class RosterEngine:
    """Handles the business logic of assigning people to slots."""
    
    def __init__(self, df: pd.DataFrame):
        self.df = df
        self.team_names = sorted(df['name'].unique().tolist())
        # Load Score: 0 based index for fairness
        self.load_score = {name: 0 for name in self.team_names}
        self.history_prev_week: List[str] = []

    def get_pool(self, role_keyword: str, role_type: str, unavailable: List[str], working_today: List[str]) -> List[str]:
        """Filters the team list for capability, availability, and freshness."""
        
        # 1. Capability Filter
        if role_type == "lead":
            # Check for explicitly marked Team Leads
            if 'team lead' in self.df.columns:
                candidates = self.df[self.df['team lead'].astype(str).str.contains("yes", case=False, na=False)]['name'].tolist()
            else:
                candidates = []
        else:
            # Check 3 role columns for keyword
            mask = (
                self.df['role 1'].str.contains(role_keyword, case=False, na=False) |
                self.df['role 2'].str.contains(role_keyword, case=False, na=False) |
                self.df['role 3'].str.contains(role_keyword, case=False, na=False)
            )
            candidates = self.df[mask]['name'].tolist()

        # 2. Availability Filter
        pool = [p for p in candidates if p not in unavailable and p not in working_today]
        
        # 3. Freshness Filter (Did they work last week?)
        # For Team Leads, if the pool is empty, we relax this rule (Prioritize filling the role)
        fresh_pool = [p for p in pool if p not in self.history_prev_week]
        
        if fresh_pool: return fresh_pool
        
        # Fallback: Use people who worked last week if no one else exists (Darrell Rule)
        return pool

    def pick_person(self, pool: List[str], role_type: str) -> str:
        """Selects the best candidate based on Load Score."""
        if not pool: return "NO FILL"
        
        # 1. Shuffle for randomness among equals
        random.shuffle(pool)
        
        # 2. Sort by Load Score (Ascending - give to person with least work)
        pool.sort(key=lambda x: self.load_score.get(x, 0))
        
        selected = pool[0]
        
        # ====================================================
        # KEY BUSINESS LOGIC: SCORING
        # Team Lead = 0 Points (Does not increase load score)
        # Technical = 1 Point
        # ====================================================
        if role_type != 'lead':
            self.load_score[selected] += 1
            
        return selected

    def set_previous_workers(self, workers: List[str]):
        self.history_prev_week = workers

    def get_stats(self) -> pd.DataFrame:
        """Returns the final scoring stats."""
        # Only show people with > 0 technical points
        valid_scores = {k: v for k, v in self.load_score.items() if v > 0}
        df = pd.DataFrame(list(valid_scores.items()), columns=["Name", "Technical Points"])
        return df.sort_values("Technical Points", ascending=False)


# ==========================================
# 3. UI HELPER FUNCTIONS
# ==========================================

@st.cache_data(ttl=60)
def fetch_data():
    """Fetches data from Google Sheets safely."""
    url = f"https://docs.google.com/spreadsheets/d/{CONFIG['SHEET_ID']}/gviz/tq?tqx=out:csv&sheet={CONFIG['SHEET_NAME']}"
    try:
        df = pd.read_csv(url).fillna("")
        df.columns = df.columns.str.strip().str.lower()
        if 'status' in df.columns:
            df = df[(df['status'].str.lower() == 'active') | (df['status'] == '')]
        if 'name' in df.columns:
            df['name'] = df['name'].str.strip()
        return df
    except Exception as e:
        st.error(f"Error connecting to Google Sheets: {e}")
        return pd.DataFrame()

def apply_styling():
    st.markdown("""
        <style>
        .stApp { background-color: #f8f9fa; }
        div.stButton > button[kind="primary"] { background-color: #007AFF; border:none; border-radius: 8px; }
        div[data-testid="stMetricValue"] { font-size: 1.2rem; }
        header {visibility: hidden;}
        </style>
    """, unsafe_allow_html=True)

# ==========================================
# 4. MAIN APPLICATION
# ==========================================

def main():
    st.set_page_config(page_title=CONFIG["PAGE_TITLE"], page_icon="🧙‍♂️", layout="wide")
    apply_styling()

    # --- Session State Init ---
    if 'stage' not in st.session_state: st.session_state.stage = 1
    if 'roster_dates' not in st.session_state: st.session_state.roster_dates = []
    if 'event_details' not in st.session_state: st.session_state.event_details = pd.DataFrame()
    if 'unavailability' not in st.session_state: st.session_state.unavailability = {}

    # --- Data Loading ---
    df_team = fetch_data()
    if df_team.empty: st.stop()
    
    st.title("🧙‍♂️ Roster Generator")
    st.markdown("---")

    # ---------------------------
    # STAGE 1: DURATION
    # ---------------------------
    if st.session_state.stage == 1:
        st.subheader("1. Select Duration")
        
        def_year, def_months = DateManager.get_defaults()
        
        c1, c2 = st.columns([1, 2])
        year_sel = c1.number_input("Year", 2024, 2030, def_year)
        selected_months = c2.multiselect("Select Months", calendar.month_name[1:], default=def_months)
        
        st.markdown("<br>", unsafe_allow_html=True)
        if st.button("Generate Dates ➡️", type="primary"):
            if not selected_months:
                st.warning("Please select at least one month.")
            else:
                dates = DateManager.generate_dates(year_sel, selected_months)
                st.session_state.roster_dates = dates
                st.session_state.stage = 2
                st.rerun()

    # ---------------------------
    # STAGE 2: REVIEW DATES
    # ---------------------------
    elif st.session_state.stage == 2:
        st.subheader("2. Review Dates")
        
        dates_df = pd.DataFrame({"Selected Dates": [d.strftime("%a, %d %b %Y") for d in st.session_state.roster_dates]})
        st.dataframe(dates_df, use_container_width=True, height=200, hide_index=True)
        
        c1, c2 = st.columns(2)
        with c1:
            new_date = st.date_input("Add specific date", date.today())
            if st.button("➕ Add Date"):
                if new_date not in st.session_state.roster_dates:
                    st.session_state.roster_dates.append(new_date)
                    st.session_state.roster_dates.sort()
                    st.rerun()
        with c2:
            if st.session_state.roster_dates:
                rem_date = st.selectbox("Remove date", st.session_state.roster_dates, format_func=lambda x: x.strftime("%d %b"))
                if st.button("❌ Remove Date"):
                    st.session_state.roster_dates.remove(rem_date)
                    st.rerun()

        st.markdown("<br>", unsafe_allow_html=True)
        c1, c2 = st.columns([1, 5])
        if c1.button("⬅️ Back"): st.session_state.stage = 1; st.rerun()
        if c2.button("Next: Event Details ➡️", type="primary"):
            # Init DataFrame for next step
            st.session_state.event_details = pd.DataFrame({
                "Date": st.session_state.roster_dates,
                "Holy Communion": [False] * len(st.session_state.roster_dates),
                "Combined Service": [False] * len(st.session_state.roster_dates),
                "Notes": [""] * len(st.session_state.roster_dates)
            })
            st.session_state.stage = 3
            st.rerun()

    # ---------------------------
    # STAGE 3: DETAILS
    # ---------------------------
    elif st.session_state.stage == 3:
        st.subheader("3. Service Details")
        
        edited_df = st.data_editor(
            st.session_state.event_details, 
            column_config={
                "Date": st.column_config.DateColumn("Date", format="DD MMM", disabled=True),
                "Holy Communion": st.column_config.CheckboxColumn("HC?", default=False),
                "Combined Service": st.column_config.CheckboxColumn("Combined?", default=False)
            },
            hide_index=True,
            use_container_width=True,
            height=(len(st.session_state.event_details) * 35) + 38
        )
        
        st.markdown("<br>", unsafe_allow_html=True)
        c1, c2 = st.columns([1, 5])
        if c1.button("⬅️ Back"): st.session_state.stage = 2; st.rerun()
        if c2.button("Next: Availability ➡️", type="primary"):
            st.session_state.event_details = edited_df
            st.session_state.stage = 4
            st.rerun()

    # ---------------------------
    # STAGE 4: AVAILABILITY
    # ---------------------------
    elif st.session_state.stage == 4:
        st.subheader("4. Team Availability (Who is AWAY?)")
        
        # Create user-friendly labels for dropdown
        date_map = {}
        for _, row in st.session_state.event_details.iterrows():
            label = row['Date'].strftime("%d-%b")
            if row['Holy Communion']: label += " (HC)"
            date_map[label] = row['Date']
            
        unavailability_map = {}
        
        # UI: Grid layout for compactness
        team_list = sorted(df_team['name'].unique())
        cols = st.columns(3)
        
        for i, name in enumerate(team_list):
            with cols[i % 3]:
                selected_labels = st.multiselect(
                    f"{name}", 
                    options=date_map.keys(), 
                    key=f"ua_{name}",
                    placeholder="Available"
                )
                if selected_labels:
                    unavailability_map[name] = [date_map[l] for l in selected_labels]
        
        st.markdown("<br>", unsafe_allow_html=True)
        c1, c2 = st.columns([1, 5])
        if c1.button("⬅️ Back"): st.session_state.stage = 3; st.rerun()
        if c2.button("✨ Generate Roster ➡️", type="primary"):
            # Transform map: Person -> Dates ===> Date -> [People]
            final_ua = {}
            for name, dates in unavailability_map.items():
                for d in dates:
                    if d not in final_ua: final_ua[d] = []
                    final_ua[d].append(name)
            
            st.session_state.unavailability = final_ua
            st.session_state.stage = 5
            st.rerun()

    # ---------------------------
    # STAGE 5: GENERATION & EXPORT
    # ---------------------------
    elif st.session_state.stage == 5:
        st.subheader("5. Final Roster")
        
        # --- EXECUTE LOGIC ---
        engine = RosterEngine(df_team)
        roster_rows = []
        
        events_sorted = st.session_state.event_details.sort_values(by="Date")
        
        for _, row in events_sorted.iterrows():
            curr_date = row['Date']
            
            # Determine Details String
            details_parts = []
            if row['Holy Communion']: details_parts.append("HC")
            if row['Combined Service']: details_parts.append("Comb")
            if row['Notes']: details_parts.append(f"({row['Notes']})")
            
            # Init Row Data
            day_data = {
                "Month": curr_date.month,
                "Service Dates": curr_date.strftime("%d-%b"),
                "Additional Details": " ".join(details_parts)
            }
            
            # Context for this specific Sunday
            unavailable_today = st.session_state.unavailability.get(curr_date, [])
            working_today = []
            
            # Fill Roles defined in CONFIG
            for role_conf in CONFIG["ROLES"]:
                if role_conf["key"] == "cam_2": 
                    # Special case: Cam 2 usually empty unless specified otherwise
                    day_data[role_conf["label"]] = ""
                    continue

                pool = engine.get_pool(
                    role_keyword=role_conf["key"],
                    role_type=role_conf["type"],
                    unavailable=unavailable_today,
                    working_today=working_today
                )
                
                selected_person = engine.pick_person(pool, role_conf["type"])
                
                if selected_person != "NO FILL":
                    working_today.append(selected_person)
                    
                day_data[role_conf["label"]] = selected_person
            
            # Update History for next iteration
            engine.set_previous_workers(working_today)
            roster_rows.append(day_data)
            
        # --- DISPLAY RESULTS ---
        final_df = pd.DataFrame(roster_rows)
        
        # Mapping labels for display order
        display_cols = ["Additional Details"] + [r["label"] for r in CONFIG["ROLES"]]
        csv_buffer = io.StringIO()
        is_first_chunk = True

        for m_idx, group in final_df.groupby("Month"):
            st.markdown(f"##### {calendar.month_name[m_idx]}")
            
            # Pivot for Excel-like view (Roles as Rows, Dates as Columns)
            display_df = group.set_index("Service Dates").T
            # Filter only relevant rows and reorder
            display_df = display_df.loc[display_df.index.isin(display_cols)]
            display_df = display_df.reindex(display_cols).reset_index().rename(columns={"index": "Role"})
            
            # Visual Styling
            st.dataframe(
                display_df.style.set_properties(**{'text-align': 'center'})
                .applymap(lambda v: 'background-color: #e6f2ff; font-weight: bold', subset=['Role']),
                use_container_width=True, 
                hide_index=True
            )
            
            # CSV Accumulation
            if not is_first_chunk: csv_buffer.write("\n")
            display_df.to_csv(csv_buffer, index=False)
            is_first_chunk = False

        # --- STATS REPORT ---
        st.divider()
        c1, c2 = st.columns([2, 1])
        with c1:
            st.write("#### 📊 Technical Workload Stats")
            st.info("ℹ️ **Scoring Rule:** Technical Roles = 1 Point. Team Lead = 0 Points (to ensure leads are available for tech).")
            stats_df = engine.get_stats()
            st.dataframe(stats_df.T, use_container_width=True)
            
        with c2:
            st.write("#### 📥 Actions")
            st.download_button(
                "💾 Download Roster (.csv)", 
                data=csv_buffer.getvalue(), 
                file_name=f"roster_{date.today().strftime('%Y_%m')}.csv", 
                mime="text/csv", 
                type="primary"
            )
            if st.button("🔄 Start Over", use_container_width=True):
                st.session_state.stage = 1
                st.session_state.roster_dates = []
                st.rerun()

if __name__ == "__main__":
    main()
