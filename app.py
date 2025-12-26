import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
import random
import collections

# --- PAGE SETUP ---
st.set_page_config(page_title="Roster Wizard", page_icon="🧙‍♂️", layout="wide")

# --- CSS FOR BETTER STYLING ---
st.markdown("""
    <style>
    .stTextArea textarea { font-family: monospace; }
    .block-container { padding-top: 2rem; }
    </style>
""", unsafe_allow_html=True)

# --- SESSION STATE INITIALIZATION ---
if 'stage' not in st.session_state:
    st.session_state.stage = 1

# Store the inputs
if 'setup_data' not in st.session_state:
    st.session_state.setup_data = {}

if 'event_settings' not in st.session_state:
    st.session_state.event_settings = {}

if 'final_roster' not in st.session_state:
    st.session_state.final_roster = None

# --- FUNCTIONS ---

def generate_sundays(start_date, num_weeks):
    dates = []
    current_date = start_date
    # Find next Sunday
    while current_date.weekday() != 6:
        current_date += timedelta(days=1)
    
    for _ in range(num_weeks):
        dates.append(current_date)
        current_date += timedelta(weeks=1)
    return dates

def reset_app():
    st.session_state.stage = 1
    st.session_state.setup_data = {}
    st.session_state.event_settings = {}
    st.session_state.final_roster = None
    st.rerun()

# ==========================================
# STEP 1: SETUP (CLASSIC TEXT FORMAT)
# ==========================================
def render_step_1():
    st.title("🧙‍♂️ Roster Wizard")
    st.info("Define your dates, roles, and team members below.")
    
    c1, c2 = st.columns(2)
    with c1:
        start_date = st.date_input("Start Date", datetime.today())
    with c2:
        num_weeks = st.number_input("Number of Weeks", min_value=1, max_value=52, value=4)
    
    st.divider()
    
    col_roles, col_people = st.columns(2)
    
    with col_roles:
        st.subheader("Roles")
        st.caption("Enter one role per line.")
        default_roles = "Team Lead\nSound Crew\nProjectionist\nStream Director\nCam 1"
        roles_text = st.text_area("Roles Input", value=default_roles, height=300, label_visibility="collapsed")
        
    with col_people:
        st.subheader("Team Members")
        st.caption("Enter one name per line.")
        default_people = "Darell\nJohn\nJane\nMike\nSarah\nEmily\nChris\nAlex"
        people_text = st.text_area("People Input", value=default_people, height=300, label_visibility="collapsed")

    if st.button("Next: Configure Dates ➡️", type="primary"):
        # Process Inputs
        roles = [r.strip() for r in roles_text.split('\n') if r.strip()]
        people = [p.strip() for p in people_text.split('\n') if p.strip()]
        
        if not roles or not people:
            st.error("Please ensure you have at least one role and one team member.")
        else:
            dates = generate_sundays(start_date, num_weeks)
            
            # Save to session state
            st.session_state.setup_data = {
                'roles': roles,
                'people': people,
                'dates': dates
            }
            # Initialize settings for Step 2
            st.session_state.event_settings = {
                d: {"HC": False, "MSS": False, "Note": ""} for d in dates
            }
            st.session_state.stage = 2
            st.rerun()

# ==========================================
# STEP 2: EVENT SETTINGS (LIST VIEW)
# ==========================================
def render_step_2():
    st.title("Step 2: Event Details")
    st.write("Customize specific Sundays below.")

    dates = st.session_state.setup_data['dates']
    
    # Headers
    h1, h2, h3, h4 = st.columns([2, 1, 1, 3])
    h1.markdown("**Date**")
    h2.markdown("**Holy Comm.**")
    h3.markdown("**MSS Combined**")
    h4.markdown("**Notes**")
    st.divider()

    # List all dates
    for d in dates:
        c1, c2, c3, c4 = st.columns([2, 1, 1, 3])
        
        d_str = d.strftime("%d-%b-%Y")
        c1.write(f"📅 {d_str}")
        
        # Checkboxes and Input
        # Note: keys must be unique per widget
        is_hc = c2.checkbox("HC", key=f"hc_{d}", value=st.session_state.event_settings[d]["HC"])
        is_mss = c3.checkbox("MSS", key=f"mss_{d}", value=st.session_state.event_settings[d]["MSS"])
        note = c4.text_input("Note", key=f"note_{d}", value=st.session_state.event_settings[d]["Note"], label_visibility="collapsed", placeholder="Optional info")
        
        # Update State immediately on interaction
        st.session_state.event_settings[d] = {
            "HC": is_hc,
            "MSS": is_mss,
            "Note": note
        }
        st.divider()

    c_back, c_gen = st.columns([1, 5])
    if c_back.button("⬅️ Back"):
        st.session_state.stage = 1
        st.rerun()
    
    if c_gen.button("🧙‍♂️ Generate Roster", type="primary"):
        generate_roster_logic()
        st.session_state.stage = 3
        st.rerun()

# ==========================================
# STEP 3: GENERATION LOGIC
# ==========================================
def generate_roster_logic():
    data = st.session_state.setup_data
    settings = st.session_state.event_settings
    
    roles = data['roles']
    people = data['people']
    dates = data['dates']
    
    # Tracking usage for load balancing
    global_usage = collections.Counter({p: 0 for p in people})
    
    roster_rows = []
    
    for d in dates:
        day_settings = settings[d]
        
        # Skip logic: If MSS Combined, we might skip standard roster 
        # (Assuming here we still roster unless user manually typed "None" in previous step, 
        # but for this script we will fill slots available.)
        
        daily_assignments = {}
        # Shuffle people for randomness
        available_people = people.copy()
        random.shuffle(available_people)
        
        # Sort available people by usage (least used first) to balance load
        available_people.sort(key=lambda p: global_usage[p])
        
        # 1. ASSIGN TEAM LEAD FIRST (Critical for Darell logic)
        # We need to process roles. Find Team Lead index if it exists, move to front
        ordered_roles = roles.copy()
        if "Team Lead" in ordered_roles:
            ordered_roles.remove("Team Lead")
            ordered_roles.insert(0, "Team Lead")
            
        for role in ordered_roles:
            selected_person = None
            
            # Try to find a person for this role
            for candidate in available_people:
                
                # --- LOGIC: DARELL RULE ---
                # "If assigned Team Lead, cannot be Sound Crew"
                # Since we assign Team Lead first (see sort above), we check:
                # If current role is Sound Crew, and Candidate is Darell, check if Darell is already Team Lead today.
                
                if role == "Sound Crew" and candidate == "Darell":
                    if daily_assignments.get("Team Lead") == "Darell":
                        continue # Skip Darell for Sound if he is TL
                
                # --- LOGIC: TEAM LEAD VS SOUND REVERSE ---
                # If we are assigning Team Lead, and by some quirk he is already Sound (unlikely given order, but safe to check)
                if role == "Team Lead" and candidate == "Darell":
                    if daily_assignments.get("Sound Crew") == "Darell":
                        continue

                # If we pass checks, select this person
                selected_person = candidate
                break
            
            if selected_person:
                daily_assignments[role] = selected_person
                available_people.remove(selected_person)
                global_usage[selected_person] += 1
            else:
                daily_assignments[role] = "TBD" # Could not find anyone matching constraints
        
        # Build Row
        row = {
            "Date": d.strftime("%Y-%m-%d"),
            "Note": day_settings['Note'],
            "Setup": [] # To collect tags
        }
        if day_settings['HC']: row['Setup'].append("HC")
        if day_settings['MSS']: row['Setup'].append("MSS")
        row['Setup'] = ", ".join(row['Setup'])
        
        # Add roles to row
        for r in roles:
            row[r] = daily_assignments.get(r, "-")
            
        roster_rows.append(row)
    
    st.session_state.final_roster = pd.DataFrame(roster_rows)

# ==========================================
# STEP 4: OUTPUT
# ==========================================
def render_step_3_output():
    st.title("✅ Final Roster")
    
    df = st.session_state.final_roster
    
    # 1. Expander for Statistics
    with st.expander("📊 View Workload Statistics (Click to Open)"):
        st.write("Number of times each person is rostered:")
        
        # Calculate stats dynamically from the result df
        roles = st.session_state.setup_data['roles']
        # Melt dataframe to get a long list of all assigned names
        melted = df[roles].melt(value_name="Person")
        counts = melted['Person'].value_counts().reset_index()
        counts.columns = ['Person', 'Count']
        # Filter out TBD or Placeholders
        counts = counts[counts['Person'] != "TBD"]
        counts = counts[counts['Person'] != "-"]
        
        st.bar_chart(counts.set_index('Person'))
        st.table(counts)

    # 2. Main Roster Table
    st.dataframe(df, use_container_width=True, hide_index=True)
    
    # 3. Download Button
    csv = df.to_csv(index=False).encode('utf-8')
    st.download_button(
        "📥 Download as CSV",
        csv,
        "church_roster.csv",
        "text/csv",
        key='download-csv'
    )
    
    if st.button("🔄 Start Over"):
        reset_app()

# ==========================================
# MAIN APP FLOW
# ==========================================
if st.session_state.stage == 1:
    render_step_1()
elif st.session_state.stage == 2:
    render_step_2()
elif st.session_state.stage == 3:
    render_step_3_output()
