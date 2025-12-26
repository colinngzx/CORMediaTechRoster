import streamlit as st
import pandas as pd

# ==========================================
# 1. CONFIGURATION & CONSTANTS
# ==========================================

# Your specific Google Sheet ID
SHEET_ID = "1jh6ScfqpHe7rRN1s-9NYPsm7hwqWWLjdLKTYThRRGUo"
SHEET_GID = "0" # The first tab is usually "0"

# The logic: We ask Google for a CSV export of that sheet
CSV_URL = f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/export?format=csv&gid={SHEET_GID}"

# The Role Definitions (Static)
ROLES_BF = [
    {'id': 'lead', 'name': 'Team Lead', 'type': 'lead'},
    {'id': 'stream', 'name': 'Stream Director', 'type': 'tech'},
    {'id': 'projection', 'name': 'Projectionist', 'type': 'tech'},
    {'id': 'sound', 'name': 'Sound Crew', 'type': 'tech'},
    {'id': 'cam1', 'name': 'Cam 1', 'type': 'tech'},
    {'id': 'cam2', 'name': 'Cam 2', 'type': 'tech'},
]

# ==========================================
# 2. DATA LOADING FUNCTION
# ==========================================

@st.cache_data(ttl=600)  # Refresh data from Google every 600 seconds (10 mins)
def load_team_from_sheet():
    """
    Fetches the Google Sheet, reads the columns, and converts them 
    into the format the app expects.
    """
    try:
        # Load CSV using Pandas
        df = pd.read_csv(CSV_URL)
        
        # Replace NaN (empty cells) with empty string to prevent errors
        df = df.fillna("")
        
        team_list = []
        
        # Calculate ID counter
        count = 1

        for _, row in df.iterrows():
            name = str(row['Name']).strip()
            
            # Skip if name is empty
            if not name:
                continue

            person_roles = []

            # --- MAPPING LOGIC ---
            # Checks if the Google Sheet cell has ANY text (Yes, x, etc)
            
            # Team Lead
            if str(row['Team Lead']).strip():
                person_roles.append('lead')
                
            # Stream Director
            if str(row['Stream Director']).strip():
                person_roles.append('stream')
                
            # Sound
            if str(row['Sound']).strip():
                person_roles.append('sound')
                
            # Projection
            if str(row['Projection']).strip():
                person_roles.append('projection')
            
            # Camera - Assigns BOTH Cam 1 and Cam 2 capability
            if str(row['Camera']).strip():
                person_roles.append('cam1')
                person_roles.append('cam2')

            # Add to list if they have at least one role
            if person_roles:
                team_list.append({
                    'id': count,
                    'name': name,
                    'roles': person_roles
                })
                count += 1
                
        return team_list

    except Exception as e:
        st.error(f"⚠️ Error connecting to Google Sheets: {e}")
        return []

# ==========================================
# 3. HELPER FUNCTIONS
# ==========================================

def get_people_for_role(role_id, team_data):
    """Filters the team list for people who can do a specific role."""
    return [p['name'] for p in team_data if role_id in p['roles']]

# ==========================================
# 4. MAIN APP UI
# ==========================================

def main():
    st.set_page_config(page_title="Team Roster", layout="wide")
    
    st.title("📹 Tech Team Roster")
    
    # --- A. Load Data ---
    with st.spinner('Syncing with Google Sheets...'):
        team_members = load_team_from_sheet()

    if not team_members:
        st.warning("No team members found. Please check your Google Sheet.")
        st.stop()
        
    # --- B. Admin/Debug View (Optional sidebar) ---
    with st.sidebar:
        st.header("Data Status")
        st.success(f"✅ Live Connection Active")
        st.write(f"**Total Members:** {len(team_members)}")
        
        if st.button("Refresh Data Now"):
            st.cache_data.clear()
            st.rerun()
            
        with st.expander("See Raw Data"):
            st.json(team_members)

    # --- C. The Scheduling Interface ---
    st.markdown("### 📅 Weekly Schedule")
    
    # Create columns for the roles
    # We map through our defined roles to create dropdowns
    
    cols = st.columns(3) # create a grid layout
    
    assignments = {}
    
    for index, role in enumerate(ROLES_BF):
        # Determine which column to place this dropdown in
        col = cols[index % 3]
        
        with col:
            # 1. Find who can do this job
            eligible_people = get_people_for_role(role['id'], team_members)
            
            # 2. Create the dropdown
            selected = st.selectbox(
                f"Select {role['name']}",
                options=["Unassigned"] + eligible_people,
                key=role['id']
            )
            
            if selected != "Unassigned":
                assignments[role['name']] = selected

    # --- D. Summary Section ---
    st.divider()
    st.subheader("📝 Deployment Summary")
    
    if assignments:
        for role, person in assignments.items():
            st.write(f"**{role}:** {person}")
    else:
        st.info("Select members above to see the summary.")

if __name__ == "__main__":
    main()
