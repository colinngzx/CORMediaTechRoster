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
        st.info("\n".join(date_strings))
    else:
        st.warning("No dates currently selected.")
    
    st.divider()
    
    # --- ADD / REMOVE CONTROLS ---
    c1, c2 = st.columns(2)
    
    # Left Column: Add Date
    with c1:
        st.subheader("➕ Add Date")
        new_date = st.date_input("Pick a date to add", value=None)
        if st.button("Add Date"):
            if new_date:
                if new_date not in st.session_state.roster_dates:
                    st.session_state.roster_dates.append(new_date)
                    st.session_state.roster_dates.sort()
                    st.success(f"Added {new_date}")
                    st.rerun()
                else:
                    st.warning("That date is already in the list.")

    # Right Column: Remove Date
    with c2:
        st.subheader("❌ Remove Date")
        if st.session_state.roster_dates:
            # Dropdown containing current dates
            date_to_remove = st.selectbox(
                "Select a date to remove:", 
                options=st.session_state.roster_dates,
                format_func=lambda x: x.strftime("%d %b %Y (%A)"),
                key="remove_selector"
            )
            
            if st.button("Remove Selected Date"):
                st.session_state.roster_dates.remove(date_to_remove)
                st.session_state.roster_dates.sort()
                st.error(f"Removed {date_to_remove}")
                st.rerun()
        else:
            st.write("List is empty, nothing to remove.")
            
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
        st.session_state.event_details = edited_df
        st.session_state.stage = 4
        st.rerun()

# ==========================================
# STAGE 4: UNAVAILABILITY
# ==========================================
elif st.session_state.stage == 4:
    st.header("Stage 4: Who is away?")
    st.write("For each date, select the people who are **unavailable**.")
    
    temp_unavailability = {}
    
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
            if role_label == "Cam 2":
                day_roster[role_label] = ""
                continue
                
            if role_label == "Team Lead":
                if 'team lead' in team_df.columns:
                    candidates = team_df[
                        (team_df['team lead'].astype(str).str.contains("yes", case=False)) &
                        (~team_df['name'].isin(away_today)) &
                        (~team_df['name'].isin(working_today))
                    ]['name'].tolist()
                else:
                    candidates = []
                
                final_candidates = []
                if candidates:
                    darrell_free = [x for x in candidates if "darrell" not in x.lower()]
                    final_candidates = darrell_free if darrell_free else candidates
                else:
                    final_candidates = []
                    
            else:
                 final_candidates = team_df[
                    (
                        team_df['role 1'].astype(str).str.contains(search_keyword, case=False) | 
                        team_df['role 2'].astype(str).str.contains(search_keyword, case=False) | 
                        team_df['role 3'].astype(str).str.contains(search_keyword, case=False)
                    ) & 
                    (~team_df['name'].isin(away_today)) &
                    (~team_df['name'].isin(working_today))
                ]['name'].tolist()
            
            if final_candidates:
                pick = random.choice(final_candidates)
                day_roster[role_label] = pick
                working_today.append(pick)
            else:
                day_roster[role_label] = "NO FILL"
        
        final_results.append(day_roster)

    final_df = pd.DataFrame(final_results)
    
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
