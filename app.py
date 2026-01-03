import streamlit as st
import pandas as pd
import random
import altair as alt
from datetime import datetime, timedelta
from collections import defaultdict
import io

# ==========================================
# 1. ENTERPRISE CONFIGURATION
# ==========================================

st.set_page_config(
    page_title="RosterOS Enterprise",
    page_icon="🟦",
    layout="wide",  # Maximizing screen real estate for productivity
    initial_sidebar_state="expanded"
)

SHEET_ID = "1jh6ScfqpHe7rRN1s-9NYPsm7hwqWWLjdLKTYThRRGUo"

# Microsoft/Office UI Theme
MS_CSS = """
<style>
    /* Global Font - Segoe UI (Windows Standard) */
    html, body, [class*="css"] {
        font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
    }
    
    /* Headers */
    h1, h2, h3 {
        color: #2b579a; /* SharePoint Blue */
        font-weight: 600;
    }

    /* Sidebar Styling */
    section[data-testid="stSidebar"] {
        background-color: #f3f2f1;
        border-right: 1px solid #e1dfdd;
    }

    /* DataFrames/Tables */
    .stDataFrame {
        border: 1px solid #e1dfdd;
    }

    /* Buttons - The "Submit" Blue */
    .stButton > button {
        background-color: #0078d4;
        color: white;
        border-radius: 2px; /* Sharp corners */
        border: none;
        padding: 8px 16px;
    }
    .stButton > button:hover {
        background-color: #106ebe;
    }
    
    /* Metrics */
    div[data-testid="stMetricValue"] {
        color: #0078d4;
        font-size: 1.8rem;
    }
</style>
"""
st.markdown(MS_CSS, unsafe_allow_html=True)

# ==========================================
# 2. DATA LAYER (ROBUST & CACHED)
# ==========================================

@st.cache_data
def fetch_enterprise_data():
    url = f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/export?format=csv&gid=0"
    try:
        df = pd.read_csv(url).fillna("")
        df.columns = df.columns.str.strip().str.lower()
        # Normalization
        renames = {'stream dire': 'stream director', 'team le': 'team lead'}
        cols = {}
        for c in df.columns:
            for k, v in renames.items():
                if k in c: cols[c] = v
        df.rename(columns=cols, inplace=True)
        return df
    except Exception as e:
        st.error(f"System Error: Connection to data source failed. {e}")
        return pd.DataFrame()

# ==========================================
# 3. COMPUTATIONAL ENGINE
# ==========================================

class SchedulerLogic:
    def __init__(self, df, weights):
        self.df = df
        self.names = sorted([n for n in df['name'].unique() if str(n).strip() != ""])
        self.history = defaultdict(int) 
        self.weights = weights # Configurable weights

    def generate_schedule(self, dates, availability_map):
        schedule = []
        
        # Simple Logic for Demo
        # In a real MS Enterprise app, this would be an Azure Function
        
        roles = [
            ("Sound", "sound"),
            ("Projections", "projection"),
            ("Stream", "stream director"),
            ("Cam 1", "camera"),
            ("Cam 2", "camera") # Reuse pool
        ]

        load_tracker = {n: 0 for n in self.names}

        for d_obj in dates:
            d_str = d_obj['Date'].strftime("%Y-%m-%d")
            row = {"Date": d_str, "Service Type": "Standard"}
            
            day_crew = []
            unavailable_today = availability_map.get(d_str, [])

            # Assign Tech
            for r_label, r_col in roles:
                if r_col not in self.df.columns:
                    row[r_label] = "CONFIG_ERR"
                    continue
                
                # Get qualified
                candidates = self.df[self.df[r_col].astype(str) != ""]['name'].tolist()
                
                # Filter Availability & Conflicts
                valid = [
                    c for c in candidates 
                    if c not in unavailable_today 
                    and c not in day_crew
                ]

                if valid:
                    # Weigh by Load (The "Balancer")
                    valid.sort(key=lambda x: (load_tracker[x], random.random()))
                    selected = valid[0]
                    load_tracker[selected] += 1
                    day_crew.append(selected)
                    row[r_label] = selected
                else:
                    row[r_label] = "UNFILLED"

            # Assign Lead
            # Logic: Has "team lead" in sheet or is manually designated
            leads = [p for p in day_crew if 'lead' in self.df[self.df['name']==p].to_string().lower()]
            if not leads:
                # Fallback to anyone with 'team lead' marked in sheet
                if 'team lead' in self.df.columns:
                    potential = self.df[self.df['team lead'].astype(str) != ""]['name'].tolist()
                    leads = [p for p in potential if p not in unavailable_today and p not in day_crew]
            
            row['Team Lead'] = leads[0] if leads else "UNFILLED"

            schedule.append(row)

        return pd.DataFrame(schedule), load_tracker

# ==========================================
# 4. APPLICATION LAYOUT (SIDEBAR NAV)
# ==========================================

def main():
    df_master = fetch_enterprise_data()
    
    # Session State Initialization
    if 'app_mode' not in st.session_state: st.session_state.app_mode = 'Setup'
    if 'generated_df' not in st.session_state: st.session_state.generated_df = None
    if 'avail_matrix' not in st.session_state: st.session_state.avail_matrix = pd.DataFrame()
    if 'target_dates' not in st.session_state: st.session_state.target_dates = []

    # --- SIDEBAR NAVIGATION ---
    with st.sidebar:
        st.title("Admin Console")
        st.markdown("v2.4.1 (Build 8086)")
        
        mode = st.radio("Navigation", ["1. Configuration", "2. Availability", "3. Master Roster", "4. Analytics"])
        
        st.markdown("---")
        st.info("💡 **Pro Tip:** Use the Analytics tab to audit load distribution before exporting.")

    # ==========================
    # TAB 1: CONFIGURATION
    # ==========================
    if mode == "1. Configuration":
        st.header("System Configuration")
        
        c1, c2 = st.columns(2)
        with c1:
            st.subheader("Date Range")
            start_d = st.date_input("Start Date", datetime.now())
            weeks = st.number_input("Duration (Weeks)", min_value=1, value=4)
        
        with c2:
            st.subheader("Algorithm Weights")
            w_load = st.slider("Priority: Load Balancing", 0.0, 1.0, 0.8)
            w_rand = st.slider("Priority: Randomization", 0.0, 1.0, 0.2)

        if st.button("Initialize Session"):
            dates = []
            curr = start_d
            # Find next Sunday
            while curr.weekday() != 6:
                curr += timedelta(days=1)
            
            for _ in range(weeks):
                dates.append({"Date": curr})
                curr += timedelta(days=7)
            
            st.session_state.target_dates = dates
            
            # Init Availability Matrix
            names = sorted(df_master['name'].unique())
            # Create a Grid: Rows = Names, Cols = Dates (Boolean)
            date_strs = [d['Date'].strftime("%Y-%m-%d") for d in dates]
            
            # Using a simplified format for the editor
            # Just a list of names, users will select Dates in next step
            st.success(f"Session initialized for {len(dates)} upcoming services.")

    # ==========================
    # TAB 2: AVAILABILITY (The Grid)
    # ==========================
    elif mode == "2. Availability":
        st.header("Resource Availability")
        
        if not st.session_state.target_dates:
            st.warning("Please configure date range in Tab 1 first.")
            return

        date_options = [d['Date'].strftime("%Y-%m-%d") for d in st.session_state.target_dates]
        all_names = sorted([n for n in df_master['name'].unique() if str(n).strip() != ""])

        # DATA EDITOR APPROACH (Excel Style)
        st.markdown("Mark dates where resources are **UNAVAILABLE**.")
        
        # Prepare data structure for the editor
        # To make it editable, we need a structure. 
        # Let's do a simple DataFrame where Col 1 = Name, Col 2 = Unavailable Dates (Multiselect logic not native in simple editor, so using bool cols)
        
        data_struct = {"Resource Name": all_names}
        for d in date_options:
            data_struct[d] = [False] * len(all_names) # Default available
        
        df_avail_input = pd.DataFrame(data_struct)
        
        # In a real app, we'd load existing state here
        if not st.session_state.avail_matrix.empty:
            # Re-merge if dimensions match, otherwise reset
            if len(st.session_state.avail_matrix) == len(df_avail_input):
               df_avail_input = st.session_state.avail_matrix 

        edited_df = st.data_editor(
            df_avail_input,
            hide_index=True,
            use_container_width=True,
            column_config={
                "Resource Name": st.column_config.TextColumn("Resource", disabled=True)
            }
        )
        
        if st.button("Save Availability State", type="primary"):
            st.session_state.avail_matrix = edited_df
            st.toast("Availability database updated.", icon="💾")

    # ==========================
    # TAB 3: MASTER ROSTER
    # ==========================
    elif mode == "3. Master Roster":
        st.header("Schedule Generation")
        
        col_ops, col_view = st.columns([1, 4])
        
        with col_ops:
            st.subheader("Operations")
            if st.button("Generate Roster", type="primary"):
                if st.session_state.avail_matrix.empty:
                    st.error("Availability data missing.")
                else:
                    # Parse Map
                    avail_map = defaultdict(list)
                    # Convert Boolean grid back to lookup
                    cols = st.session_state.avail_matrix.columns
                    for index, row in st.session_state.avail_matrix.iterrows():
                        name = row["Resource Name"]
                        for c in cols:
                            if c != "Resource Name" and row[c] == True: # If Checked (True) = Unavailable
                                avail_map[c].append(name)
                    
                    eng = SchedulerLogic(df_master, {})
                    res_df, stats = eng.generate_schedule(st.session_state.target_dates, avail_map)
                    st.session_state.generated_df = res_df
                    st.session_state.stats = stats
                    st.success("Optimization Complete.")

            st.markdown("---")
            if st.session_state.generated_df is not None:
                # Excel Export (The Bill Gates Special)
                buffer = io.BytesIO()
                with pd.ExcelWriter(buffer, engine='xlsxwriter') as writer:
                    st.session_state.generated_df.to_excel(writer, index=False, sheet_name='Sheet1')
                
                st.download_button(
                    label="Download .xlsx",
                    data=buffer,
                    file_name="MasterRoster.xlsx",
                    mime="application/vnd.ms-excel"
                )

        with col_view:
            if st.session_state.generated_df is not None:
                st.subheader("Output Matrix")
                # Editable Output - User can manually override the algorithm
                final_edit = st.data_editor(st.session_state.generated_df, use_container_width=True, num_rows="dynamic")
                st.session_state.generated_df = final_edit
            else:
                st.info("Awaiting generation command...")

    # ==========================
    # TAB 4: ANALYTICS (Power BI Lite)
    # ==========================
    elif mode == "4. Analytics":
        st.header("Operational Dashboard")
        
        if st.session_state.generated_df is None:
            st.warning("No roster data generated yet.")
        else:
            # Flatten the roster to count roles
            df = st.session_state.generated_df.copy()
            melted = df.melt(id_vars=["Date", "Service Type", "Details", "Team Lead"], var_name="Role", value_name="Person")
            
            # Combine Lead column
            leads = df[["Date", "Team Lead"]].rename(columns={"Team Lead": "Person"})
            leads["Role"] = "Team Lead"
            combined = pd.concat([melted[["Person", "Role"]], leads[["Person", "Role"]]])
            combined = combined[combined["Person"].isin(["UNFILLED", "CONFIG_ERR", ""]) == False]
            
            c1, c2 = st.columns(2)
            
            with c1:
                st.subheader("Workload Distribution")
                chart = alt.Chart(combined).mark_bar().encode(
                    x=alt.X('count()', title='Shifts Assigned'),
                    y=alt.Y('Person', sort='-x'),
                    color=alt.Color('Role', scale=alt.Scale(scheme='tableau10'))
                ).properties(height=400)
                st.altair_chart(chart, use_container_width=True)

            with c2:
                st.subheader("Role Breakdown")
                pie = alt.Chart(combined).mark_arc().encode(
                    theta=alt.Theta("count()", stack=True),
                    color=alt.Color("Role"),
                    tooltip=["Role", "count()"]
                )
                st.altair_chart(pie, use_container_width=True)
            
            # Key Performance Indicators
            st.markdown("### KPI")
            k1, k2, k3 = st.columns(3)
            total_slots = len(df) * 5 # Approx
            unfilled = len(combined[combined['Person'] == "UNFILLED"])
            k1.metric("Total Shifts Created", len(combined))
            k2.metric("Unfilled Slots", unfilled, delta=-unfilled if unfilled > 0 else 0)
            k3.metric("Unique Volunteers", combined['Person'].nunique())

if __name__ == "__main__":
    main()
