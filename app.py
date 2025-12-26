import streamlit as st
import pandas as pd
import random
from datetime import datetime, timedelta
import io

# --- CONFIG ---
st.set_page_config(page_title="SWS Matrix Roster", page_icon="📅", layout="wide")
st.title("📅 Church Roster: Matrix Generator")

# --- DATA LOADING FUNCTION ---
# We use the direct CSV export link 'gviz' trick which works 100% of the time for public sheets
SHEET_ID = "1jh6ScfqpHe7rRN1s-9NYPsm7hwqWWLjdLKTYThRRGUo"

def load_data():
    try:
        # Load Team Tab
        url_team = f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/gviz/tq?tqx=out:csv&sheet=Team"
        team_df = pd.read_csv(url_team).fillna("")
        
        # Load Unavailability Tab
        url_unavail = f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/gviz/tq?tqx=out:csv&sheet=Unavailability"
        try:
            unavail_df = pd.read_csv(url_unavail).fillna("")
        except:
            # If tab doesn't exist or is empty
            unavail_df = pd.DataFrame(columns=["Name", "Date"])
            
        # Ensure Unavailability dates are strings conformant to comparison
        if 'Date' in unavail_df.columns:
            unavail_df['Date'] = unavail_df['Date'].astype(str)
            
        return team_df, unavail_df, None
    except Exception as e:
        return None, None, e

# --- LOAD ---
team_df, unavail_df, error = load_data()

if error:
    st.error("Could not read the Google Sheet.")
    st.warning("Make sure the sheet is Public (Anyone with link) and the tab names are 'Team' and 'Unavailability'.")
    st.stop()

# --- ADMIN INTERFACE ---
st.info("ℹ️ Because we are not using a Service Key, this app is Read-Only. Use the Download button at the end to save your roster.")

password = st.text_input("Admin Password", type="password")

if password == "admin123":
    c1, c2 = st.columns(2)
    start_date = c1.date_input("Start Date (Sunday)")
    weeks = c2.slider("Weeks to generate", 4, 12, 8)
    
    # DEFINITIONS
    roles_config = [
        ("Sound Crew", "sound"),
        ("Projectionist", "projection"),
        ("Stream Director", "stream"),
        ("Cam 1", "camera"),
        ("Cam 2", "camera_2_placeholder"), 
        ("Team Lead", "team lead") 
    ]

    # --- GENERATION LOGIC ---
    if st.button("🚀 Generate Roster", type="primary"):
        st.session_state.draft_matrix = None # Reset
        
        matrix_dict = {} 
        for role_name, _ in roles_config:
            matrix_dict[role_name] = []

        date_headers = []
        current_date = start_date
        
        for _ in range(weeks):
            date_str_short = current_date.strftime("%d-%b")
            date_headers.append(date_str_short)
            date_str_full = str(current_date)
            
            # Check Unavailability (Convert pandas dates to string for matching)
            # We try to match what the user typed or YYYY-MM-DD
            # To be safe, we look for partial matches on the date string
            away_today = []
            if 'Date' in unavail_df.columns:
                 away_today = unavail_df[unavail_df['Date'].str.contains(date_str_full, na=False)]['Name'].tolist()
            
            working_today = []
            
            # --- FILL ROLES ---
            for role_label, search_keyword in roles_config:
                
                # 1. CAM 2 (Always Blank)
                if role_label == "Cam 2":
                    candidates = []

                # 2. TEAM LEAD (Darrell Logic)
                elif role_label == "Team Lead":
                    # Filter matching "team lead" or "yes"
                    all_candidates = team_df[
                        (team_df['team lead'].astype(str).str.contains("yes", case=False)) &
                        (~team_df['Name'].isin(away_today)) &
                        (~team_df['Name'].isin(working_today))
                    ]['Name'].tolist()
                    
                    if all_candidates:
                        others = [x for x in all_candidates if "darrell" not in x.lower()]
                        if others:
                            candidates = others 
                        else:
                            candidates = all_candidates
                    else:
                        candidates = []

                # 3. STANDARD ROLES
                else:
                    candidates = team_df[
                        (
                            team_df['Role 1'].astype(str).str.contains(search_keyword, case=False) | 
                            team_df['Role 2'].astype(str).str.contains(search_keyword, case=False) | 
                            team_df['Role 3'].astype(str).str.contains(search_keyword, case=False)
                        ) & 
                        (~team_df['Name'].isin(away_today)) &
                        (~team_df['Name'].isin(working_today))
                    ]['Name'].tolist()

                # --- SELECTION ---
                if candidates:
                    pick = random.choice(candidates)
                    working_today.append(pick)
                    matrix_dict[role_label].append(pick)
                else:
                    matrix_dict[role_label].append("")

            current_date = current_date + timedelta(days=7)

        # Transpose to Matrix
        df = pd.DataFrame(matrix_dict)
        df = df.T 
        df.columns = date_headers
        st.session_state.draft_matrix = df

    # --- DISPLAY & DOWNLOAD ---
    if "draft_matrix" in st.session_state and st.session_state.draft_matrix is not None:
        st.divider()
        st.subheader("Results")
        
        # Interactive Editor
        edited_matrix = st.data_editor(st.session_state.draft_matrix, use_container_width=True)
        
        st.write("### How to Save")
        st.write("1. Click the Download button below.")
        st.write("2. Open the CSV file.")
        st.write("3. Copy the data and Paste it into your Google Sheet 'Roster' tab.")
        
        # CSV Download Button
        csv_buffer = io.BytesIO()
        edited_matrix.to_csv(csv_buffer)
        st.download_button(
            label="💾 Download Roster CSV",
            data=csv_buffer.getvalue(),
            file_name="roster_matrix.csv",
            mime="text/csv"
        )

elif password:
    st.error("Incorrect Password")
