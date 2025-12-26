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

# --- APPLE STYLE CSS INJECTION ---
def apply_apple_style():
    st.markdown("""
        <style>
        /* Import clean font */
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600&display=swap');
        
        html, body, [class*="css"] {
            font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
            color: #1d1d1f;
        }

        /* Headings */
        h1, h2, h3 {
            font-weight: 600;
            letter-spacing: -0.5px;
            color: #1d1d1f;
        }
        
        /* Rounded "Pill" Buttons with apple-blue hover */
        div.stButton > button {
            border-radius: 20px;
            padding: 0.5rem 1.5rem;
            font-weight: 500;
            border: 1px solid #e5e5ea;
            background-color: white;
            color: #007AFF;
            box-shadow: 0 1px 2px rgba(0,0,0,0.05);
            transition: all 0.2s ease;
        }
        div.stButton > button:hover {
            transform: translateY(-1px);
            box-shadow: 0 4px 6px rgba(0,0,0,0.1);
            border-color: #007AFF;
            color: #007AFF;
        }
        div.stButton > button[kind="primary"] {
            background-color: #007AFF;
            color: white;
            border: none;
        }
        div.stButton > button[kind="primary"]:hover {
            background-color: #0062cc;
            color: white;
        }

        /* Clean Inputs */
        .stTextInput input, .stSelectbox > div > div, .stMultiSelect > div > div {
            border-radius: 12px;
            border-color: #d1d1d6;
        }
        
        /* Remove default decoration */
        header {visibility: hidden;}
        </style>
    """, unsafe_allow_html=True)

apply_apple_style()

# --- HELPER: RERUN COMPATIBILITY ---
def rerun_script():
    """Handles rerun for different Streamlit versions"""
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
SHEET_ID = "1jh6ScfqpHe7rRN1s-9NYPsm7hwqWWLjdLKTYThRRGUo"

@st.cache_data(ttl=60)
def get_team_data():
    try:
        url = f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/gviz/tq?tqx=out:csv&sheet=Team"
        df = pd.read_csv(url).fillna("")
        df.columns = df.columns.str.strip().str.lower()
        
        # Filter Logic: Check for 'Status' column (optional)
        if 'status' in df.columns:
            # Keep only if status is Empty or 'Active'
            df = df[
                (df['status'].str.lower() == 'active') | 
                (df['status'] == '')
            ]
        
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
# STAGE 1: SELECT MONTHS & YEAR
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
# STAGE 2: DATE REVIEW
# ==========================================
elif st.session_state.stage == 2:
    st.subheader("Review Dates")

    if st.session_state.roster_dates:
        fmt_dates = [{"Day": d.strftime("%A"), "Date": d.strftime("%d %b %Y")} for d in st.session_state.roster_dates]
        st.dataframe(fmt_dates, use_container_width=True, height=250)
    else:
        st.warning("No dates currently selected.")
    
    st.markdown("---")
    c1, c2 = st.columns(2)
    
    with c1:
        st.caption("Add Date")
        new_date = st.date_input("Pick a date", value=date.today(), label_visibility="collapsed")
        if st.button("➕ Add"):
            if new_date not in st.session_state.roster_dates:
                st.session_state.roster_dates.append(new_date)
                st.session_state.roster_dates.sort()
                rerun_script()

    with c2:
        st.caption("Remove Date")
        if st.session_state.roster_dates:
            date_to_remove = st.selectbox(
                "Select date", 
                options=st.session_state.roster_dates,
                format_func=lambda x: x.strftime("%d %b %Y"),
                label_visibility="collapsed"
            )
            if st.button("❌ Remove"):
                if date_to_remove in st.session_state.roster_dates:
                    st.session_state.roster_dates.remove(date_to_remove)
                    st.session_state.roster_dates.sort()
                    rerun_script()
            
    st.markdown("<br><br>", unsafe_allow_html=True)
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
# STAGE 4: UNAVAILABILITY (PERSON BASED)
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

    st.markdown("<div style='background-color:#F5F5F7; padding:20px; border-radius:15px;'>", unsafe_allow_html=True)
    
    for person_name in all_team_names:
        c1, c2 = st.columns([1, 3])
        with c1:
            st.markdown(f"<div style='margin-top:10px; font-weight:500;'>{person_name}</div>", unsafe_allow_html=True)
        with c2:
            selected_labels = st.multiselect(
                f"Dates {person_name} is away",
                options=dropdown_options,
                label_visibility="collapsed",
                key=f"na_person_{person_name}"
            )
            person_unavailable_map[person_name] = selected_labels
        st.markdown("<hr style='margin: 0.5rem 0; border:none; border-bottom:1px solid #e0e0e0;'>", unsafe_allow_html=True)
    
    st.markdown("</div>", unsafe_allow_html=True)
        
    st.markdown("<br>", unsafe_allow_html=True)
    col1, col2 = st.columns([1, 5])
    if col1.button("⬅️ Back"):
        st.session_state.stage = 3
        rerun_script()
        
    if col2.button("Next: Generate Roster ➡️", type="primary"):
        # Flip map for processing
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
# STAGE 5: INTELLIGENT GENERATION & STACKED CSV OUTPUT
# ==========================================
elif st.session_state.stage == 5:
    st.subheader("Final Roster")
    st.caption("Grouped by month")
    
    # 1. Initialize logic counters
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
    
    # --- GENERATION LOOP ---
    for _, row in sort_dates.iterrows():
        current_date_obj = row['Date']
        
        info_parts = []
        if row['Holy Communion']: info_parts.append("HC")
        if row['Combined Service']: info_parts.append("Combined (MSS)")
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
            
            # Fallback for Team Lead
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

    # --- CHUNK BY MONTH & FORMAT ---
    full_df = pd.DataFrame(generated_rows)
    desired_row_order = [
         "Additional Details", "Sound Crew", "Projectionist", 
         "Stream Director", "Cam 1", "Cam 2", "Team Lead"
    ]
    
    def create_month_table(month_subset_df):
        t_df = month_subset_df.set_index("Service Dates").T
        t_df = t_df.reindex(desired_row_order)
        t_df = t_df.reset_index().rename(columns={"index": "Role"})
        return t_df

    # --- STYLING FUNCTION (THE "FILLED DATES" VISUALS) ---
    def style_dataframe(df):
        # Header Color (Cyan/Blue like screenshot)
        header_color = "#C3F3F5" 
        
        return df.style.set_properties(
            **{
                'background-color': '#FFFFFF', 
                'color': '#1d1d1f', 
                'border-color': '#E5E5EA',
                'font-size': '14px'
            }
        ).set_table_styles([
            # Style the Headers (The Dates)
            {
                'selector': 'th',
                'props': [
                    ('background-color', header_color), 
                    ('color', 'black'),
                    ('font-weight', '600'),
                    ('border-bottom', '2px solid #aaaaaa'),
                    ('text-align', 'center')
                ]
            },
            # Style the First Column (Role Names)
            {
                'selector': 'td:first-child',
                'props': [
                    ('font-weight', 'bold'), 
                    ('background-color', '#F5F5F7'),
                    ('color', '#333333')
                ]
            }
        ])

    grouped = full_df.groupby("Month")
    csv_output = io.StringIO()
    
    first_table = True
    
    for month_num, group in grouped:
        month_name = calendar.month_name[month_num]
        
        st.markdown(f"#### {month_name}")
        
        visual_table = create_month_table(group)
        
        # DISPLAY
        st.dataframe(style_dataframe(visual_table), use_container_width=True, hide_index=True)
        
        # CSV EXPORT
        if not first_table:
            csv_output.write("\n") 
        visual_table.to_csv(csv_output, index=False)
        first_table = False

    # --- STATS ---
    st.divider()
    st.write("#### 📊 Workload Stats")
    
    display_stats = {name: 0 for name in all_team_names}
    technical_roles = ["Sound Crew", "Projectionist", "Stream Director", "Cam 1", "Cam 2"]
    
    for day_data in generated_rows:
        for role_key in technical_roles:
            person = day_data.get(role_key, "")
            if person and person != "NO FILL" and person in display_stats:
                display_stats[person] += 1
    
    stats_df = pd.DataFrame(list(display_stats.items()), columns=["Name", "Shifts"])
    stats_df = stats_df[stats_df['Shifts'] > 0].sort_values(by="Shifts", ascending=False)
    
    st.dataframe(
        stats_df.T.style.set_properties(**{'background-color': 'white'}), 
        use_container_width=True
    )

    # --- FOOTER ---
    st.markdown("<br>", unsafe_allow_html=True)
    colA, colB = st.columns(2)
    with colA:
        st.download_button(
            label="💾 Download Excel CSV",
            data=csv_output.getvalue(),
            file_name="roster_final_stacked.csv",
            mime="text/csv",
            type="primary"
        )
    with colB:
        if st.button("🔄 Start Over"):
            st.session_state.stage = 1
            st.session_state.roster_dates = []
            rerun_script()
