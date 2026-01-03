import streamlit as st
import pandas as pd
import random
import calendar
from datetime import datetime, date
from collections import defaultdict
from typing import List, Dict, Tuple
from dataclasses import dataclass

# ==========================================
# 1. CONFIGURATION: "Designed in California"
# ==========================================

@dataclass(frozen=True)
class AppConfig:
    PAGE_TITLE: str = "Team Sync" # Simpler Request
    SHEET_ID: str = "1jh6ScfqpHe7rRN1s-9NYPsm7hwqWWLjdLKTYThRRGUo"
    PRIMARY_LEADS: Tuple[str, ...] = ("gavin", "ben", "mich lo") 
    
    # Mapping Config
    ROLES: Tuple[Dict[str, str], ...] = (
        {"label": "Sound",           "sheet_col": "sound"},
        {"label": "Projections",     "sheet_col": "projection"},
        {"label": "Stream",          "sheet_col": "stream director"},
        {"label": "Camera 1",        "sheet_col": "camera"},
    )

CONFIG = AppConfig()

st.set_page_config(
    page_title=CONFIG.PAGE_TITLE, 
    page_icon="",
    layout="centered", # Jobs prefers focus over width
    initial_sidebar_state="collapsed" # Hide the clutter
)

# ==========================================
# 2. APPLE-ESQUE STYLING
# ==========================================

APPLE_CSS = """
<style>
    /* 1. Global Reset & Fonts */
    html, body, [class*="css"] {
        font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif, "Apple Color Emoji";
        color: #1d1d1f;
    }
    .stApp {
        background-color: #f5f5f7; /* Apple Light Grey Background */
    }

    /* 2. Headlines */
    h1, h2, h3 {
        font-weight: 600;
        letter-spacing: -0.02em;
        color: #1d1d1f;
    }
    
    /* 3. The Service Card (The Hero) */
    .service-card {
        background-color: #ffffff;
        border-radius: 18px;
        box-shadow: 0 4px 12px rgba(0,0,0,0.08); /* Soft, diffused shadow */
        padding: 24px;
        margin-bottom: 24px;
        border: 1px solid rgba(0,0,0,0.02);
        transition: transform 0.2s ease;
    }
    .service-card:hover {
        transform: translateY(-2px);
    }
    
    /* 4. Date Header inside Card */
    .card-date-row {
        display: flex;
        justify-content: space-between;
        align-items: baseline;
        margin-bottom: 20px;
        border-bottom: 1px solid #f0f0f0;
        padding-bottom: 10px;
    }
    .card-date {
        font-size: 1.4rem;
        font-weight: 700;
        color: #1d1d1f;
    }
    .card-meta {
        font-size: 0.9rem;
        color: #86868b;
        font-weight: 500;
        background: #f5f5f7;
        padding: 4px 12px;
        border-radius: 12px;
    }

    /* 5. Role Pills */
    .role-row {
        display: flex;
        align-items: center;
        margin-bottom: 12px;
    }
    .role-label {
        width: 100px;
        font-size: 0.85rem;
        text-transform: uppercase;
        letter-spacing: 0.05em;
        color: #86868b;
        font-weight: 600;
    }
    .role-value {
        font-size: 1.1rem;
        font-weight: 500;
        color: #1d1d1f;
    }
    .role-empty {
        color: #d2d2d7;
        font-style: italic;
    }
    
    /* 6. Buttons - Making them look like iOS buttons */
    .stButton > button {
        border-radius: 99px;
        font-weight: 500;
        padding-top: 0.5rem;
        padding-bottom: 0.5rem;
    }
    
    /* Hide Streamlit Boilerplate for printing */
    @media print {
        section[data-testid="stSidebar"] { display: none; }
        .stButton { display: none; }
        .stApp { background-color: white; }
        .service-card { box-shadow: none; border: 1px solid #ddd; page-break-inside: avoid; }
    }
</style>
"""
st.markdown(APPLE_CSS, unsafe_allow_html=True)

# ==========================================
# 3. STATE & DATA (Engine remains Logic-Heavy)
# ==========================================

class SessionManager:
    @staticmethod
    def init():
        defaults = {'stage': 1, 'roster_dates': [], 'unavailability': {}, 'master_roster': None}
        for k, v in defaults.items():
            if k not in st.session_state: st.session_state[k] = v

    @staticmethod
    def reset():
        for k in list(st.session_state.keys()): del st.session_state[k]
        SessionManager.init()

class DataLoader:
    @staticmethod
    @st.cache_data(ttl=900)
    def fetch_data(sheet_id):
        url = f"https://docs.google.com/spreadsheets/d/{sheet_id}/export?format=csv&gid=0"
        try:
            df = pd.read_csv(url).fillna("")
            df.columns = df.columns.str.strip().str.lower()
            renames = {'stream dire': 'stream director', 'team le': 'team lead'}
            cols = {}
            for c in df.columns:
                for k, v in renames.items():
                    if k in c: cols[c] = v
            df.rename(columns=cols, inplace=True)
            return df
        except: return pd.DataFrame()

# ==========================================
# 4. THE ENGINE (The Brains inside the Beauty)
# ==========================================

class RosterEngine:
    def __init__(self, df):
        self.df = df
        self.team_names = sorted([n for n in df['name'].unique() if str(n).strip() != ""], key=str.lower)
        self.load = defaultdict(int)
        self.lead_load = defaultdict(int)
        self.pair_history = defaultdict(int) 
        self.last_role = defaultdict(str)
        self.prev_crew = []

    def get_social_score(self, candidate, current_crew):
        return sum(self.pair_history[tuple(sorted((candidate, m)))] for m in current_crew)

    def record_pairs(self, crew):
        u_crew = list(set(crew))
        for i in range(len(u_crew)):
            for j in range(i+1, len(u_crew)):
                self.pair_history[tuple(sorted((u_crew[i], u_crew[j])))] += 1

    def get_candidate(self, role_col, role_label, unavailable, current_crew):
        if role_col not in self.df.columns: return ""
        candidates = self.df[self.df[role_col].astype(str).str.strip() != ""]['name'].tolist()
        
        # Filter
        available = [p for p in candidates if p not in unavailable and p not in current_crew and p not in self.prev_crew]
        if not available: 
            available = [p for p in candidates if p not in unavailable and p not in current_crew]
        
        if not available: return ""

        # Weighting: 1. Load, 2. Role Variety (Penalty), 3. Social Clique (Penalty), 4. Random
        available.sort(key=lambda x: (
            self.load[x],
            1 if self.last_role[x] == role_label else 0,
            self.get_social_score(x, current_crew),
            random.random()
        ))
        
        selected = available[0]
        self.load[selected] += 1
        self.last_role[selected] = role_label
        return selected

    def assign_lead(self, crew):
        if not crew: return ""
        # Priority Leads
        leads = [p for p in crew if any(pl in p.lower() for pl in CONFIG.PRIMARY_LEADS)]
        if leads:
            leads.sort(key=lambda x: self.lead_load[x])
            self.lead_load[leads[0]] += 1
            return leads[0]
        # Fallback Leads
        if 'team lead' in self.df.columns:
            fallback = []
            for p in crew:
                row = self.df[self.df['name'] == p]
                if not row.empty and str(row.iloc[0]['team lead']).strip() != "":
                    fallback.append(p)
            if fallback:
                fallback.sort(key=lambda x: self.lead_load[x])
                self.lead_load[fallback[0]] += 1
                return fallback[0]
        return ""

# ==========================================
# 5. UI RENDERERS (THE STEVE JOBS PART)
# ==========================================

def render_apple_header(title, subtitle=None):
    st.markdown(f"## {title}")
    if subtitle:
        st.markdown(f"<p style='color:#86868b; margin-top:-10px;'>{subtitle}</p>", unsafe_allow_html=True)
    st.markdown("---")

def render_card_view(df):
    """Renders the roster as a vertical feed of sleek cards."""
    if df is None or df.empty: return

    for _, row in df.iterrows():
        # Parsing data for display
        date_str = row['Service Date']
        # Check if year exists, simple logic
        try:
            dt = datetime.strptime(date_str, "%Y-%m-%d")
            fmt_date = dt.strftime("%A, %b %d")
        except:
            fmt_date = date_str

        details = row.get('Details', '')
        
        # Build HTML for Roles
        roles_html = ""
        
        # 1. Lead (Highlighted)
        lead = row.get('Team Lead', '')
        if lead:
            roles_html += f"""
            <div class="role-row">
                <div class="role-label" style="color:#007aff;">Team Lead</div>
                <div class="role-value">{lead}</div>
            </div>
            """
            
        # 2. Tech Roles
        tech_roles = [r['label'] for r in CONFIG.ROLES] + ["Cam 2"]
        for role in tech_roles:
            val = row.get(role, "")
            val_html = f'<div class="role-value">{val}</div>' if val else '<div class="role-value role-empty">Unassigned</div>'
            roles_html += f"""
            <div class="role-row">
                <div class="role-label">{role}</div>
                {val_html}
            </div>
            """

        # Card Container
        st.markdown(f"""
        <div class="service-card">
            <div class="card-date-row">
                <div class="card-date">{fmt_date}</div>
                <div class="card-meta">{details if details else "Main Service"}</div>
            </div>
            {roles_html}
        </div>
        """, unsafe_allow_html=True)

# ==========================================
# 6. APP FLOW
# ==========================================

def main():
    SessionManager.init()
    df_data = DataLoader.fetch_data(CONFIG.SHEET_ID)

    if df_data.empty:
        st.error("Unable to connect to Team Data.")
        return

    # --- PROGRESS INDICATOR (Minimal) ---
    # No giant stepped bars. Just context.

    # ==========================
    # STAGE 1: SET DATE SCOPE
    # ==========================
    if st.session_state.stage == 1:
        render_apple_header("New Schedule", "Select the timeframe for the upcoming roster.")
        
        col1, col2 = st.columns([1,1])
        now = datetime.now()
        with col1:
            year = st.number_input("Year", value=now.year, min_value=2024)
        with col2:
            months = st.multiselect("Months", list(calendar.month_name)[1:], default=[calendar.month_name[(now.month % 12) + 1]])

        if st.button("Continue →", type="primary"):
            # Generate Logic
            dates = []
            m_map = {m: i for i, m in enumerate(calendar.month_name)}
            for m in months:
                mi = m_map[m]
                _, dim = calendar.monthrange(year, mi)
                for d in range(1, dim+1):
                    dt = date(year, mi, d)
                    if dt.weekday() == 6: # Sunday
                        dates.append(dt)
            st.session_state.roster_dates = [{"Date": d, "Details": ""} for d in sorted(dates)]
            st.session_state.stage = 2
            st.rerun()

    # ==========================
    # STAGE 2: DATE CONFIRMATION
    # ==========================
    elif st.session_state.stage == 2:
        render_apple_header("Confirm Dates", "Does this timeline look correct?")
        
        # Instead of raw editor, show a clean list, hide editor in expander
        dates = [d['Date'].strftime("%b %d") for d in st.session_state.roster_dates]
        st.info(f"Scheduled for **{len(dates)}** Sundays: {', '.join(dates)}", icon="📅")
        
        with st.expander("Customize Dates & Details"):
            df_dates = pd.DataFrame(st.session_state.roster_dates)
            df_dates['Date'] = pd.to_datetime(df_dates['Date']).dt.date
            edited = st.data_editor(df_dates, num_rows="dynamic", use_container_width=True)
            
        c1, c2 = st.columns([1, 3])
        if c1.button("Back"):
            st.session_state.stage = 1
            st.rerun()
        if c2.button("Next: Availability →", type="primary"):
            # Save state
            clean = []
            for r in edited.to_dict('records'):
                if r.get('Date'): clean.append(r)
            st.session_state.roster_dates = clean
            st.session_state.stage = 3
            st.rerun()

    # ==========================
    # STAGE 3: UNAVAILABILITY
    # ==========================
    elif st.session_state.stage == 3:
        render_apple_header("Availability", "Who is away?")
        
        all_names = sorted(list(df_data['name'].unique()))
        dates_obj = [d['Date'] for d in st.session_state.roster_dates]
        d_strs = [d.strftime("%Y-%m-%d") for d in dates_obj]
        d_lbls = {d.strftime("%Y-%m-%d"): d.strftime("%d %b") for d in dates_obj}

        if not st.session_state.unavailability:
            st.session_state.unavailability = {n: [] for n in all_names}

        # Clean Form Layout
        with st.form("avail_form", border=False):
            cols = st.columns(2)
            temp = {}
            for i, name in enumerate(all_names):
                with cols[i % 2]:
                    sel = st.multiselect(
                        name, 
                        d_strs, 
                        default=[x for x in st.session_state.unavailability.get(name, []) if x in d_strs],
                        format_func=lambda x: d_lbls[x]
                    )
                    temp[name] = sel
            
            st.markdown("---")
            submitted = st.form_submit_button("✨ Create Schedule", type="primary") # The "Magic" Button
            
            if submitted:
                st.session_state.unavailability = temp
                st.session_state.master_roster = None # Clear old roster
                st.session_state.stage = 4
                st.rerun()

    # ==========================
    # STAGE 4: THE REVEAL
    # ==========================
    elif st.session_state.stage == 4:
        
        # 1. GENERATE (Behind the scenes)
        if st.session_state.master_roster is None:
            engine = RosterEngine(df_data)
            
            # Map unavailability
            unavail_lookup = defaultdict(list)
            for n, ds in st.session_state.unavailability.items():
                for d in ds: unavail_lookup[d].append(n)
            
            rows = []
            crew_tracker = []
            
            for i, d_meta in enumerate(st.session_state.roster_dates):
                d = d_meta['Date']
                d_str = d.strftime("%Y-%m-%d")
                row = {
                    "Service Date": d.strftime("%A, %b %d"), 
                    "RawDate": d_str,
                    "Details": d_meta.get("Details", "")
                }
                
                # Assign
                current_crew = []
                today_unavail = unavail_lookup[d_str]
                
                for role in CONFIG.ROLES:
                    p = engine.get_candidate(role['sheet_col'], role['label'], today_unavail, current_crew)
                    row[role['label']] = p
                    if p: current_crew.append(p)
                
                row["Cam 2"] = ""
                row['Team Lead'] = engine.assign_lead(current_crew)
                
                rows.append(row)
                engine.prev_crew = current_crew
                engine.record_pairs(current_crew)
            
            st.session_state.master_roster = pd.DataFrame(rows)
            st.balloons() # Because it's a celebration

        df = st.session_state.master_roster

        # 2. RENDER THE BEAUTIFUL CARDS
        st.markdown(f"## {CONFIG.PAGE_TITLE}")
        
        # Action Bar
        col_main, col_actions = st.columns([3, 1])
        with col_actions:
            if st.button("Start Over"):
                SessionManager.reset()
                st.rerun()
            if st.button("Regenerate 🔄"):
                st.session_state.master_roster = None
                st.rerun()

        # The Feed
        render_card_view(df)

        # 3. FINE TUNING (Hidden)
        with st.expander("Fine Tune Details (Spreadsheet View)"):
            edited = st.data_editor(df, use_container_width=True)
            if not edited.equals(df):
                st.session_state.master_roster = edited
                st.rerun()
        
        # 4. EXPORT
        st.markdown("---")
        csv = df.to_csv(index=False)
        st.download_button("Download CSV", csv, "roster.csv", "text/csv")
        st.caption("Tip: Press Cmd+P (Mac) or Ctrl+P (Win) to print this page as a PDF.")

if __name__ == "__main__":
    main()
