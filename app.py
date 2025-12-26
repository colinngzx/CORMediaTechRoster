import streamlit as st
import pandas as pd
import random
import calendar
from datetime import datetime, date
import io

# --- CONFIG ---
st.set_page_config(
    page_title="SWS Roster Wizard", 
    page_icon="🧙‍♂️", 
    layout="wide",
    initial_sidebar_state="collapsed"
)

# --- FORCE WHITE THEME & APPLE FONTS ---
def apply_custom_style():
    st.markdown("""
        <style>
        /* IMPORT FONT */
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600&display=swap');
        
        /* 1. FORCE WHITE BACKGROUND & BLACK TEXT (Overrides Dark Mode) */
        .stApp {
            background-color: white !important;
            color: #000000 !important;
        }
        
        /* 2. TYPOGRAPHY */
        html, body, [class*="css"], .stMarkdown, .stText {
            font-family: 'Inter', sans-serif !important;
            color: #000000 !important;
        }
        h1, h2, h3 {
            color: #000000 !important;
            font-weight: 600;
        }

        /* 3. BUTTON STYLING (Apple Style Pills) */
        div.stButton > button {
            border-radius: 20px;
            padding: 0.5rem 1.5rem;
            font-weight: 500;
            border: 1px solid #d1d1d6;
            background-color: #f2f2f7; /* Light gray pill */
            color: #007AFF;
            transition: all 0.2s;
        }
        div.stButton > button:hover {
            border-color: #007AFF;
            background-color: #e5f1ff;
            color: #007AFF;
        }
        div.stButton > button[kind="primary"] {
            background-color: #007AFF !important;
            color: white !important;
            border: none;
        }

        /* 4. INPUT FIELDS (Force clear background) */
        .stTextInput input, .stSelectbox > div > div, .stMultiSelect > div > div {
            background-color: #ffffff !important;
            color: #000000 !important;
            border: 1px solid #d1d1d6;
        }
        
        /* 5. REMOVE STREAMLIT HEADER */
        header {visibility: hidden;}
        </style>
    """, unsafe_allow_html=True)

apply_custom_style()

# --- HELPER: RERUN COMPATIBILITY ---
def rerun_script():
    if hasattr(st, 'rerun'):
        st.rerun()
    elif hasattr(st, 'experimental_rerun'):
        st.experimental_rerun()
    else:
        st.write("⚠️ Please refresh the page.")

# --- SESSION STATE SETUP ---
if 'stage' not in st.session_state:
    st.session_state.stage = 1
if 'roster_dates' not in st.session_state:
    st.session_state.roster_dates = []
if 'event_details' not in st.session_state:
    st.session_state.event_details = pd.DataFrame()
if 'unavailability' not in st.session_state:
    st.session_state.unavailability = {}

# --- LOAD TEAM NAMES ---
# Using the same Sheet ID you provided earlier
SHEET_ID = "1jh6ScfqpHe7rRN1s-9NYPsm7hwqWWLjdLKTYThRRGUo"

@st.cache_data(ttl=60)
def get_team_data():
    try:
        url = f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/gviz/tq?tqx=out:csv&sheet=Team"
        df = pd.read_csv(url).fillna("")
        df.columns = df.columns.str.strip().str.lower()
        
        # Filter Logic: Check for 'Status' column
        if 'status' in df.columns:
            df = df[(df['status'].str.lower() == 'active') | (df['status'] == '')]
        
        return df
    except Exception as e:
        return pd.DataFrame()

team_df = get_team_data()

if team_df.empty:
    st.error("Could not load team members. Check internet or Sheet permissions.")
    st.stop()

if 'name' not in team_df.columns:
    st.error(f"Error: 'Team' sheet must have a 'Name' column.")
    st.stop()

all_team_names = sorted(team_df['name'].tolist())

# --- HEADER ---
st.title("🧙‍♂️ Roster Generator")
st.markdown("---")

# ==========================================
# STAGE 1: SELECT MONTHS
# ==========================================
if st.session_state.stage == 1:
    st.subheader("Select Duration")
    
    col1, col2 = st.columns([1, 2])
    with col1:
        year_sel = st.number_input("Year", min_value=2024, max_value=2030, value=datetime.now().year)
    with col2:
        month_names = list(calendar.month_name)[1:] 
        selected_months = st.multiselect("Select Months", options=month_names)
    
    st.markdown("<br>", unsafe_allow_html=True)
    if st.button("Generate Dates ➡️", type="primary"):
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
# STAGE 2: REVIEW DATES
# ==========================================
elif st.session_state.stage == 2:
    st.subheader("Review Dates")
    
    # Simple table for review
    if st.session_state.roster_dates:
        fmt_dates = [{"Day": d.strftime("%A"), "Date": d.strftime("%d %b %Y")} for d in st.session_state.roster_dates]
        st.dataframe(fmt_dates, use_container_width=True, height=250)
    else:
        st.warning("No dates currently selected.")
    
    st.markdown("---")
    c1, c2 = st.columns(2)
    
    with c1:
        new_date = st.date_input("Add Date", value=date.today())
        if st.button("➕ Add Date"):
            if new_date not in st.session_state.roster_dates:
                st.session_state.roster_dates.append(new_date)
                st.session_state.roster_dates.sort()
                rerun_script()

    with c2:
        if st.session_state.roster_dates:
            date_to_remove = st.selectbox("Remove Date", options=st.session_state.roster_dates, format_func=lambda x: x.strftime("%d %b %Y"))
            if st.button("❌ Remove Date"):
                if date_to_remove in st.session_state.roster_dates:
                    st.session_state.roster_dates.remove(date_to_remove)
                    st.session_state.roster_dates.sort()
                    rerun_script()
            
    st.markdown("<br>", unsafe_allow_html=True)
    col1, col2 = st.columns([1, 5])
    if col1.button("⬅️ Back"):
        st.session_state.stage = 1
        rerun_script()
    if col2.button("Next: Event Details ➡️", type="primary"):
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
    st.subheader("Service Details")
    
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
    
    st.markdown("<br>", unsafe_allow_html=True)
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
    st.subheader("Team Availability")
    st.info("Select dates when team members are **UNAVAILABLE**.")
    
    date_options_map = {}
    for _, row in st.session_state.event_details.iterrows():
        d = row['Date']
        label = d.strftime("%d-%b")
        if row['Holy Communion']: label += " (HC)"
        if row['Combined Service']: label += " (Comb)"
        date_options_map[label] = d

    dropdown_options = list(date_options_map.keys())
    person_unavailable_map = {}

    # Render a clean list
    st.markdown("<div style='background-color:#ffffff; border:1px solid #e5e5ea; padding:20px; border-radius:15px;'>", unsafe_allow_html=True)
    
    for person_name in all_team_names:
        c1, c2 = st.columns([1, 3])
        with c1:
            st.markdown(f"<div style='margin-top:10px; font-weight:500; color:black;'>{person_name}</div>", unsafe_allow_html=True)
        with c2:
            selected_labels = st.multiselect(
                f"Dates {person_name} is away",
                options=dropdown_options,
                label_visibility="collapsed",
                key=f"na_person_{person_name}"
            )
            person_unavailable_map[person_name] = selected_labels
        st.markdown("<hr style='margin: 0.5rem 0; border:none; border-bottom:1px solid #f0f0f0;'>", unsafe_allow_html=True)
    
    st.markdown("</div>", unsafe_allow_html=True)
        
    st.markdown("<br>", unsafe_allow_html=True)
    col1, col2 = st.columns([1, 5])
    if col1.button("⬅️ Back"):
        st.session_state.stage = 3
        rerun_script()
        
    if col2.button("Next: Generate Roster ➡️", type="primary"):
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
# STAGE 5: FINAL ROSTER (EXCEL STYLE)
# ==========================================
elif st.session_state.stage == 5:
    st.subheader("Final Roster")
    
    # --- LOGIC GENERATION ---
    load_balance_counts = {name: 0 for name in all_team_names}
    previous_week_workers = []
    
    roles_processing_order = [
         ("Sound Crew", "sound"),
         ("Projectionist", "projection"),
         ("Stream Director", "stream"),
         ("Cam 1", "camera"),
         ("Team Lead", "team lead") 
    ]
    
    generated_rows = []
    sort_dates = st.session_state.event_details.sort_values(by="Date")
    
    for _, row in sort_dates.iterrows():
        current_date_obj = row['Date']
        
        info_parts = []
        if row['Holy Communion']: info_parts.append("HC")
        if row['Combined Service']: info_parts.append("Combined")
        if not info_parts: info_parts.append("")
        if row['Notes']: info_parts.append(f"({row['Notes']})")
        
        away_today = st.session_state.unavailability.get(current_date_obj, [])
        working_today = [] 
        
        day_roster = {
            "Month": current_date_obj.month,
            "Service Dates": current_date_obj.strftime("%d-%b"),
            "Additional Details": " ".join(info_parts),
            "Cam 2": "" 
        }
        
        for role_label, search_keyword in roles_processing_order:
            if role_label == "Team Lead":
                if 'team lead' in team_df.columns:
                    base_candidates = team_df[team_df['team lead'].astype(str).str.contains("yes", case=False)]['name'].tolist()
                else:
                    base_candidates = []
                darrell_free = [x for x in base_candidates if "darrell" not in x.lower()]
                pool = darrell_free if darrell_free else base_candidates
            else:
                pool = team_df[
                    team_df['role 1'].astype(str).str.contains(search_keyword, case=False) | 
                    team_df['role 2'].astype(str).str.contains(search_keyword, case=False) | 
                    team_df['role 3'].astype(str).str.contains(search_keyword, case=False)
                ]['name'].tolist()
            
            valid = [p for p in pool if p not in away_today]
            valid = [p for p in valid if p not in working_today]
            fresh_legs = [p for p in valid if p not in previous_week_workers]
            
            final_pool = fresh_legs if fresh_legs else valid
            
            # Fallback logic for TL
            if role_label == "Team Lead" and not final_pool:
                 darrells = [x for x in base_candidates if "darrell" in x.lower() and x not in away_today and x not in working_today]
                 if darrells: final_pool = darrells
            
            selected_person = "NO FILL"
            if final_pool:
                random.shuffle(final_pool) 
                final_pool.sort(key=lambda x: load_balance_counts[x])
                selected_person = final_pool[0]
                load_balance_counts[selected_person] += 1
                working_today.append(selected_person)
            
            day_roster[role_label] = selected_person

        previous_week_workers = working_today
        generated_rows.append(day_roster)

    # --- PANDAS STYLING FOR EXCEL GRID LOOK ---
    full_df = pd.DataFrame(generated_rows)
    desired_row_order = [
         "Additional Details", "Sound Crew", "Projectionist", 
         "Stream Director", "Cam 1", "Cam 2", "Team Lead"
    ]
    
    def display_excel_style(month_subset_df):
        # Transpose
        t_df = month_subset_df.set_index("Service Dates").T
        t_df = t_df.reindex(desired_row_order)
        t_df = t_df.reset_index().rename(columns={"index": "Role"})
        
        # Apply CSS Styler
        styled = t_df.style.set_properties(**{
            'background-color': 'white',
            'color': 'black',
            'border': '1px solid black',        # THE GRID LINES
            'text-align': 'center'
        }).set_table_styles([
            # Style the Headers (Dates) -> Cyan Blue like screenshot
            {
                'selector': 'th',
                'props': [
                    ('background-color', '#C3F3F5'), 
                    ('color', 'black'),
                    ('font-weight', 'bold'),
                    ('border', '1px solid black'),
                    ('text-align', 'center')
                ]
            },
            # Style the First Column (Roles) -> Light Green like screenshot
            {
                'selector': 'td:nth-child(1)', 
                'props': [
                    ('background-color', '#E2EFDA'),
                    ('font-weight', 'bold'),
                    ('border', '1px solid black'),
                    ('text-align', 'left'),
                    ('padding-left', '10px')
                ]
            },
            # Remove index column
            {'selector': '.row_heading', 'props': [('display', 'none')]},
            {'selector': '.blank', 'props': [('display', 'none')]}
        ])
        
        return styled, t_df

    grouped = full_df.groupby("Month")
    csv_output = io.StringIO()
    first_table = True
    
    for month_num, group in grouped:
        month_name = calendar.month_name[month_num]
        
        st.markdown(f"### {month_name}")
        
        styled_
