import streamlit as st
import pandas as pd
import random
import calendar
from datetime import datetime, date
import io

# --- CONFIG ---
st.set_page_config(page_title="SWS Roster Wizard", page_icon="🧙‍♂️", layout="wide")

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
        # Normalize headers to lowercase to prevent KeyErrors
        df.columns = df.columns.str.strip().str.lower()
        return df
    except:
        return pd.DataFrame()

team_df = get_team_data()

if team_df.empty:
    st.error("Could not load team members from Google Sheet. Check internet or Sheet permissions.")
    st.stop()

if 'name' not in team_df.columns:
    st.error("Error: The 'Team' sheet must have a column named 'Name'. Found: " + ", ".join(team_df.columns))
    st.stop()

all_team_names = team_df['name'].tolist()

# --- HEADER ---
st.title("🧙‍♂️ Roster Generator Wizard")

# ==========================================
# STAGE 1: SELECT MONTHS & YEAR
# ==========================================
if st.session_state.stage == 1:
    st.header("Stage 1: Select Duration")
    st.write("Which months represent this quarter/roster period?")
    
    col1, col2 = st.columns([1, 2])
    
    # Changed default value to 2026
    year_sel = col1.number_input("Year", min_value=2024, max_value=2030, value=2026)
    
    month_names = list(calendar.month_name)[1:] 
    selected_months = col2.multiselect("Select Months", options=month_names, default=["January", "February", "March"])
    
    if st.button("Next: Generate Dates ➡️"):
        if not selected_months:
            st.warning("Please select at least one month.")
        else:
            month_map = {name: i for i, name in enumerate(calendar.month_name) if name}
            generated_dates = []
            
            for m_name in selected_months:
                m_int = month_map[m_name]
                _, num_days = calendar.monthrange(year_sel, m_int)
                for day in range(1, num_days + 1):
                    dt = date(year_sel, m_int, day)
                    if dt.weekday() == 6: # Sunday
                        generated_dates.append(dt)
            
            generated_dates.sort()
            st.session_state.roster_dates = generated_dates
            st.session_state.stage = 2
            st.rerun()

# ==========================================
# STAGE 2: CONFIRM & MODIFY DATES
# ==========================================
elif st.session_state.stage == 2:
    st.header("Stage 2: Date Review")
    st.write("Review the schedule below. You can **Add** new dates or **Remove** dates you don't need.")

    # Show current list cleanly
    if st.session_state.roster_dates:
        date_strings = [d.strftime("• %A, %d %b %Y") for d in st.session_state.roster_dates]
        st.info("\n".join(date_
