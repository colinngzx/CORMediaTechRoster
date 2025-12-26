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

all_team_names = team_df['name'].tolist()

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
            rerun_script()

# ==========================================
# STAGE 2: CONFIRM & MODIFY DATES
# ==========================================
elif st.session_state.stage == 2:
    st.header("Stage 2: Date Review")
    st.write("Review the schedule below.")

    # Display dates in a simple dataframe for stability
    if st.session_state.roster_dates:
        # Create a display list
        fmt_dates = [{"Day": d.strftime("%A"), "Date": d.strftime("%d %b %Y")} for d in st.session_state.roster_dates]
        st.dataframe(fmt_dates, use_container_width=True, height=300)
    else:
        st.warning("No dates currently selected.")
    
    st.divider()
    
    # --- ADD / REMOVE CONTROLS ---
    c1, c2 = st.columns(2)
    
    # Left Column: Add Date
    with c1:
        st.subheader("➕ Add Date")
        # Fixed: Removed 'value=None' to ensure compatibility
        new_date = st.date_input("Pick a date to add", value=date.today())
        
        if st.button("Add Date"):
            if new_date not in st.session_state.roster_dates:
                st.session_state.roster_dates.append(new_date)
                st.session_state.roster_dates.sort()
                st.success(f"Added {new_date}")
                rerun_script()
            else:
                st.warning("Date already exists.")

    # Right Column: Remove Date
    with c2:
        st.subheader("❌ Remove Date")
        if st.session_state.roster_dates:
            date_to_remove = st.selectbox(
                "Select a date to remove:", 
                options=st.session_state.roster_dates,
                format_func=lambda x: x.strftime("%d %b %Y (%A)")
            )
            
            if st.button("Remove Selected"):
                if date_to_remove in st.session_state.roster_dates:
                    st.session_state.roster_dates.remove(date_to_remove)
                    st.session_state.roster_dates.sort()
                    rerun_script()
        else:
            st.write("List is empty.")
            
    st.divider()
    col1, col2 = st.columns([1, 5])
    if col1.button("⬅️ Back"):
        st.session_state.stage = 1
        rerun_script()
    if col2.button("Next: Event Details ➡️", type="primary"):
        # Initialize DataFrame
        data = {
            "Date": st.session_state.roster_dates,
            "Holy Communion": [False] * len(st.session_state.roster_dates),
            "Combined Service": [False] * len(st.session_state.roster_dates),
            "Notes": [""] * len(st.session_state.roster_dates)
        }
        st.session_state.event_details = pd.DataFrame(data)
        st.session_state.stage = 3
        rerun_script()

# ==========================================
# STAGE 3: EVENT DETAILS
# ==========================================
elif st.session_state.stage == 3:
    st.header("Stage 3: Service Details")
    st.info("Check boxes for specific service types.")
    
    edited_df = st.data_editor(
        st.session_state.event_details,
        column_config={
            "Date": st.column_config.DateColumn("Date", format="DD MMM YYYY", disabled=True),
            "Holy Communion": st.column_config.CheckboxColumn("Holy Communion?", default=False),
            "Combined Service": st.column_config.CheckboxColumn("Combined (MSS)?", default=False),
            "Notes": st.column_config.TextColumn("Custom Notes", width="large")
        },
        hide_index=True,
        use_container_width=True
    )
    
    st.divider()
    col1, col2 = st.columns([1, 5])
    if col1.button("⬅️ Back"):
        st.session_state.stage = 2
        rerun_script()
    if col2.button("Next: Availability ➡️", type="primary"):
        st.session_state.event_details = edited_df
        st.session_state.stage = 4
        rerun_script()

# ==========================================
# STAGE 4: UNAVAILABILITY
# ==========================================
elif st.session_state.stage == 4:
    st.header("Stage 4: Who is away?")
    st.write("For each date, select team members who are **unavailable**.")
    
    temp_unavailability = {}
    
    for index, row in st.session_state.event_details.iterrows():
        d_str = row['Date'].strftime("%d-%b")
        
        # Build label
        extras = []
        if row['Holy Communion']: extras.append("HC")
        if row['Combined Service']: extras.append("Combined")
        if row['Notes']: extras.append(row['Notes'])
        
        label_text = f"**{d_str}**"
        if extras:
            label_text += f" ({', '.join(extras)})"
            
        st.markdown(label_text)
        unavailable_people = st.multiselect(
            "Select unavailable:", 
            options=all_team_names,
            key=f"na_{index}",
            label_visibility="collapsed"
        )
        st.write("") # Spacer
        temp_unavailability[row['Date']] = unavailable_people
        
    st.divider()
    col1, col2 = st.columns([1, 5])
    if col1.button("⬅️ Back"):
        st.session_state.stage = 3
        rerun_script()
        
    if col2.button("Next: Generate Roster ➡️", type="primary"):
        st.session_state.unavailability = temp_unavailability
        st.session_state.stage = 5
        rerun_script()

# ==========================================
# STAGE 5: GENERATION
# ==========================================
elif st.session_state.stage == 5:
    st.header("Stage 5: Final Roster")
    
    # ROLES CONFIGURATION
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
        
        # Info string
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
            # SKIP CAM 2 Logic
            if role_label == "Cam 2":
                day_roster[role_label] = ""
                continue
                
            # SPECIAL: TEAM LEAD
            if role_label == "Team Lead":
                if 'team lead' in team_df.columns:
                    # Filter: Must have 'yes' in 'team lead' column
                    candidates = team_df[
                        (team_df['team lead'].astype(str).str.contains("yes", case=False)) &
                        (~team_df['name'].isin(away_today)) &
                        (~team_df['name'].isin(working_today))
                    ]['name'].tolist()
                else:
                    candidates = []
                
                # Logic: Avoid Darrell if possible
                final_candidates = []
                if candidates:
                    darrell_free = [x for x in candidates if "darrell" not in x.lower()]
                    final_candidates = darrell_free if darrell_free else candidates
            
            # STANDARD ROLES
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
            
            # PICK ONE
            if final_candidates:
                pick = random.choice(final_candidates)
                day_roster[role_label] = pick
                working_today.append(pick)
            else:
                day_roster[role_label] = "NO FILL"
        
        final_results.append(day_roster)

    final_df = pd.DataFrame(final_results)
    
    st.success("Roster Generated Successfully!")
    edited_final = st.data_editor(final_df, use_container_width=True, height=600)
    
    st.write("### Actions")
    
    csv_buffer = io.BytesIO()
    edited_final.to_csv(csv_buffer, index=False)
    
    colA, colB = st.columns(2)
    with colA:
        st.download_button(
            label="💾 Download CSV",
            data=csv_buffer.getvalue(),
            file_name="roster_final.csv",
            mime="text/csv"
        )
    with colB:
        if st.button("🔄 Start Over"):
            st.session_state.stage = 1
            st.session_state.roster_dates = []
            rerun_script()
