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
        # --- CRITICAL FIX: Normalize headers to lowercase to prevent KeyErrors ---
        df.columns = df.columns.str.strip().str.lower()
        return df
    except:
        return pd.DataFrame()

team_df = get_team_data()

if team_df.empty:
    st.error("Could not load team members from Google Sheet. Check internet or Sheet permissions.")
    st.stop()

# logic to handle potential column name mismatches
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
    
    # Year Selector
    current_year = datetime.now().year
    year_sel = col1.number_input("Year", min_value=2024, max_value=2030, value=current_year)
    
    # Month Selector
    month_names = list(calendar.month_name)[1:] # ['January', 'February', ...]
    selected_months = col2.multiselect("Select Months", options=month_names, default=["January", "February", "March"])
    
    if st.button("Next: Generate Dates ➡️"):
        if not selected_months:
            st.warning("Please select at least one month.")
        else:
            # Map month names to numbers (January=1, etc)
            month_map = {name: i for i, name in enumerate(calendar.month_name) if name}
            
            generated_dates = []
            
            # Loop through selected months and find Sundays
            for m_name in selected_months:
                m_int = month_map[m_name]
                # Get number of days in that month
                _, num_days = calendar.monthrange(year_sel, m_int)
                
                for day in range(1, num_days + 1):
                    dt = date(year_sel, m_int, day)
                    # 6 = Sunday in Python's weekday()
                    if dt.weekday() == 6: 
                        generated_dates.append(dt)
            
            # Sort them chronologically
            generated_dates.sort()
            
            st.session_state.roster_dates = generated_dates
            st.session_state.stage = 2
            st.rerun()

# ==========================================
# STAGE 2: CONFIRM & ADD EXTRA DATES
# ==========================================
elif st.session_state.stage == 2:
    st.header("Stage 2: Date Review")
    st.write("Based on your selection, these are the Sundays found. You can add extra dates (e.g. Good Friday) below.")

    # Show current list
    st.write("### Current Schedule:")
    date_strings = [d.strftime("%A, %d %b %Y") for d in st.session_state.roster_dates]
    st.write(" • " + "  \n • ".join(date_strings))
    
    st.divider()
    
    # Add new date
    new_date = st.date_input("Add an extra event date? (e.g. Good Friday)", value=None)
    if st.button("Add Date"):
        if new_date and new_date not in st.session_state.roster_dates:
            st.session_state.roster_dates.append(new_date)
            st.session_state.roster_dates.sort() # Keep them in order
            st.success(f"Added {new_date}")
            st.rerun()
            
    st.divider()
    col1, col2 = st.columns([1, 5])
    if col1.button("⬅️ Back"):
        st.session_state.stage = 1
        st.rerun()
    if col2.button("Next: Event Details ➡️"):
        # Initialize the DataFrame
        data = {
            "Date": st.session_state.roster_dates,
            "Holy Communion": [False] * len(st.session_state.roster_dates),
            "Combined Service": [False] * len(st.session_state.roster_dates),
            "Notes": [""] * len(st.session_state.roster_dates)
        }
        st.session_state.event_details = pd.DataFrame(data)
        st.session_state.stage = 3
        st.rerun()

# ==========================================
# STAGE 3: EVENT DETAILS
# ==========================================
elif st.session_state.stage == 3:
    st.header("Stage 3: Service Details")
    st.info("Check the boxes for Holy Communion or Combined Services.")
    
    # Editable Table
    edited_df = st.data_editor(
        st.session_state.event_details,
        column_config={
            "Date": st.column_config.DateColumn("Date", format="DD MMM YYYY", disabled=True),
            "Holy Communion": st.column_config.CheckboxColumn("Holy Communion?", default=False),
            "Combined Service": st.column_config.CheckboxColumn("Combined (MSS)?", default=False),
            "Notes": st.column_config.TextColumn("Custom Notes", width="large")
        },
        hide_index=True,
        use_container_width=True,
        num_rows="fixed"
    )
    
    st.divider()
    col1, col2 = st.columns([1, 5])
    if col1.button("⬅️ Back"):
        st.session_state.stage = 2
        st.rerun()
    if col2.button("Next: Availability ➡️"):
        st.session_state.event_details = edited_df # Save changes
        st.session_state.stage = 4
        st.rerun()

# ==========================================
# STAGE 4: UNAVAILABILITY
# ==========================================
elif st.session_state.stage == 4:
    st.header("Stage 4: Who is away?")
    st.write("For each date, select the people who are **unavailable**.")
    
    temp_unavailability = {}
    
    # Loop through dates and create a multiselect for each
    for index, row in st.session_state.event_details.iterrows():
        d_str = row['Date'].strftime("%d-%b")
        
        type_parts = []
        if row['Holy Communion']: type_parts.append("HC")
        if row['Combined Service']: type_parts.append("Combined")
        if not type_parts: type_parts.append("Normal")
        
        type_label = "/".join(type_parts)
        note = row['Notes']
        label = f"{d_str} ({type_label})"
        if note:
            label += f" - {note}"
            
        unavailable_people = st.multiselect(
            label, 
            options=all_team_names,
            key=f"na_{index}"
        )
        temp_unavailability[row['Date']] = unavailable_people
        
    st.divider()
    col1, col2 = st.columns([1, 5])
    if col1.button("⬅️ Back"):
        st.session_state.stage = 3
        st.rerun()
        
    if col2.button("Next: Generate Roster ➡️", type="primary"):
        st.session_state.unavailability = temp_unavailability
        st.session_state.stage = 5
        st.rerun()

# ==========================================
# STAGE 5: GENERATION
# ==========================================
elif st.session_state.stage == 5:
    st.header("Stage 5: Final Roster")
    
    # --- ALGORITHM ---
    roles_config = [
        ("Sound Crew", "sound"),
        ("Projectionist", "projection"),
        ("Stream Director", "stream"),
        ("Cam 1", "camera"),
        ("Cam 2", "camera_2_placeholder"), 
        ("Team Lead", "team lead") 
    ]
    
    final_results = []
    
    for _, row in st.session_state.event_details.iterrows():
        current_date = row['Date']
        
        # Construct Service Info string
        info_parts = []
        if row['Holy Communion']: info_parts.append("HC")
        if row['Combined Service']: info_parts.append("Combined")
        if not info_parts: info_parts.append("Normal")
        if row['Notes']: info_parts.append(f"({row['Notes']})")
        service_info = " ".join(info_parts)
        
        away_today = st.session_state.unavailability.get(current_date, [])
        working_today = []
        
        day_roster = {
            "Date": current_date.strftime("%d-%b-%Y"),
            "Service Info": service_info
        }
        
        for role_label, search_keyword in roles_config:
            
            # 1. Handle Cam 2
            if role_label == "Cam 2":
                day_roster[role_label] = ""
                continue
                
            # 2. Team Lead Special Logic
            if role_label == "Team Lead":
                # NOTE: We use lowercase 'team lead' because we normalized headers at the top
                if 'team lead' in team_df.columns:
                    candidates = team_df[
                        (team_df['team lead'].astype(str).str.contains("yes", case=False)) &
                        (~team_df['name'].isin(away_today)) &
                        (~team_df['name'].isin(working_today))
                    ]['name'].tolist()
                else:
                    candidates = [] # Should not happen if sheet is correct
                
                final_candidates = []
                if candidates:
                    darrell_free = [x for x in candidates if "darrell" not in x.lower()]
                    final_candidates = darrell_free if darrell_free else candidates
                else:
                    final_candidates = []
                    
            # 3. Standard Roles
            else:
                 # NOTE: We use lowercase 'role 1', 'role 2' etc
                 final_candidates = team_df[
                    (
                        team_df['role 1'].astype(str).str.contains(search_keyword, case=False) | 
                        team_df['role 2'].astype(str).str.contains(search_keyword, case=False) | 
                        team_df['role 3'].astype(str).str.contains(search_keyword, case=False)
                    ) & 
                    (~team_df['name'].isin(away_today)) &
                    (~team_df['name'].isin(working_today))
                ]['name'].tolist()
            
            # PICK ONE
            if final_candidates:
                pick = random.choice(final_candidates)
                day_roster[role_label] = pick
                working_today.append(pick)
            else:
                day_roster[role_label] = "NO FILL"
        
        final_results.append(day_roster)

    # Convert to DataFrame
    final_df = pd.DataFrame(final_results)
    
    # Display
    st.success("Roster Generated!")
    edited_final = st.data_editor(final_df, use_container_width=True, height=600)
    
    st.write("### Actions")
    
    csv_buffer = io.BytesIO()
    edited_final.to_csv(csv_buffer, index=False)
    
    st.download_button(
        label="💾 Download CSV (for Excel/Google Sheets)",
        data=csv_buffer.getvalue(),
        file_name="roster_final.csv",
        mime="text/csv"
    )
    
    if st.button("🔄 Start Over"):
        st.session_state.stage = 1
        st.session_state.roster_dates = []
        st.rerun()
