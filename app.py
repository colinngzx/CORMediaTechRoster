import streamlit as st
import pandas as pd
import random
import calendar
from datetime import datetime, date
from collections import defaultdict
from typing import List, Dict, Tuple, NamedTuple
from dataclasses import dataclass

# ==========================================
# 1. CONFIGURATION
# ==========================================

@dataclass(frozen=True)
class AppConfig:
    PAGE_TITLE: str = "SWS Roster Wizard"
    # Your specific Sheet ID
    SHEET_ID: str = "1jh6ScfqpHe7rRN1s-9NYPsm7hwqWWLjdLKTYThRRGUo"
    
    # Priority for Team Lead assignments:
    PRIMARY_LEADS: Tuple[str, ...] = ("gavin", "ben", "mich lo")
    
    # Roster Roles Configuration
    ROLES: Tuple[Dict[str, str], ...] = (
        {"label": "Sound Crew",      "sheet_col": "sound"},
        {"label": "Projectionist",   "sheet_col": "projection"},
        {"label": "Stream Director", "sheet_col": "stream director"},
        {"label": "Cam 1",           "sheet_col": "camera"},
    )

CONFIG = AppConfig()

st.set_page_config(page_title=CONFIG.PAGE_TITLE, layout="wide")

# ==========================================
# 2. HELPER CLASSES & FUNCTIONS
# ==========================================

class RosterDateSpec(NamedTuple):
    date_obj: date
    is_hc: bool
    is_combined: bool
    notes: str

    @property
    def service_type_details(self) -> str:
        parts = []
        if self.is_combined: parts.append("MSS Combined")
        if self.is_hc: parts.append("HC")
        if self.notes: parts.append(self.notes)
        return " / ".join(parts) if parts else "Regular SWS"

class DateUtils:
    @staticmethod
    def get_default_window() -> Tuple[int, List[str]]:
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
            _, days_in_month = calendar.monthrange(year, m_idx)
            for day in range(1, days_in_month + 1):
                try:
                    curr = date(year, m_idx, day)
                    if curr.year == year and curr.weekday() == 6:  # 6 = Sunday
                        valid_dates.append(curr)
                except ValueError:
                    continue
        return sorted(valid_dates)

# ==========================================
# 3. ROSTER LOGIC ENGINE
# ==========================================

class RosterEngine:
    def __init__(self, df: pd.DataFrame):
        self.df = df
        self.team_names: List[str] = sorted(df['name'].unique().tolist(), key=lambda x: str(x).lower())
        self.tech_load: Dict[str, int] = {name: 0 for name in self.team_names}
        self.lead_load: Dict[str, int] = {name: 0 for name in self.team_names}
        self.last_worked_idx: Dict[str, int] = {name: -999 for name in self.team_names}
        self.prev_week_crew: List[str] = []

    def _update_stats(self, person: str, role_type: str, week_idx: int):
        if role_type == "tech":
            self.tech_load[person] = self.tech_load.get(person, 0) + 1
        elif role_type == "lead":
            self.lead_load[person] = self.lead_load.get(person, 0) + 1
        self.last_worked_idx[person] = week_idx

    def get_tech_candidate(self, role_col: str, unavailable: List[str], current_crew: List[str], week_idx: int) -> str:
        if role_col not in self.df.columns: return ""
        mask = self.df[role_col].astype(str).str.strip().str.lower() == 'yes'
        candidates = self.df[mask]['name'].tolist()
        
        available_pool = [
            p for p in candidates 
            if p not in unavailable 
            and p not in current_crew 
            and p not in self.prev_week_crew
        ]

        if not available_pool: 
            available_pool = [
                p for p in candidates 
                if p not in unavailable 
                and p not in current_crew
            ]

        if not available_pool: return ""

        random.shuffle(available_pool) 
        available_pool.sort(key=lambda x: (self.tech_load.get(x, 0), self.last_worked_idx.get(x, -999)))
        
        selected = available_pool[0]
        self._update_stats(selected, "tech", week_idx)
        return selected

    def assign_lead(self, current_crew: List[str], unavailable: List[str], week_idx: int) -> str:
        crew_present = [p for p in current_crew if p]
        primaries = [p for p in crew_present if any(lead.lower() in p.lower() for lead in CONFIG.PRIMARY_LEADS)]
        
        if primaries:
            primaries.sort(key=lambda x: (self.lead_load.get(x, 0), self.last_worked_idx.get(x, -999)))
            selected = primaries[0]
            self._update_stats(selected, "lead", week_idx)
            return selected

        fallbacks = []
        if 'team lead' in self.df.columns:
            for person in crew_present:
                person_row = self.df[self.df['name'] == person]
                if not person_row.empty:
                    val = str(person_row.iloc[0]['team lead']).strip().lower()
                    if val == 'yes':
                        fallbacks.append(person)
        
        if fallbacks:
            fallbacks.sort(key=lambda x: self.lead_load.get(x, 0))
            selected = fallbacks[0]
            self._update_stats(selected, "lead", week_idx)
            return selected
        return ""

# ==========================================
# 4. DATA FETCH
# ==========================================

@st.cache_data(ttl=600)
def fetch_roster_data() -> pd.DataFrame:
    url = f"https://docs.google.com/spreadsheets/d/{CONFIG.SHEET_ID}/export?format=csv&gid=0"
    try:
        df = pd.read_csv(url).fillna("")
        df.columns = df.columns.str.strip().str.lower()
        if 'name' not in df.columns:
            st.error("Could not find a 'name' column in your Google Sheet.")
            return pd.DataFrame()
        if 'status' in df.columns:
            df = df[(df['status'].str.lower() == 'active') | (df['status'] == '')]
        df['name'] = df['name'].str.strip().astype(str)
        return df
    except Exception as e:
        st.error("⚠️ Connection Error")
        st.warning(f"Unable to read the Google Sheet. Error details: {e}")
        return pd.DataFrame()

# ==========================================
# 5. UI FLOW
# ==========================================

def main():
    st.title("🎛️ SWS Roster Wizard")
    
    if 'stage' not in st.session_state: st.session_state.stage = 1
    if 'roster_dates' not in st.session_state: st.session_state.roster_dates = []
    if 'unavailability_by_person' not in st.session_state: st.session_state.unavailability_by_person = {}
    
    df_team = fetch_roster_data()
    if df_team.empty: st.stop()
    
    all_names = sorted(df_team['name'].unique().tolist(), key=lambda x: str(x).lower())

    # --- STEP 1: SELECT DATE RANGE ---
    if st.session_state.stage == 1:
        st.header("Step 1: Select Service Dates")
        col1, col2 = st.columns(2)
        with col1:
            def_year, def_months = DateUtils.get_default_window()
            year = st.number_input("Year", value=def_year, min_value=2024, max_value=2030)
        with col2:
            months = st.multiselect("Months", list(calendar.month_name)[1:], default=def_months)

        if st.button("Generate Date List"):
            dates = DateUtils.generate_sundays(year, months)
            st.session_state.roster_dates = [
                {"Date": d, "Combined": False, "HC": False, "Notes": ""} for d in dates
            ]
            st.session_state.stage = 2
            st.rerun()

    # --- STEP 2: CONFIGURE SERVICES ---
    elif st.session_state.stage == 2:
        st.header("Step 2: Service Details")
        st.info("Edit details below. Use the tabs below to Add or Remove dates.")
        
        df_dates = pd.DataFrame(st.session_state.roster_dates)
        if 'Notes' not in df_dates.columns: df_dates['Notes'] = ""
        df_dates['Notes'] = df_dates['Notes'].fillna("").astype(str)
        if not df_dates.empty and 'Date' in df_dates.columns:
            df_dates['Date'] = pd.to_datetime(df_dates['Date']).dt.date
        
        edited_df = st.data_editor(
            df_dates,
            column_config={
                "Date": st.column_config.DateColumn("Service Date", format="DD-MMM", required=True),
                "Combined": st.column_config.CheckboxColumn("MSS Combined?", default=False),
                "HC": st.column_config.CheckboxColumn("Holy Communion?", default=False),
                "Notes": st.column_config.TextColumn("Notes"),
            },
            num_rows="dynamic",
            use_container_width=True,
            hide_index=True,
            key="date_editor"
        )
        
        st.write("### Manage Dates")
        with st.container(border=True):
            tab_add, tab_remove = st.tabs(["➕ Add Date", "🗑️ Remove Date"])
            with tab_add:
                c1, c2 = st.columns([1, 1])
                with c1: new_date = st.date_input("Select Date", key="add_picker")
                with c2:
                    st.write(" ") 
                    st.write(" ") 
                    if st.button("Add Date"):
                        current_data = edited_df.to_dict('records')
                        if not any(d.get('Date') == new_date for d in current_data if d.get('Date')):
                            current_data.append({"Date": new_date, "Combined": False, "HC": False, "Notes": ""})
                            current_data.sort(key=lambda x: x['Date'] if x.get('Date') else date.max)
                            st.session_state.roster_dates = current_data
                            st.rerun()

            with tab_remove:
                valid_dates = sorted([d['Date'] for d in edited_df.to_dict('records') if d.get('Date')])
                if valid_dates:
                    c1, c2 = st.columns([1, 1])
                    with c1: date_to_remove = st.selectbox("Select Date", valid_dates, format_func=lambda x: x.strftime("%d-%b"))
                    with c2:
                        st.write(" ")
                        st.write(" ")
                        if st.button("Delete Date", type="primary"):
                            current_data = edited_df.to_dict('records')
                            updated_data = [row for row in current_data if row.get('Date') != date_to_remove]
                            st.session_state.roster_dates = updated_data
                            st.rerun()

        st.markdown("---")
        col_l, col_r = st.columns([1, 5])
        if col_l.button("← Back"):
            st.session_state.stage = 1
            st.rerun()
        if col_r.button("Next: Availability →"):
            cleaned_rows = []
            for r in edited_df.to_dict('records'):
                if r.get('Date') and pd.notnull(r['Date']):
                    if isinstance(r['Date'], pd.Timestamp): r['Date'] = r['Date'].date()
                    r['Notes'] = str(r.get('Notes', '')).strip()
                    cleaned_rows.append(r)
            cleaned_rows.sort(key=lambda x: x['Date'])
            st.session_state.roster_dates = cleaned_rows
            st.session_state.stage = 3
            st.rerun()

    # --- STEP 3: UNAVAILABILITY ---
    elif st.session_state.stage == 3:
        st.header("Step 3: Unavailability")
        date_options = [r['Date'] for r in st.session_state.roster_dates]
        date_map = {str(d): d for d in date_options}
        sorted_date_keys = sorted(list(date_map.keys()))

        with st.form("avail_form_names"):
            if not st.session_state.unavailability_by_person:
                 st.session_state.unavailability_by_person = {name: [] for name in all_names}
            user_selections = {}
            cols = st.columns(3)
            for i, name in enumerate(all_names):
                with cols[i % 3]:
                    current_sel = st.session_state.unavailability_by_person.get(name, [])
                    valid_defaults = [str(d) for d in current_sel if str(d) in sorted_date_keys]
                    selected_strs = st.multiselect(
                        f"🚫 {name}", 
                        options=sorted_date_keys, 
                        default=valid_defaults, 
                        format_func=lambda x: date_map[x].strftime("%d-%b")
                    )
                    user_selections[name] = selected_strs
            st.markdown("---")
            if st.form_submit_button("Generate Roster"):
                st.session_state.unavailability_by_person = user_selections
                st.session_state.stage = 4
                st.rerun()
        if st.button("← Back"):
            st.session_state.stage = 2
            st.rerun()

    # --- STEP 4: FINAL ROSTER (TRANSPOSED VIEW) ---
    elif st.session_state.stage == 4:
        st.header("Step 4: Roster Review")
        
        # Sidebar for Names Reference since Dropdowns aren't supported in transposed view
        with st.sidebar:
            st.info("📝 **Name List Reference**")
            st.caption("Copy-paste names if needed:")
            st.code("\n".join(all_names), language="text")

        # 1. GENERATE ROSTER ONCE (Stored as Row=Date)
        if 'master_roster_df' not in st.session_state:
            unavailable_by_date_str = defaultdict(list)
            for name, unavailable_dates in st.session_state.unavailability_by_person.items():
                for d_str in unavailable_dates:
                    unavailable_by_date_str[d_str].append(name)
            
            engine = RosterEngine(df_team)
            raw_schedule = []

            for idx, r_data in enumerate(st.session_state.roster_dates):
                d_obj = r_data['Date']
                n_val = str(r_data.get('Notes', "")).strip()
                spec = RosterDateSpec(d_obj, r_data['HC'], r_data['Combined'], n_val)
                d_str_key = str(d_obj)
                unavailable_today = unavailable_by_date_str.get(d_str_key, [])
                
                current_crew = []
                date_entry = {
                    "Service Date": d_obj.strftime("%d-%b"), 
                    "_month_group": d_obj.strftime("%B %Y"),
                    "Details": spec.service_type_details, 
                    # "Notes": spec.notes # Combined into Details for the view
                }
                
                # Assign Roles
                for role_conf in CONFIG.ROLES:
                    person = engine.get_tech_candidate(
                        role_conf['sheet_col'], unavailable_today, current_crew, idx
                    )
                    date_entry[role_conf['label']] = person
                    if person: current_crew.append(person)
                
                date_entry["Cam 2"] = "" 
                t_lead = engine.assign_lead(current_crew, unavailable_today, idx)
                date_entry["Team Lead"] = t_lead
                
                raw_schedule.append(date_entry)
                engine.prev_week_crew = current_crew

            df_schedule = pd.DataFrame(raw_schedule)
            st.session_state.master_roster_df = df_schedule

        # 2. HELPER: STATS
        def recalculate_live_stats(current_df, all_team_members):
            tech_roles = ["Sound Crew", "Projectionist", "Stream Director", "Cam 1", "Cam 2"]
            lead_roles = ["Team Lead"]
            
            name_map = {n.lower().strip(): n for n in all_team_members}
            stats = {name: {'Tech': 0, 'Lead': 0} for name in all_team_members}
            
            for col in current_df.columns:
                if col in tech_roles or col in lead_roles:
                    for val in current_df[col]:
                        val_str = str(val).strip().lower()
                        if val_str in name_map:
                            real_name = name_map[val_str]
                            if col in tech_roles: stats[real_name]['Tech'] += 1
                            if col in lead_roles: stats[real_name]['Lead'] += 1

            data_out = []
            for name, counts in stats.items():
                total = counts['Tech'] + counts['Lead']
                if total > 0:
                    data_out.append({
                        "Name": name, 
                        "Tech Shifts": counts['Tech'], 
                        "Lead Shifts": counts['Lead'], 
                        "Total": total
                    })
            if not data_out: return pd.DataFrame(columns=["Name", "Total"])
            return pd.DataFrame(data_out).sort_values("Name")

        # 3. DISPLAY LOGIC (Rotated View)
        master_df = st.session_state.master_roster_df
        
        # Ensure define row order for the display
        display_rows_order = ["Details", "Sound Crew", "Projectionist", "Stream Director", "Cam 1", "Cam 2", "Team Lead"]
        
        unique_months = master_df['_month_group'].unique()
        has_changes = False

        for month in unique_months:
            st.subheader(month)
            
            # Extract month data
            month_mask = master_df['_month_group'] == month
            month_subset = master_df[month_mask].copy()
            
            # --- TRANSPOSE LOGIC ---
            # 1. Set Date as Index
            month_subset = month_subset.set_index("Service Date")
            
            # 2. Select only the columns we want as rows
            view_subset = month_subset[display_rows_order]
            
            # 3. Transpose: Now Index=Roles, Columns=Dates
            transposed_view = view_subset.T
            
            # 4. Display Editor strings only (Note: Dropdowns not possible in mixed-type transposed view)
            edited_transposed = st.data_editor(
                transposed_view,
                use_container_width=True,
                key=f"editor_{month}"
            )
            
            # --- SYNC BACK LOGIC ---
            # If changed, rotate back and update master
            if not edited_transposed.equals(transposed_view):
                # Rotate back: Index=Date, Columns=Roles
                reverted_df = edited_transposed.T.reset_index()
                
                # Update specific rows in master_df based on Date matching
                for _, row in reverted_df.iterrows():
                    d_val = row['Service Date']
                    # Find index in master where Service Date matches
                    idx_in_master = master_df.index[master_df['Service Date'] == d_val]
                    if not idx_in_master.empty:
                        idx = idx_in_master[0]
                        for col in display_rows_order:
                            master_df.at[idx, col] = row[col]
                has_changes = True

        if has_changes:
            st.session_state.master_roster_df = master_df
            st.rerun()

        # 4. STATS & DOWNLOAD (Based on the internal Master DF)
        st.markdown("---")
        with st.expander("📊 Live Load Statistics", expanded=True):
            live_stats = recalculate_live_stats(master_df, all_names)
            st.dataframe(live_stats, use_container_width=True)

        st.markdown("---")
        
        # For download, we probably want the Rotated view as CSV?
        # Let's create a full rotated CSV for the user
        full_rotated = master_df.set_index("Service Date")[display_rows_order].T
        csv = full_rotated.to_csv().encode('utf-8')
        
        c1, c2 = st.columns(2)
        with c1: 
            st.download_button("📥 Download Roster (CSV)", csv, "roster_final.csv", "text/csv")
        with c2: 
            if st.button("Start Over"):
                keys_to_del = ['stage', 'roster_dates', 'unavailability_by_person', 'master_roster_df']
                for k in keys_to_del:
                    if k in st.session_state: del st.session_state[k]
                st.session_state.stage = 1
                st.rerun()

if __name__ == "__main__":
    main()
