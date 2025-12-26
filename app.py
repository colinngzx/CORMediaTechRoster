import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
import random

# ------------------------------------------------------------------
# CONFIGURATION & SETUP
# ------------------------------------------------------------------
st.set_page_config(page_title="SWS Media Roster", layout="wide")

# ------------------------------------------------------------------
# 1. LOAD DATA FUNCTION
# ------------------------------------------------------------------
# Replace this URL with your specific Google Sheet 'published to web' CSV link
# OR keep your existing connection method if you use st.connection
SHEET_ID = "1W4a5k-7kHjXwFhXyZ1_aKj5mNnOPqRsTuvWxYzAbCdE" # <--- REPLACE WITH YOUR ID IF NEEDED
SHEET_NAME = "Sheet1" # <--- REPLACE WITH YOUR SHEET NAME
CSV_URL = f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/gviz/tq?tqx=out:csv&sheet={SHEET_NAME}"

@st.cache_data(ttl=60)
def load_data():
    try:
        # You can replace this line with your specific st.connection code if you prefer
        # But this works for any Public Google Sheet or CSV export
        df = pd.read_csv(CSV_URL)
        
        # --- THE FIX: CLEAN UP & SORT DATA IMMEDIATELY ---
        
        # 1. Ensure 'Name' column is treated as text (string)
        df['Name'] = df['Name'].astype(str)
        
        # 2. Sort the WHOLE dataframe alphabetically A-Z (Case Insensitive)
        # This makes 'mich lo' appear right after 'Micah' automatically everywhere
        df = df.sort_values(by='Name', key=lambda col: col.str.lower())
        
        return df
    except Exception as e:
        st.error(f"Error loading data: {e}")
        return pd.DataFrame()

# ------------------------------------------------------------------
# 2. HELPER FUNCTIONS
# ------------------------------------------------------------------
def get_sunday_dates(start_date, num_weeks):
    dates = []
    current_date = start_date
    # Find next Sunday if start is not Sunday
    while current_date.weekday() != 6:
        current_date += timedelta(days=1)
    
    for _ in range(num_weeks):
        dates.append(current_date.strftime("%d-%b"))
        current_date += timedelta(weeks=1)
    return dates

# ------------------------------------------------------------------
# 3. MAIN APP INTERFACE
# ------------------------------------------------------------------

st.title("🎛️ SWS Media Roster Generator")
df = load_data()

if not df.empty:
    
    # --- STEP 1: SELECT DATES ---
    st.header("Step 1: Select Dates")
    col_d1, col_d2 = st.columns(2)
    with col_d1:
        start_date = st.date_input("Start Date", datetime.today())
    with col_d2:
        num_weeks = st.number_input("Number of Weeks to Generate", min_value=1, max_value=12, value=4)
    
    roster_dates = get_sunday_dates(start_date, num_weeks)
    st.info(f"Generating roster for: {', '.join(roster_dates)}")

    # --- STEP 2: DEFINE ROLES ---
    st.header("Step 2: Role Requirements")
    # Define roles needed (Hardcoded for simplicity, or can be dynamic)
    roles_needed = ["Stream Director", "Audio/Sound", "Camera", "Projection"]
    role_config = {}
    
    cols = st.columns(len(roles_needed))
    for i, role in enumerate(roles_needed):
        with cols[i]:
            count = st.number_input(f"{role}", min_value=0, value=1, key=f"role_{i}")
            role_config[role] = count

    # --- STEP 3: UNAVAILABILITY (ALPHABETICAL FIX APPLIED HERE) ---
    st.header("Step 3: Unavailability")
    st.info("Select Team Members and mark the dates they are UNAVAILABLE.")

    # Initialize unavailability in session state if not exists
    if 'unavailable_data' not in st.session_state:
        st.session_state.unavailable_data = {}

    with st.container(border=True):
        # We extract the names. KEY FIX: Use the key=str.lower to ensure sorting logic holds
        # although df is already sorted, we double-ensure the list extraction is clean.
        all_team_members = sorted(df['Name'].unique().tolist(), key=lambda x: str(x).lower())

        # CSS Grid layout for visual names
        cols = st.columns(3) # Create 3 columns
        
        for i, name in enumerate(all_team_members):
            col_index = i % 3
            with cols[col_index]:
                st.write(f"🚫 **{name}**")
                
                # Retrieve previous selection if exists
                current_selection = st.session_state.unavailable_data.get(name, [])
                
                # Multiselect for dates
                unavailable_dates = st.multiselect(
                    "Choose options",
                    roster_dates,
                    default=list(set(current_selection) & set(roster_dates)), # Keep only valid dates
                    key=f"unav_{name}",
                    label_visibility="collapsed"
                )
                
                # Save to session state
                st.session_state.unavailable_data[name] = unavailable_dates

    # --- STEP 4: GENERATE ---
    st.write("---")
    if st.button("Generate Roster", type="primary"):
        st.success("Roster Generation Logic would run here (add your solver logic).")
        
        # EXAMPLE DEBUG OUTPUT TO SHOW SORTING WORKS
        st.write("### Debug: Availability Check")
        processed_data = []
        for name in all_team_members:
            dates_out = st.session_state.unavailable_data.get(name, [])
            status = f"❌ Unavailable: {dates_out}" if dates_out else "✅ Available"
            processed_data.append({"Name": name, "Status": status})
        
        st.dataframe(pd.DataFrame(processed_data), use_container_width=True)

else:
    st.warning("Could not load Google Sheet data. Please check your URL.")
