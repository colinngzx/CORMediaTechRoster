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
# 2. HELPER CLASSES
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
        mask = self.df[role_col].
