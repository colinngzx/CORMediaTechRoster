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

    if st.session_state.roster_dates:
        fmt_dates = [{"Day": d.strftime("%A"), "Date": d.strftime("%d %b %Y")} for d in st.session_state.roster_dates]
        st.dataframe(fmt_dates, use_container_width=True, height=300)
    else:
        st.warning("No dates currently selected.")
    
    st.divider()
    
    c1, c2 = st.columns(2)
    
    with c1:
        st.subheader("➕ Add Date")
        # Removing value=None to fix blank screen issues on older Streamlits
        new_date = st.date_input("Pick a date to add", value=date.today())
        
        if st.button("Add Date"):
            if new_date not in st.session_state.roster_dates:
                st.session_state.roster_dates.append(new_date)
                st.session_state.roster_dates.sort()
                st.success(f"Added {new_date}")
                rerun_script()
            else:
                st.warning("Date already exists.")

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
        # Initialize DataFrame keys if strictly needs fresh start
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
# STAGE 4: UNAVAILABILITY (REVISED)
# ==========================================
elif st.session_state.stage == 4:
    st.header("Stage 4: Input Availability")
    st.write("Scroll down the list. For each person, select the **dates they are UNAVAILABLE**.")
    st.info("💡 **Tip:** If a person says '8-22 Feb', just tick all the Sundays in that range.")
    
    # Create a mapping of nice labels string -> real date object
    # e.g. "04-Jan (Normal)" -> date(2025, 1, 4)
    date_options_map = {}
    for _, row in st.session_state.event_details.iterrows():
        d = row['Date']
        label = d.strftime("%d-%b")
        if row['Holy Communion']: label += " (HC)"
        if row['Combined Service']: label += " (Comb)"
        date_options_map[label] = d

    dropdown_options = list(date_options_map.keys())
    
    # Store user selections here temporarily
    person_unavailable_map = {}

    # Display list of people
    for person_name in all_team_names:
        c1, c2 = st.columns([1, 3])
        with c1:
            st.markdown(f"**{person_name}**")
        with c2:
            selected_labels = st.multiselect(
                f"Dates {person_name} is away",
                options=dropdown_options,
                label_visibility="collapsed",
                key=f"na_person_{person_name}"
            )
            person_unavailable_map[person_name] = selected_labels
        
        st.markdown("<hr style='margin: 0.5rem 0; opacity: 0.3;'>", unsafe_allow_html=True)
        
    st.divider()
    col1, col2 = st.columns([1, 5])
    if col1.button("⬅️ Back"):
        st.session_state.stage = 3
        rerun_script()
        
    if col2.button("Next: Generate Roster ➡️", type="primary"):
        # TRANSFORM DATA
        # We need to flip the logic from {Person: [Dates]} -> {Date: [People]}
        # so Phase 5 interacts with it correctly.
        
        final_unavailability = {}
        
        for person, labeled_dates_list in person_unavailable_map.items():
            for label in labeled_dates_list:
                real_date_obj = date_options_map[label]
                
                if real_date_obj not in final_unavailability:
                    final_unavailability[real_date_obj] = []
                
                final_unavailability[real_date_obj].append(person)
        
        st.session_state.unavailability = final_unavailability
        st.session_state.stage = 5
        rerun_script()

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
