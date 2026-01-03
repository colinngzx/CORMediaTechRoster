import streamlit as st
import pandas as pd
import random
import calendar
from datetime import datetime, date
from collections import defaultdict
from typing import List, Dict, Tuple
from dataclasses import dataclass

# ==========================================
# 1. CONFIGURATION & STYLES
# ==========================================

@dataclass(frozen=True)
class AppConfig:
    PAGE_TITLE: str = "SWS Roster Wizard"
    # REPLACE WITH YOUR OWN SHEET ID IF NEEDED
    SHEET_ID: str = "1jh6ScfqpHe7rRN1s-9NYPsm7hwqWWLjdLKTYThRRGUo"
    
    # People who should be prioritized for Team Lead if present
    PRIMARY_LEADS: Tuple[str, ...] = ("gavin", "ben", "mich lo") 
    
    # Mapping Config: Label in UI -> Column header in Google Sheet
    ROLES: Tuple[Dict[str, str], ...] = (
        {"label": "Sound Crew",      "sheet_col": "sound"},
        {"label": "Projectionist",   "sheet_col": "projection"},
        {"label": "Stream Director", "sheet_col": "stream director"},
        {"label": "Cam 1",           "sheet_col": "camera"},
    )

CONFIG = AppConfig()

st.set_page_config(
    page_title=CONFIG.PAGE_TITLE, 
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS for the "Excel-like" view
STYLING_CSS = """
<style>
    .roster-header {
        background-color: #4f81bd;
        color: white;
        padding: 10px;
        text-align: center;
        font-weight: bold;
        border: 1px solid #385d8a;
    }
    table.custom-table {
        width: 100%;
        border-collapse: collapse;
        font-family: Calibri, Arial, sans-serif;
        font-size: 14px;
    }
    table.custom-table th {
        background-color: #dce6f1;
        border: 1px solid #8e8e8e;
        padding: 5px;
        color: #1f497d;
    }
    table.custom-table td {
        border: 1px solid #a6a6a6;
        padding: 5px;
        text-align: center;
    }
    .date-row {
        background-color: #f2f2f2; 
        font-weight: bold;
    }
</style>
"""
st.markdown(STYLING_CSS, unsafe_allow_html=True)


# ==========================================
# 2. STATE MANAGEMENT
# ==========================================

class SessionManager:
    """Handles initialization and clearing of Session State."""
    @staticmethod
    def init():
        defaults = {
            'stage': 1,
            'roster_dates': [],
            'unavailability_by_person': {},
            'master_roster_df': None,
        }
        for key, val in defaults.items():
            if key not in st.session_state:
                st.session_state[key] = val

    @staticmethod
    def reset():
        """Hard reset of the app state."""
        for key in list(st.session_state.keys()):
            del st.session_state[key]
        SessionManager.init()


# ==========================================
# 3. DATA & UTILS
# ==========================================

class DataLoader:
    """Handles fetching and cleaning data from Google Sheets."""
    
    @staticmethod
    @st.cache_data(ttl=900) # Cache for 15 mins
    def fetch_data(sheet_id: str) -> pd.DataFrame:
        url = f"https://docs.google.com/spreadsheets/d/{sheet_id}/export?format=csv&gid=0"
        try:
            df = pd.read_csv(url).fillna("")
            
            # Normalize Clean Columns: lowercase, strip spaces
            df.columns = df.columns.str.strip().str.lower()
            
            # Common renames to prevent errors
            renames = {
                'stream dire': 'stream director',
                'team le': 'team lead',
                'team leader': 'team lead'
            }
            # Rename if partial match found
            final_cols = {}
            for col in df.columns:
                for k, v in renames.items():
                    if k in col: final_cols[col] = v
            
            df.rename(columns=final_cols, inplace=True)
            
            if 'name' not in df.columns:
                st.error("❌ CRTICAL ERROR: Could not find a 'Name' column in the Google Sheet.")
                return pd.DataFrame()
                
            return df
        except Exception as e:
            st.error(f"⚠️ Network/Data Error: {e}")
            return pd.DataFrame()

class DateUtils:
    @staticmethod
    def get_upcoming_window() -> Tuple[int, List[str]]:
        """Returns the current year and the next 3 months."""
        now = datetime.now()
        target_year = now.year + 1 if now.month == 12 else now.year
        suggested_months = []
        for i in range(1, 4):
            idx = (now.month + i - 1) % 12 + 1
            suggested_months.append(calendar.month_name[idx])
        return target_year, suggested_months

    @staticmethod
    def generate_sundays(year: int, month_names: List[str]) -> List[date]:
        valid_dates = []
        month_map = {m: i for i, m in enumerate(calendar.month_name) if m}
        
        for m_name in month_names:
            m_idx = month_map.get(m_name)
            if not m_idx: continue
            
            # Find all dates in month
            _, days_in_month = calendar.monthrange(year, m_idx)
            for day in range(1, days_in_month + 1):
                try:
                    curr = date(year, m_idx, day)
                    if curr.weekday() == 6:  # 6 = Sunday
                        valid_dates.append(curr)
                except ValueError:
                    continue
        return sorted(valid_dates)


# ==========================================
# 4. ROSTER ENGINE (UPDATED LOGIC)
# ==========================================

class RosterEngine:
    def __init__(self, people_df: pd.DataFrame):
        self.df = people_df
        # Create list of all unique names, sorted
        self.team_names: List[str] = sorted(
            [n for n in self.df['name'].unique() if str(n).strip() != ""],
            key=lambda x: str(x).lower()
        )
        # Tracking Stats (Load Fairness)
        self.tech_load: Dict[str, int] = defaultdict(int)
        self.lead_load: Dict[str, int] = defaultdict(int)
        self.last_worked_idx: Dict[str, int] = defaultdict(lambda: -99)
        self.prev_week_crew: List[str] = []
        
        # --- LOGIC 1: SOCIAL MIXING ---
        # Track how many times pair ('Ben', 'Gavin') has worked together
        self.pair_history: Dict[Tuple[str, str], int] = defaultdict(int)

        # --- LOGIC 2: ROLE VARIETY ---
        # Track the last Role Label assigned to a person
        self.last_role: Dict[str, str] = defaultdict(str)

    def get_social_score(self, candidate: str, current_crew: List[str]) -> int:
        """Calculates how 'expensive' this candidate is socially based on current crew."""
        score = 0
        for member in current_crew:
            # Create a sorted tuple key so (A, B) is same as (B, A)
            pair_key = tuple(sorted((candidate, member)))
            score += self.pair_history[pair_key]
        return score

    def record_pairs(self, full_crew: List[str]):
        """After a Sunday is full, save the pairs so we remember them next week."""
        # Loop through every unique pair in the list
        unique_crew = list(set(full_crew)) # remove duplicates
        for i in range(len(unique_crew)):
            for j in range(i + 1, len(unique_crew)):
                p1 = unique_crew[i]
                p2 = unique_crew[j]
                pair_key = tuple(sorted((p1, p2)))
                self.pair_history[pair_key] += 1

    def get_candidate(self, role_col: str, role_label: str, unavailable: List[str], current_crew: List[str], week_idx: int) -> str:
        """Finds the best tech candidate using Load + Social Mixing + Role Variety logic."""
        if role_col not in self.df.columns:
            return ""

        # 1. Filter: Capabilities (Based on Google Sheet Column)
        candidates_in_sheet = self.df[self.df[role_col].astype(str).str.strip() != ""]['name'].tolist()
        
        # 2. Filter: Unavailability, Exclusivity, Burnout (Back-to-back weeks)
        available = [
            p for p in candidates_in_sheet
            if p not in unavailable 
            and p not in current_crew 
            and p not in self.prev_week_crew
        ]

        # Soft Constraint Fallback: If no one found, allow people who worked last week
        if not available:
            available = [
                p for p in candidates_in_sheet
                if p not in unavailable and p not in current_crew
            ]
        
        if not available:
            return "" # No one available

        # 3. SELECTION LOGIC (The Sorting Hat)
        # We sort the available list. The person at index 0 wins.
        # Priority 1: Who has the fewest shifts so far? (Fairness)
        # Priority 2: Did they do this exact role last time? (Role Variety penalty)
        # Priority 3: Have they worked with the current crew a lot? (Social Mixing penalty)
        # Priority 4: Random Fuzz (avoid alphabetical bias)
        
        available.sort(key=lambda x: (
            self.tech_load[x],                              # Priority 1
            1 if self.last_role[x] == role_label else 0,    # Priority 2 (Penalty=1 if same role)
            self.get_social_score(x, current_crew),         # Priority 3
            random.uniform(0, 1)                            # Priority 4
        ))
        
        selected = available[0]
        self.tech_load[selected] += 1
        self.last_worked_idx[selected] = week_idx
        
        # Save this role as their "last role"
        self.last_role[selected] = role_label
        
        return selected

    def assign_lead(self, current_crew: List[str], week_idx: int) -> str:
        """Assigns a Team Lead from the current assigned crew."""
        if not current_crew: return ""

        # 1. Look for Primary Leads (defined in Config)
        primaries_present = [
            p for p in current_crew 
            if any(pl.lower() in p.lower() for pl in CONFIG.PRIMARY_LEADS)
        ]
        
        if primaries_present:
            # Pick primary who has done it least
            primaries_present.sort(key=lambda x: self.lead_load[x])
            selected = primaries_present[0]
            self.lead_load[selected] += 1
            return selected

        # 2. Look for anyone marked as 'Team Lead' capable in sheet
        if 'team lead' in self.df.columns:
            capable_leads = []
            for person in current_crew:
                # Check row for this person
                row = self.df[self.df['name'] == person]
                if not row.empty and str(row.iloc[0]['team lead']).strip() != "":
                    capable_leads.append(person)
            
            if capable_leads:
                capable_leads.sort(key=lambda x: self.lead_load[x])
                best_fallback = capable_leads[0]
                self.lead_load[best_fallback] += 1
                return best_fallback

        return "" # No qualified lead in crew

    def calculate_stats(self, roster_df: pd.DataFrame) -> pd.DataFrame:
        """Reads the final roster and counts shifts per person."""
        stats = {n: {'Tech': 0, 'Lead': 0} for n in self.team_names}
        
        # Tech cols + Cam 2
        tech_cols = [r['label'] for r in CONFIG.ROLES] + ["Cam 2"]
        
        for _, row in roster_df.iterrows():
            # Count Tech
            for col in tech_cols:
                if col in row:
                    name = str(row[col]).strip()
                    if name in stats: stats[name]['Tech'] += 1
            # Count Lead
            if "Team Lead" in row:
                name = str(row["Team Lead"]).strip()
                if name in stats: stats[name]['Lead'] += 1
        
        # Convert to displayable format
        rows = []
        for name, data in stats.items():
            total = data['Tech'] + data['Lead']
            if total > 0:
                rows.append({
                    "Name": name, 
                    "Tech Shifts": data['Tech'], 
                    "Lead Shifts": data['Lead'], 
                    "Total": total
                })
        
        if not rows: return pd.DataFrame(columns=["Name", "Total"])
        return pd.DataFrame(rows).sort_values("Name")


# ==========================================
# 5. UI RENDERERS
# ==========================================

class RosterRenderer:
    @staticmethod
    def render_month_html(month_name: str, df: pd.DataFrame) -> str:
        """Generates a clean HTML table for the 'Copy' view."""
        if df.empty: return ""
        
        html = f"""
        <div class="roster-card">
            <div class="roster-header">{month_name}</div>
            <table class="custom-table">
                <thead>
                    <tr>
                        <th style="width: 150px;">Role \ Date</th>
                        {"".join(f'<th class="date-row">{d}</th>' for d in df.columns)}
                    </tr>
                </thead>
                <tbody>
        """
        
        for idx, row in df.iterrows():
            html += f"<tr><td><strong>{idx}</strong></td>"
            for cell in row:
                html += f"<td>{cell}</td>"
            html += "</tr>"
            
        html += """
                </tbody>
            </table>
        </div><br>
        """
        return html


# ==========================================
# 6. APP STEPS
# ==========================================

def render_step_1_dates():
    st.header("Step 1: Select Service Dates")
    with st.container(border=True):
        col1, col2 = st.columns(2)
        with col1:
            def_year, def_months = DateUtils.get_upcoming_window()
            year = st.number_input("Year", value=def_year, min_value=2024)
        with col2:
            months = st.multiselect("Months", list(calendar.month_name)[1:], default=def_months)

        if st.button("Generate Date List", type="primary"):
            dates = DateUtils.generate_sundays(year, months)
            st.session_state.roster_dates = [
                {"Date": d, "Combined": False, "HC": False, "Notes": ""} for d in dates
            ]
            st.session_state.stage = 2
            st.rerun()

def render_step_2_details():
    st.header("Step 2: Service Details")
    st.info("Check dates below. Add special notes (e.g., 'Combined') or remove dates.")
    
    # --- ADD DATE BUTTON ---
    col_date, col_btn = st.columns([3, 1])
    with col_date:
        new_date = st.date_input("Manual Date Add", value=None, label_visibility="collapsed")
    with col_btn:
        if st.button("➕ Add This Date"):
            if new_date:
                st.session_state.roster_dates.append({
                    "Date": new_date, "Combined": False, "HC": False, "Notes": ""
                })
                st.session_state.roster_dates.sort(key=lambda x: str(x['Date']) if x['Date'] else "")
                st.rerun()
    # -----------------------

    # Editor logic
    df_dates = pd.DataFrame(st.session_state.roster_dates)
    if not df_dates.empty:
        df_dates['Date'] = pd.to_datetime(df_dates['Date']).dt.date
    
    edited_df = st.data_editor(
        df_dates,
        column_config={
            "Date": st.column_config.DateColumn("Service Date", format="DD-MMM", required=True),
        },
        num_rows="dynamic",
        use_container_width=True,
        key="date_editor_widget"
    )
    
    col_back, col_next = st.columns([1, 4])
    if col_back.button("← Back"):
        st.session_state.stage = 1
        st.rerun()
    if col_next.button("Next: Availability →", type="primary"):
        clean_records = []
        for r in edited_df.to_dict('records'):
            if r.get('Date'): clean_records.append(r)
            
        st.session_state.roster_dates = clean_records
        st.session_state.stage = 3
        st.rerun()

def render_step_3_unavailability(all_names: List[str]):
    st.header("Step 3: Unavailability")
    st.markdown("Select dates where a person is **NOT** available.")
    
    roster_dates = [d['Date'] for d in st.session_state.roster_dates if d.get('Date')]
    roster_dates.sort()
    
    date_map = {d.strftime("%Y-%m-%d"): d for d in roster_dates}
    date_strs = list(date_map.keys())

    if not st.session_state.unavailability_by_person:
        st.session_state.unavailability_by_person = {name: [] for name in all_names}

    with st.form("availability_form", border=True):
        cols = st.columns(3)
        temp_selections = {}
        
        for i, name in enumerate(all_names):
            with cols[i % 3]:
                current_vals = st.session_state.unavailability_by_person.get(name, [])
                valid_vals = [v for v in current_vals if v in date_strs]
                
                selected = st.multiselect(
                    f"{name}", 
                    options=date_strs, 
                    default=valid_vals,
                    format_func=lambda x: date_map[x].strftime("%d-%b")
                )
                temp_selections[name] = selected
        
        submitted = st.form_submit_button("Generate Roster", type="primary")
        if submitted:
            st.session_state.unavailability_by_person = temp_selections
            st.session_state.master_roster_df = None
            st.session_state.stage = 4
            st.rerun()

    if st.button("← Back"):
        st.session_state.stage = 2
        st.rerun()

def render_step_4_final(people_df: pd.DataFrame):
    st.header("Step 4: Roster Dashboard")
    
    # Self-healing state
    if st.session_state.master_roster_df is not None:
        if '_month' not in st.session_state.master_roster_df.columns:
            st.session_state.master_roster_df = None

    # --- 1. ROSTER GENERATION LOGIC ---
    if st.session_state.master_roster_df is None:
        engine = RosterEngine(people_df)
        
        unavailable_lookup = defaultdict(list)
        for name, dates_str in st.session_state.unavailability_by_person.items():
            for d_str in dates_str:
                unavailable_lookup[d_str].append(name)

        roster_rows = []
        
        for idx, date_meta in enumerate(st.session_state.roster_dates):
            d_raw = date_meta.get('Date')
            if not d_raw: continue
            
            if isinstance(d_raw, str):
                try: d_obj = datetime.strptime(d_raw, "%Y-%m-%d").date()
                except: d_obj = pd.to_datetime(d_raw).date()
            else:
                d_obj = d_raw

            # Metadata Display
            details_parts = []
            if date_meta.get('Combined'): details_parts.append("Combined")
            if date_meta.get('HC'): details_parts.append("HC")
            if date_meta.get('Notes'): details_parts.append(date_meta['Notes'])
            details_str = " / ".join(details_parts)
            
            d_str_key = d_obj.strftime("%Y-%m-%d")
            unavailable_today = unavailable_lookup.get(d_str_key, [])
            
            row_data = {
                "Service Date": d_obj.strftime("%d-%b"),
                "_month": d_obj.strftime("%B %Y"),
                "Details": details_str
            }
            
            current_crew = []
            
            # --- ASSIGN TECH ROLES ---
            for role in CONFIG.ROLES:
                person = engine.get_candidate(
                    role['sheet_col'], 
                    role['label'],          # Pass Label for "Role Variety" logic
                    unavailable_today, 
                    current_crew, 
                    idx
                )
                row_data[role['label']] = person
                if person: current_crew.append(person)
            
            # Assign Misc / Lead
            row_data["Cam 2"] = ""
            row_data["Team Lead"] = engine.assign_lead(current_crew, idx)
            
            roster_rows.append(row_data)
            engine.prev_week_crew = current_crew 
            
            # --- RECORD SOCIAL PAIRS FOR NEXT DATE ---
            engine.record_pairs(current_crew) # Prevents "Cliques"
        
        if roster_rows:
            st.session_state.master_roster_df = pd.DataFrame(roster_rows)
        else:
            st.session_state.master_roster_df = pd.DataFrame(
                columns=["Service Date", "_month", "Details", "Team Lead", "Cam 2"]
            )

    master_df = st.session_state.master_roster_df

    if master_df.empty:
        st.warning("No dates found to roster. Please go back to Step 1.")
        if st.button("Start Over"): SessionManager.reset(); st.rerun()
        return

    # --- 2. EDITING INTERFACE ---
    row_order = ["Details"] + [r['label'] for r in CONFIG.ROLES] + ["Cam 2", "Team Lead"]
    
    st.subheader("✏️ Editor")
    
    has_edits = False
    if '_month' in master_df.columns:
        months = master_df['_month'].unique()
    else:
        months = []

    for month in months:
        with st.expander(f"Edit {month}", expanded=True):
            sub = master_df[master_df['_month'] == month].copy()
            sub.set_index("Service Date", inplace=True)
            view_df = sub[row_order].T
            
            edited_view = st.data_editor(
                view_df, 
                use_container_width=True, 
                key=f"editor_{month}"
            )
            
            if not edited_view.equals(view_df):
                for d_col in edited_view.columns:
                    for role_row in edited_view.index:
                        new_val = edited_view.at[role_row, d_col]
                        mask = (master_df['Service Date'] == d_col) & (master_df['_month'] == month)
                        if mask.any():
                            master_df.loc[mask, role_row] = new_val
                has_edits = True

    if has_edits:
        st.session_state.master_roster_df = master_df
        st.rerun()

    # --- 3. COPY VIEW ---
    st.markdown("---")
    st.subheader("📋 Final List")
    
    csv_buffers = []
    
    for month in months:
        sub = master_df[master_df['_month'] == month].copy()
        sub.set_index("Service Date", inplace=True)
        display_df = sub[row_order].T 
        
        st.markdown(
            RosterRenderer.render_month_html(month, display_df), 
            unsafe_allow_html=True
        )
        
        display_df.index.name = "Role"
        csv_buffers.append(f"\n{month}\n")
        csv_buffers.append(display_df.to_csv())

    # --- 4. LIVE LOAD STATS ---
    st.markdown("---")
    with st.expander("📊 Live Load Statistics", expanded=False):
        stats_engine = RosterEngine(people_df)
        stats_df = stats_engine.calculate_stats(master_df)
        st.dataframe(stats_df, use_container_width=True, hide_index=True)

    # --- 5. FOOTER ACTIONS ---
    st.markdown("---")
    c1, c2, c3, c4 = st.columns(4)
    
    if c1.button("← Configuration"):
        st.session_state.stage = 3
        st.rerun()
        
    if c2.button("🔄 Regenerate All"):
        st.session_state.master_roster_df = None
        st.rerun()
        
    full_csv = "\n".join(csv_buffers)
    c3.download_button(
        label="💾 Download CSV",
        data=full_csv,
        file_name=f"roster_{datetime.now().strftime('%Y-%m-%d')}.csv",
        mime="text/csv",
        type="primary"
    )
    
    if c4.button("Start Over"):
        SessionManager.reset()
        st.rerun()

# ==========================================
# 7. MAIN ENTRY POINT
# ==========================================

def main():
    SessionManager.init()
    
    df_team = DataLoader.fetch_data(CONFIG.SHEET_ID)
    
    if df_team.empty:
        st.warning("Please check your Google Sheet ID or Internet Connection.")
        if st.button("Retry Connection"):
            st.cache_data.clear()
            st.rerun()
        return

    all_names = sorted(
        [n for n in df_team['name'].unique() if str(n).strip() != ""], 
        key=lambda x: str(x).lower()
    )

    if st.session_state.stage == 1:
        render_step_1_dates()
    elif st.session_state.stage == 2:
        render_step_2_details()
    elif st.session_state.stage == 3:
        render_step_3_unavailability(all_names)
    elif st.session_state.stage == 4:
        render_step_4_final(df_team)

if __name__ == "__main__":
    main()
