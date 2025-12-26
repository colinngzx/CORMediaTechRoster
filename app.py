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

# --- STYLE ---
def apply_custom_style():
    st.markdown("""
        <style>
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600&display=swap');
        .stApp { background-color: white !important; color: #000000 !important; }
        html, body, [class*="css"], .stMarkdown, .stText { font-family: 'Inter', sans-serif !important; color: #000000 !important; }
        div.stButton > button { border-radius: 20px; padding: 0.5rem 1.5rem; font-weight: 500; border: 1px solid #d1d1d6; background-color: #f2f2f7; color: #007AFF; }
        div.stButton > button:hover { border-color: #007AFF; background-color: #e5f1ff; color: #007AFF; }
        div.stButton > button[kind="primary"] { background-color: #007AFF !important; color: white !important; border: none; }
        .stTextInput input, .stSelectbox > div > div, .stMultiSelect > div > div { background-color: #ffffff !important; color: #000000 !important; border: 1px solid #d1d1d6; }
        header {visibility: hidden;}
        </style>
    """, unsafe_allow_html=True)

apply_custom_style()

# --- REFRESH HELPER ---
def rerun_script():
    if hasattr(st, 'rerun'): st.rerun()
    elif hasattr(st, 'experimental_rerun'): st.experimental_rerun()
    else: st.write("⚠️ Please refresh.")

# --- STATE ---
if 'stage' not in st.session_state: st.session_state.stage = 1
if 'roster_dates' not in st.session_state: st.session_state.roster_dates = []
if 'event_details' not in st.session_state: st.session_state.event_details = pd.DataFrame()
if 'unavailability' not in st.session_state: st.session_state.unavailability = {}

# --- DATA LOADING ---
SHEET_ID = "1jh6ScfqpHe7rRN1s-9NYPsm7hwqWWLjdLKTYThRRGUo"

@st.cache_data(ttl=60)
def get_team_data():
    try:
        url = f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/gviz/tq?tqx=out:csv&sheet=Team"
        df = pd.read_csv(url).fillna("")
        df.columns = df.columns.str.strip().str.lower()
        if 'status' in df.columns: df = df[(df['status'].str.lower() == 'active') | (df['status'] == '')]
        if 'name' in df.columns: df['name'] = df['name'].str.strip()
        return df
    except: return pd.DataFrame()

team_df = get_team_data()

if team_df.empty:
    st.error("Could not load team. Check Sheet permissions.")
    st.stop()

all_team_names = sorted(team_df['name'].unique().tolist())

# --- APP ---
st.title("🧙‍♂️ Roster Generator")
st.markdown("---")

# 1. DATE SELECT
# ------------------------------------------------
if st.session_state.stage == 1:
    st.subheader("Select Duration")

    # --- AUTO-CALCULATE DEFAULTS ---
    now = datetime.now()
    current_year_val = now.year
    current_month_idx = now.month

    # 1. Calculate next 3 months names (wrapping around Dec->Jan)
    default_months_opts = []
    for i in range(1, 4):
        next_idx = current_month_idx + i
        if next_idx > 12: next_idx -= 12
        default_months_opts.append(calendar.month_name[next_idx])
    
    # 2. Logic for Year Default: 
    # If currently December (12), we move to next year. 
    # Else preserve current year.
    default_year_val = current_year_val + 1 if current_month_idx == 12 else current_year_val

    c1, c2 = st.columns([1, 2])
    with c1: 
        year_sel = st.number_input("Year", 2024, 2030, default_year_val)
    with c2: 
        month_names = list(calendar.month_name)[1:]
        selected_months = st.multiselect("Select Months", options=month_names, default=default_months_opts)
    
    st.markdown("<br>", unsafe_allow_html=True)
    if st.button("Generate Dates ➡️", type="primary"):
        if not selected_months: st.warning("Select a month.")
        else:
            dates = []
            m_map = {m: i for i, m in enumerate(calendar.month_name) if m}
            
            for m in selected_months:
                i = m_map[m]
                _, days = calendar.monthrange(year_sel, i)
                for d in range(1, days+1):
                    # Smart Date Logic:
                    # If we accidentally generated a date in the past (e.g. selected Jan while Year is still set to previous year),
                    # we could check it here. However, relying on the user setting the Year box correctly (which is now auto-defaulted correctly) is safer.
                    dt = date(year_sel, i, d)
                    
                    # Logic: If Jan is selected, but the Year box is roughly ~11 months ago, bump the year.
                    # This is an edge case safety net.
                    if (date.today() - dt).days > 320:
                         dt = date(year_sel + 1, i, d)

                    if dt.weekday() == 6: 
                        dates.append(dt)
            
            st.session_state.roster_dates = sorted(dates)
            st.session_state.stage = 2
            rerun_script()

# 2. REVIEW DATES
# ------------------------------------------------
elif st.session_state.stage == 2:
    st.subheader("Review Dates")
    if st.session_state.roster_dates:
        st.dataframe([{"Date": d.strftime("%d %b %Y")} for d in st.session_state.roster_dates], use_container_width=True, height=200)
    
    c1, c2 = st.columns(2)
    with c1:
        nd = st.date_input("Add Date", date.today())
        if st.button("➕ Add"): 
            if nd not in st.session_state.roster_dates: 
                st.session_state.roster_dates.append(nd)
                st.session_state.roster_dates.sort()
                rerun_script()
    with c2:
        if st.session_state.roster_dates:
            rd = st.selectbox("Remove Date", st.session_state.roster_dates, format_func=lambda x: x.strftime("%d %b"))
            if st.button("❌ Remove"): 
                st.session_state.roster_dates.remove(rd)
                rerun_script()

    st.markdown("<br>", unsafe_allow_html=True)
    c1, c2 = st.columns([1, 5])
    if c1.button("⬅️ Back"): st.session_state.stage = 1; rerun_script()
    if c2.button("Next ➡️", type="primary"):
        st.session_state.event_details = pd.DataFrame({
            "Date": st.session_state.roster_dates,
            "Holy Communion": [False]*len(st.session_state.roster_dates),
            "Combined Service": [False]*len(st.session_state.roster_dates),
            "Notes": [""]*len(st.session_state.roster_dates)
        })
        st.session_state.stage = 3
        rerun_script()

# 3. DETAILS
# ------------------------------------------------
elif st.session_state.stage == 3:
    st.subheader("Service Details")
    edited = st.data_editor(st.session_state.event_details, column_config={
        "Date": st.column_config.DateColumn("Date", format="DD MMM", disabled=True),
        "Holy Communion": st.column_config.CheckboxColumn("HC?", default=False),
        "Combined Service": st.column_config.CheckboxColumn("Combined?", default=False)
    }, hide_index=True, use_container_width=True)
    
    st.markdown("<br>", unsafe_allow_html=True)
    c1, c2 = st.columns([1, 5])
    if c1.button("⬅️ Back"): st.session_state.stage = 2; rerun_script()
    if c2.button("Next ➡️", type="primary"):
        st.session_state.event_details = edited
        st.session_state.stage = 4
        rerun_script()

# 4. AVAILABILITY
# ------------------------------------------------
elif st.session_state.stage == 4:
    st.subheader("Team Availability")
    d_map = {}
    for _, r in st.session_state.event_details.iterrows():
        lbl = r['Date'].strftime("%d-%b")
        if r['Holy Communion']: lbl += " (HC)"
        d_map[lbl] = r['Date']
    
    u_map = {}
    st.info("Select dates when people are **UNAVAILABLE**.")
    with st.container():
        for p in all_team_names:
            c1, c2 = st.columns([1, 3])
            c1.write(p)
            u_map[p] = c2.multiselect(f"Away {p}", d_map.keys(), label_visibility="collapsed", key=f"ua_{p}")
            st.markdown("<hr style='margin:0.2rem 0'>", unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)
    c1, c2 = st.columns([1, 5])
    if c1.button("⬅️ Back"): st.session_state.stage = 3; rerun_script()
    if c2.button("Generate ➡️", type="primary"):
        final_ua = {}
        for p, dates in u_map.items():
            for lbl in dates:
                d = d_map[lbl]
                if d not in final_ua: final_ua[d] = []
                final_ua[d].append(p)
        st.session_state.unavailability = final_ua
        st.session_state.stage = 5
        rerun_script()

# 5. ROSTER & STATS
# ------------------------------------------------
elif st.session_state.stage == 5:
    st.subheader("Final Roster")
    
    # Internal Load Scores used for picking people
    # We treat Team Lead as "free labor" for load balancing purposes
    # so they remain available for Tech roles
    load_score = {n: 0 for n in all_team_names} 
    prev_workers = []
    
    roles = [
        ("Sound Crew", "sound"),
        ("Projectionist", "projection"),
        ("Stream Director", "stream"),
        ("Cam 1", "camera"),
        ("Team Lead", "team lead") 
    ]
    
    roster_rows = []
    
    for _, row in st.session_state.event_details.sort_values(by="Date").iterrows():
        dt = row['Date']
        away = st.session_state.unavailability.get(dt, [])
        working = [] # Who is working THIS sunday
        
        info = []
        if row['Holy Communion']: info.append("HC")
        if row['Combined Service']: info.append("Comb")
        if row['Notes']: info.append(f"({row['Notes']})")
        
        day_data = {
            "Month": dt.month,
            "Service Dates": dt.strftime("%d-%b"),
            "Additional Details": " ".join(info),
            "Cam 2": "" 
        }
        
        for r_label, keyword in roles:
            # 1. Define Pool
            if r_label == "Team Lead":
                # Special Team Lead Logic
                if 'team lead' in team_df.columns:
                    pool = team_df[team_df['team lead'].astype(str).str.contains("yes", case=False)]['name'].tolist()
                else: pool = []
            else:
                # Technical Logic
                pool = team_df[
                    team_df['role 1'].str.contains(keyword, case=False, na=False) | 
                    team_df['role 2'].str.contains(keyword, case=False, na=False) | 
                    team_df['role 3'].str.contains(keyword, case=False, na=False)
                ]['name'].tolist()
            
            # 2. Filter Availability
            candidates = [p for p in pool if p not in away]
            candidates = [p for p in candidates if p not in working]
            
            # Prioritize those who didn't work last week
            fresh = [p for p in candidates if p not in prev_workers]
            final_pool = fresh if fresh else candidates

            # FALLBACK: If Team Lead pool dry, check prev workers (Darrell rule)
            if r_label == "Team Lead" and not final_pool:
                 final_pool = [p for p in pool if p not in away and p not in working]
            
            # 3. Pick Person (Fairness)
            selected = "NO FILL"
            if final_pool:
                random.shuffle(final_pool)
                # Sort by current workload to encourage spread
                final_pool.sort(key=lambda x: load_score[x])
                selected = final_pool[0]
                
                # SCORE UPDATE LOGIC:
                # If they do a Technical Role, add +1 to load score.
                # If they do Team Lead, add +0 (keeps them fresh for tech roles).
                if r_label != "Team Lead":
                    load_score[selected] += 1
                
                working.append(selected)
            
            day_data[r_label] = selected
        
        prev_workers = working
        roster_rows.append(day_data)

    # --- DISPLAY ---
    data_df = pd.DataFrame(roster_rows)
    role_order = ["Additional Details", "Sound Crew", "Projectionist", "Stream Director", "Cam 1", "Cam 2", "Team Lead"]
    
    csv_buf = io.StringIO()
    first = True
    
    for m, grp in data_df.groupby("Month"):
        st.markdown(f"### {calendar.month_name[m]}")
        
        # Excel Style Transpose
        t_df = grp.set_index("Service Dates").T.reindex(role_order).reset_index().rename(columns={"index":"Role"})
        
        # Style
        st.dataframe(t_df.style.set_properties(**{
            'text-align': 'center', 'border': '1px solid black'
        }).applymap(lambda v: 'background-color: #E2EFDA; font-weight: bold', subset=['Role']), use_container_width=True, hide_index=True)
        
        if not first: csv_buf.write("\n")
        t_df.to_csv(csv_buf, index=False)
        first = False

    # --- STATS REPORT ---
    st.divider()
    st.write("#### Technical Workload Stats (Points)")
    st.caption("Points: Sound/Proj/Stream/Cam = 1 Point. Team Lead = 0 Points.")
    
    stats_count = {n: 0 for n in all_team_names}
    
    # Calculate strictly based on the User Rule:
    tech_roles = ["Sound Crew", "Projectionist", "Stream Director", "Cam 1", "Cam 2"]
    
    for r in roster_rows:
        for tr in tech_roles:
            person = r.get(tr, "")
            if person and person != "NO FILL" and person in stats_count:
                stats_count[person] += 1
                
    st_df = pd.DataFrame(list(stats_count.items()), columns=["Name", "Technical Points"])
    st_df = st_df[st_df['Technical Points'] > 0].sort_values(by="Technical Points", ascending=False)
    
    st.dataframe(st_df.T, use_container_width=True)

    # --- DOWNLOAD ---
    c1, c2 = st.columns(2)
    c1.download_button("💾 Download CSV", csv_buf.getvalue(), "roster.csv", "text/csv", type="primary")
    if c2.button("🔄 Start Over"):
        st.session_state.stage = 1
        st.session_state.roster_dates = []
        rerun_script()
