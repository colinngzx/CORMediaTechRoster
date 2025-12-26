import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
import random
from datetime import datetime, timedelta

# --- CONFIG ---
st.set_page_config(page_title="SWS Matrix Roster", page_icon="📅", layout="wide")
st.title("📅 Church Roster: Matrix View")

# --- DIRECT CONNECTION SETUP ---
# We represent the connection object but put the URL directly here to avoid Secrets errors
conn = st.connection("gsheets", type=GSheetsConnection)

# YOUR PUBLIC SHEET URL
SHEET_URL = "https://docs.google.com/spreadsheets/d/1jh6ScfqpHe7rRN1s-9NYPsm7hwqWWLjdLKTYThRRGUo/edit?usp=sharing"

def get_data():
    # We pass the URL directly to the read function
    try:
        team_df = conn.read(spreadsheet=SHEET_URL, worksheet="Team", ttl=0).astype(str)
        # Check if Unavailability exists, otherwise make empty
        try:
            unavail_df = conn.read(spreadsheet=SHEET_URL, worksheet="Unavailability", ttl=0).astype(str)
        except:
            unavail_df = pd.DataFrame(columns=["Name", "Date"])
            
        team_df = team_df.fillna("")
        return team_df, unavail_df
    except Exception as e:
        return None, None, e

# Load Data
team_df, unavail_df, error = get_data()

# Error Handling
if error:
    st.error(f"⚠️ Could not load data. Error: {error}")
    st.info("Troubleshooting: Make sure your Google Sheet has a tab named 'Team' and a tab named 'Unavailability'.")
    st.stop()

# --- INIT SESSION STATE ---
if "draft_matrix" not in st.session_state:
    st.session_state.draft_matrix = None

# --- SIDEBAR ---
mode = st.sidebar.radio("Mode", ["I am a Team Member", "I am the Admin"])

# --- MEMBER MODE ---
if mode == "I am a Team Member":
    st.header("📝 Submit Away Dates")
    names = sorted(team_df['Name'].unique().tolist())
    selected_name = st.selectbox("Select your name", names)
    away_date = st.date_input("When are you away?", min_value=datetime.today())
    
    if st.button("Submit Unavailability"):
        new_row = pd.DataFrame([{"Name": selected_name, "Date": str(away_date)}])
        
        # Determine if we are appending to existing or starting fresh
        if unavail_df.empty:
            updated_df = new_row
        else:
            updated_df = pd.concat([unavail_df, new_row], ignore_index=True)
            
        conn.update(spreadsheet=SHEET_URL, worksheet="Unavailability", data=updated_df)
        st.success("Saved!")
        st.cache_data.clear()

# --- ADMIN MODE ---
elif mode == "I am the Admin":
    st.header("⚙️ Roster Generator (Matrix)")
    
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

        if st.button("🚀 Generate Draft Roster", type="primary"):
            matrix_dict = {} 
            
            for role_name, _ in roles_config:
                matrix_dict[role_name] = []

            date_headers = []
            current_date = start_date
            
            for _ in range(weeks):
                date_str_short = current_date.strftime("%d-%b")
                date_headers.append(date_str_short)
                date_str_full = str(current_date)
                
                # Check Unavailability
                if 'Date' in unavail_df.columns:
                    away_today = unavail_df[unavail_df['Date'] == date_str_full]['Name'].tolist()
                else:
                    away_today = []
                
                working_today = []
                
                # --- FILL ROLES ---
                for role_label, search_keyword in roles_config:
                    
                    # 1. CAM 2 (Always Blank)
                    if role_label == "Cam 2":
                        candidates = []

                    # 2. TEAM LEAD (Darrell Logic)
                    elif role_label == "Team Lead":
                        all_candidates = team_df[
                            (team_df['team lead'].str.contains("yes", case=False)) &
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
                                team_df['Role 1'].str.contains(search_keyword, case=False) | 
                                team_df['Role 2'].str.contains(search_keyword, case=False) | 
                                team_df['Role 3'].str.contains(search_keyword, case=False)
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

            # Transpose
            df = pd.DataFrame(matrix_dict)
            df = df.T 
            df.columns = date_headers
            st.session_state.draft_matrix = df

        # EDITOR SECTION
        if st.session_state.draft_matrix is not None:
            st.divider()
            st.subheader("✏️ Edit Matrix")
            st.caption("Double-click any cell to edit.")
            
            edited_matrix = st.data_editor(
                st.session_state.draft_matrix,
                use_container_width=True
            )
            
            if st.button("💾 Save Final Roster"):
                save_df = edited_matrix.reset_index()
                save_df = save_df.rename(columns={"index": "Role"})
                conn.update(spreadsheet=SHEET_URL, worksheet="Roster", data=save_df)
                st.success("✅ Roster Published!")

    elif password:
        st.error("Incorrect Password")
