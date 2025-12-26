import streamlit as st
import pandas as pd
from datetime import datetime, timedelta

# ------------------------------------------------------------------
# CONFIGURATION
# ------------------------------------------------------------------
st.set_page_config(page_title="SWS Media Roster", layout="wide")

# ------------------------------------------------------------------
# 1. LOAD DATA (WITH YOUR SPECIFIC LINK)
# ------------------------------------------------------------------
@st.cache_data(ttl=60)
def load_data():
    # I converted your "Edit" link to an "Export" link here:
    sheet_id = "1jh6ScfqpHe7rRN1s-9NYPsm7hwqWWLjdLKTYThRRGUo"
    gid = "0"
    csv_url = f"https://docs.google.com/spreadsheets/d/{sheet_id}/export?format=csv&gid={gid}"

    try:
        df = pd.read_csv(csv_url)
        
        # --- THE FIX: CASE-INSENSITIVE SORTING ---
        # 1. Ensure 'Name' column is text to avoid errors
        # (This handles if you have empty rows or numbers)
        # We look for "Name" or "name"
        name_col = 'Name' if 'Name' in df.columns else 'name'
        if name_col not in df.columns:
            st.error("Could not find a 'Name' column in your Google Sheet.")
            return pd.DataFrame()

        df[name_col] = df[name_col].astype(str)
        
        # 2. Sort A-Z ignoring upper/lowercase
        # This makes 'mich ler' sort alongside 'Micah' immediately
        df = df.sort_values(by=name_col, key=lambda col: col.str.lower())
        
        return df
    except Exception as e:
        st.error("⚠️ Error loading Google Sheet.")
        st.error("1. Please make sure your Google Sheet Share settings are set to **'Anyone with the link'**.")
        st.error(f"Technical Error: {e}")
        return pd.DataFrame()

# ------------------------------------------------------------------
# 2. HELPER FUNCTIONS
# ------------------------------------------------------------------
def get_sunday_dates(start_date, num_weeks):
    dates = []
    current_date = start_date
    while current_date.weekday() != 6: # 6 is Sunday
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
    
    # Identify the correct name column (Name or name)
    name_col = 'Name' if 'Name' in df.columns else 'name'

    # --- STEP 1: SELECT DATES ---
    st.header("Step 1: Select Dates")
    col_d1, col_d2 = st.columns(2)
    with col_d1:
        start_date = st.date_input("Start Date", datetime.today())
    with col_d2:
        num_weeks = st.number_input("Number of Weeks", min_value=1, max_value=12, value=4)
    
    roster_dates = get_sunday_dates(start_date, num_weeks)
    st.info(f"Generating roster for: {', '.join(roster_dates)}")

    # --- STEP 3: UNAVAILABILITY ---
    st.header("Step 3: Unavailability")
    st.info("Select Team Members and mark the dates they are UNAVAILABLE.")

    if 'unavailable_data' not in st.session_state:
        st.session_state.unavailable_data = {}

    with st.container(border=True):
        # Double check sorting here just in case, using case-insensitive key
        # 'mich lo' (lowercase m) will now be treated like 'Mich lo' for sorting purposes
        all_team_members = sorted(df[name_col].unique().tolist(), key=lambda x: str(x).lower())

        cols = st.columns(3) 
        
        for i, name in enumerate(all_team_members):
            # Skip "nan" or empty names if they exist in the sheet
            if name == "nan" or name == "":
                continue

            col_index = i % 3
            with cols[col_index]:
                st.write(f"🚫 **{name}**")
                
                current_selection = st.session_state.unavailable_data.get(name, [])
                
                unavailable_dates = st.multiselect(
                    "Choose options",
                    roster_dates,
                    default=list(set(current_selection) & set(roster_dates)),
                    key=f"unav_{name}",
                    label_visibility="collapsed"
                )
                
                st.session_state.unavailable_data[name] = unavailable_dates

    # --- STEP 4: GENERATE BUTTON ---
    st.write("---")
    if st.button("Generate Roster", type="primary"):
        st.success("Logic running...")
        
        # Display current unavailability to verify
        chk_data = []
        for name in all_team_members:
             # Skip empty names
            if name == "nan" or name == "": continue

            dates = st.session_state.unavailable_data.get(name, [])
            if dates:
                chk_data.append({"Name": name, "Unavailable": ", ".join(dates)})
        
        if chk_data:
            st.write("### Recorded Unavailability (Sorted):")
            st.dataframe(chk_data)
        else:
            st.write("No unavailability recorded.")
