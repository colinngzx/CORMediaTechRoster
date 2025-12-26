import streamlit as st
import pandas as pd
import random
import calendar
from datetime import datetime, date
from collections import defaultdict
from typing import List, Dict, Tuple, NamedTuple
from dataclasses import dataclass
import io

# ==========================================
# 1. CONFIGURATION
# ==========================================

@dataclass(frozen=True)
class AppConfig:
    PAGE_TITLE: str = "SWS Roster Wizard"
    
    # YOUR GOOGLE SHEET ID
    SHEET_ID: str = "1jh6ScfqpHe7rRN1s-9NYPsm7hwqWWLjdLKTYThRRGUo"
    
    # Priority for Team Lead assignments
    PRIMARY_LEADS: Tuple[str, ...] = ("gavin", "ben", "mich lo")
    
    # Mapping App Roles to YOUR Google Sheet Columns (lowercased)
    ROLES: Tuple[Dict[str, str], ...] = (
        {"label": "Sound Crew",      "sheet_col": "sound"},
        {"label": "Projectionist",   "sheet_col": "projection"},
        {"label": "Stream Director", "sheet_col": "stream director"},
        {"label": "Cam 1",           "sheet_col": "camera"},
    )

CONFIG = AppConfig()

st.set_page_config(page_title=CONFIG.PAGE_TITLE, layout="wide")

# ==========================================
# 2. HELPER CLASSES & STATE
# ==========================================

if 'step' not in st.session_state:
    st.session_state.step = 1
if 'roster_results' not in st.session_state:
    st.session_state.roster_results = None

class RosterDateSpec(NamedTuple):
    date_obj: date
    is_hc: bool
    is_combined: bool
    notes: str

    @property
    def service_type_details(self):
        parts = []
        if self.is_combined: parts.append("MSS Combined")
        if self.is_hc: parts.append("HC")
        if self.notes: parts.append(self.notes)
        return " / ".join(parts)

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
        mask = self.df[role_col].astype(str).str.strip() != ""
        candidates = self.df[mask]['name'].tolist()
        
        # Filter for availability
        available_pool = [
            p for p in candidates 
            if p not in unavailable 
            and p not in current_crew 
            and p not in self.prev_week_crew # Soft rule: avoid back-to-back
        ]

        # Relax soft rule if no one is available
        if not available_pool: 
            available_pool = [
                p for p in candidates 
                if p not in unavailable 
                and p not in current_crew
            ]

        if not available_pool: return ""

        # Randomize first, then sort by load.
        # This adds variety while still respecting fairness.
        random.shuffle(available_pool) 
        available_pool.sort(key=lambda x: (self.tech_load.get(x, 0), self.last_worked_idx.get(x, -999)))
        
        selected = available_pool[0]
        self._update_stats(selected, "tech", week_idx)
        return selected

    def assign_lead(self, current_crew: List[str], unavailable: List[str], week_idx: int) -> str:
        crew_present = [p for p in current_crew if p]
        
        # 1. Try Primary Leads present in crew
        primaries = [p for p in crew_present if any(lead.lower() in p.lower() for lead in CONFIG.PRIMARY_LEADS)]
        if primaries:
            primaries.sort(key=lambda x: (self.lead_load.get(x, 0), self.last_worked_idx.get(x, -999)))
            selected = primaries[0]
            self._update_stats(selected, "lead", week_idx)
            return selected
            
        # 2. Try any crew member capable of leading (assumed everyone in crew list can potential lead if primaries missing)
        # Or you can add specific logic here. For now, pick most experienced from crew.
        if crew_present:
            crew_present.sort(key=lambda x: (self.lead_load.get(x, 0), self.last_worked_idx.get(x, -999)))
            selected = crew_present[0]
            self._update_stats(selected, "lead", week_idx)
            return selected

        return "Unassigned"

    def generate(self, date_specs: List[RosterDateSpec]) -> Tuple[pd.DataFrame, pd.DataFrame]:
        roster_rows = []
        
        for i, spec in enumerate(date_specs):
            week_num = i + 1
            current_crew = []
            
            # 1. Check Unavailability
            day_field = spec.date_obj.strftime("%A").lower() # "sunday"
            date_str = spec.date_obj.strftime("%d-%b")
            
            # Simple unavailability check (if name is in a "Leave" column - optional extension)
            unavailable = [] 

            row_data = {
                "Date": spec.date_obj,
                "Service": spec.service_type_details, 
                "Team Lead": ""
            }

            # 2. Fill Tech Roles
            for role in CONFIG.ROLES:
                person = self.get_tech_candidate(role["sheet_col"], unavailable, current_crew, i)
                row_data[role["label"]] = person
                if person: current_crew.append(person)

            # 3. Assign Lead
            row_data["Team Lead"] = self.assign_lead(current_crew, unavailable, i)
            
            roster_rows.append(row_data)
            self.prev_week_crew = current_crew

        # Create DataFrames
        roster_df = pd.DataFrame(roster_rows)
        
        # Stats DataFrame
        stats_data = []
        for name in self.team_names:
            if self.tech_load[name] > 0 or self.lead_load[name] > 0:
                stats_data.append({
                    "Name": name,
                    "Tech Shifts": self.tech_load[name],
                    "Lead Shifts": self.lead_load[name],
                    "Total": self.tech_load[name] + self.lead_load[name]
                })
        stats_df = pd.DataFrame(stats_data).sort_values("Name")
        
        return roster_df, stats_df

# ==========================================
# 4. APP INTERFACE UTILS
# ==========================================

from streamlit.components.v1 import html
def nav_buttons(prev_idx=None, next_idx=None, next_label="Next"):
    c1, c2, c3 = st.columns([1, 4, 1])
    with c1:
        if prev_idx and st.button("← Back", use_container_width=True):
            st.session_state.step = prev_idx
            st.rerun()
    with c3:
        if next_idx and st.button(f"{next_label} →", type="primary", use_container_width=True):
            st.session_state.step = next_idx
            st.rerun()

# ==========================================
# 5. STAGES
# ==========================================

def render_stage_1_intro():
    st.title("🧙‍♂️ SWS Roster Wizard")
    st.info("Welcome! I'll help you generate the monthly roster based on the Google Sheet data.")
    
    # Load Data
    url = f"https://docs.google.com/spreadsheets/d/{CONFIG.SHEET_ID}/gviz/tq?tqx=out:csv"
    try:
        if 'master_data' not in st.session_state:
            df = pd.read_csv(url)
            # Normalize columns
            df.columns = [c.strip().lower() for c in df.columns]
            # Ensure name exists
            if 'name' not in df.columns:
                st.error("Sheet must have a 'Name' column!")
                return
            st.session_state.master_data = df
        
        st.success(f"Successfully loaded {len(st.session_state.master_data)} team members.")
        
        # Date Setup
        dy, d_months = DateUtils.get_default_window()
        
        st.subheader("Select Roster Period")
        c1, c2 = st.columns(2)
        year = c1.number_input("Year", value=dy)
        months = c2.multiselect("Months", calendar.month_name[1:], default=d_months)
        
        if st.button("Generate Dates →", type="primary"):
            dates = DateUtils.generate_sundays(year, months)
            if not dates:
                st.error("No Sundays found for selection.")
            else:
                st.session_state.target_dates = dates
                st.session_state.step = 2
                st.rerun()
                
    except Exception as e:
        st.error(f"Error loading sheet: {e}")

def render_stage_2_dates():
    st.title("📅 Confirm Service Details")
    st.write("Customize specific Sundays (Combined services, HC, etc.)")
    
    dates = st.session_state.target_dates
    specs = []
    
    with st.form("dates_form"):
        for d in dates:
            cols = st.columns([1, 1, 1, 2])
            cols[0].write(f"**{d.strftime('%d %b %Y')}**")
            hc = cols[1].checkbox("HC", key=f"hc_{d}")
            comb = cols[2].checkbox("Combined", key=f"comb_{d}")
            note = cols[3].text_input("Notes", placeholder="e.g. Special Event", key=f"note_{d}")
            specs.append(RosterDateSpec(d, hc, comb, note))
            
        if st.form_submit_button("Confirm & Generate Roster"):
            st.session_state.date_specs = specs
            st.session_state.step = 3
            st.rerun()
    
    if st.button("← Back"):
        st.session_state.step = 1
        st.rerun()

def render_stage_3_loading():
    st.title("⚙️ Processing...")
    # This stage basically just runs the logic once then moves to result
    # It bridges the gap so we don't re-run logic on every interaction in the result page
    # unless requested.
    
    engine = RosterEngine(st.session_state.master_data)
    roster, stats = engine.generate(st.session_state.date_specs)
    
    st.session_state.roster_results = {"roster": roster, "stats": stats}
    st.session_state.step = 4
    st.rerun()

def render_stage_4_results():
    st.title("✨ Roster Ready!")
    
    if 'roster_results' not in st.session_state or st.session_state.roster_results is None:
        # If state was lost or regenerated, go back to processing
        st.session_state.step = 3
        st.rerun()
        return

    res = st.session_state.roster_results
    roster_df = res['roster']
    stats_df = res['stats']

    # 1. Show Roster Table
    st.subheader("Final Roster")
    st.dataframe(
        roster_df.style.applymap(lambda x: "background-color: #262730" if "Combined" in str(x) else ""),
        use_container_width=True,
        hide_index=True
    )

    # 2. Show Stats
    with st.expander("📊 Live Load Statistics (Updates automatically)", expanded=False):
        st.dataframe(stats_df, use_container_width=True, hide_index=True)

    st.markdown("---")

    # 3. ACTION BUTTONS 
    # Defined in 4 explicit columns to force alignment
    c1, c2, c3, c4 = st.columns(4)

    with c1:
        if st.button("← Back", use_container_width=True):
            st.session_state.step = 2
            st.rerun()

    with c2:
        # REGENERATE BUTTON: Clears the result from memory and reruns stage 3
        if st.button("🔄 Regenerate", use_container_width=True, help="Re-roll the randomization"):
            del st.session_state['roster_results']
            st.session_state.step = 3
            st.rerun()

    with c3:
        # DOWNLOAD BUTTON
        csv = roster_df.to_csv(index=False).encode('utf-8')
        st.download_button(
            label="💾 Download CSV",
            data=csv,
            file_name=f"roster_{datetime.now().strftime('%Y%m%d')}.csv",
            mime="text/csv",
            type="primary",
            use_container_width=True
        )

    with c4:
        # START OVER BUTTON
        if st.button("Start Over", use_container_width=True):
            st.session_state.clear()
            st.rerun()

# ==========================================
# 6. MAIN ROUTER
# ==========================================

if st.session_state.step == 1:
    render_stage_1_intro()
elif st.session_state.step == 2:
    render_stage_2_dates()
elif st.session_state.step == 3:
    render_stage_3_loading()
elif st.session_state.step == 4:
    render_stage_4_results()
