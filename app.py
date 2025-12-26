import streamlit as st
import pandas as pd
import random
import calendar
from datetime import datetime, date
import io

# --- CONFIG ---
st.set_page_config(page_title="SWS Roster Wizard", page_icon="🧙‍♂️", layout="wide")

# --- HELPER: RERUN COMPATIBILITY ---
def rerun_script():
    """Handles rerun for different Streamlit versions"""
    if hasattr(st, 'rerun'):
        st.rerun()
    elif hasattr(st, 'experimental_rerun'):
        st.experimental_rerun()
    else:
        st.write("⚠️ Please click 'Rerun' in the top right menu or refresh the page.")

# --- SESSION STATE SETUP ---
if 'stage' not in st.session_state:
    st.session_state.stage = 1
if 'roster_dates' not in st.session_state:
    st.session_state.roster_dates = []
if 'event_details' not in st.session_state:
    st.session_state.event_details = pd.DataFrame()
if 'unavailability' not in st.session_state:
    st.session_state.unavailability = {}

# --- LOAD TEAM NAMES (READ ONLY) ---
SHEET_ID = "1jh6ScfqpHe7rRN1s-9NYPsm7hwqWWLjdLKTYThRRGUo"

@st.cache_data
def get_team_data():
    try:
        url = f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/gviz/tq?tqx=out:csv&sheet=Team"
        df = pd.read_csv(url).fillna("")
        # Normalize headers to lowercase
        df.columns = df.columns.str.strip().str.lower()
        return df
    except Exception as e:
        return pd.DataFrame()

team_df = get_team_data()

# Check for data load errors
if team_df.empty:
    st.error("Could not load team members. Check internet or Sheet permissions.")
    st.stop()

if 'name' not in team_df.columns:
    st.error(f"Error: 'Team' sheet needs a column named 'Name'. Found: {list(team_df.columns)}")
    st.stop()

# Get names and sort them alphabetically for easier finding
all_team_names = sorted(team_df['name'].tolist())

# --- HEADER ---
st.title("🧙‍♂️ Roster Generator Wizard")

# ==========================================
# STAGE 1: SELECT MONTHS & YEAR
# ==========================================
if st.session_state.stage == 1:
    st.header("Stage 1: Select Duration")
    
    col1, col2 = st.columns([1, 2])
    
    with col1:
        year_sel = st.number_input("Year", min_value=2024, max_value=2030, value=2026)
    
    with col2:
        month_names = list(calendar.month_name)[1:] 
        selected_months = st.multiselect("Select Months", options=month_names, default=["January", "February", "March"])
    
    if st.button("Next: Generate Dates ➡️", type="primary"):
        if not selected_months:
            st.warning("Please select at least one month.")
        else:
            month_map = {name: i for i, name in enumerate(calendar.month_name) if name}
            generated_dates = []
            
            for m_name in selected
