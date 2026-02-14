import streamlit as st
import pandas as pd
import random
import calendar
from datetime import datetime, date, timedelta
from collections import defaultdict

# ==========================================
# 1. INITIAL SETTINGS & DATA FETCH
# ==========================================
SHEET_ID = "1jh6ScfqpHe7rRN1s-9NYPsm7hwqWWLjdLKTYThRRGUo"
GIDS = {
    "Media Tech": "0",
    "Welcome Ministry": "2080125013"
}

st.set_page_config(page_title="Church Roster Automator", layout="wide")

@st.cache_data(ttl=600)
def fetch_sheet_data(ministry):
    gid = GIDS.get(ministry, "0")
    url = f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/export?format=csv&gid={gid}"
    try:
        df = pd.read_csv(url).fillna("")
        df.columns = df.columns.str.strip().str.lower()
        return df
    except Exception as e:
        st.error(f"Error fetching sheet: {e}")
        return pd.DataFrame()

# ==========================================
# 2. SCHEDULING ENGINE (WELCOME RULES)
# ==========================================
class WelcomeEngine:
    def __init__(self, df):
        self.df = df
        self.total_load = defaultdict(int)
        self.prev_week_crew = []

    def get_ui_name(self, name):
        if not name: return ""
        row = self.df[self.df['name'] == name].iloc[0]
        tags = []
        if str(row.get('male', '')).lower() == 'yes': tags.append("M")
        if str(row.get('senior citizen', '')).lower() == 'yes': tags.append("S")
        return f"{name} ({', '.join(tags)})" if tags else name

    def generate_roster(self, dates_meta, unavailability):
        roster_data = []
        leaders_pool = self.df[self.df['team lead'].astype(str).str.lower() == 'yes']['name'].tolist()
        members_pool = self.df[self.df['member'].astype(str).str.lower() == 'yes']['name'].tolist()

        for meta in dates_meta:
            d_str = meta['Date'].strftime("%Y-%m-%d")
            is_hc = meta.get('HC', False)
            is_combined = meta.get('Combined', False)
            
            # Logic: Combined services might have different sizes, 
            # but standardizing to HC size (5) for now as a default
            team_size = 5 if (is_hc or is_combined) else 4
            unav = unavailability.get(d_str, [])
            crew = []
            
            row = {"Date": meta['Date'].strftime("%d-%b"), "Note": ""}
            if is_hc: row["Note"] = "HC"
            if is_combined: row["Note"] = "Combined"

            # 1. Team Lead
            avail_l = [l for l in leaders_pool if l not in unav and l not in self.prev_week_crew]
            if not avail_l: avail_l = [l for l in leaders_pool if l not in unav]
            
            if avail_l:
                avail_l.sort(key=lambda x: (self.total_load[x], random.uniform(0, 1)))
                leader = avail_l[0]
                row["Team Lead"] = self.get_ui_name(leader)
                crew.append(leader)
                self.total_load[leader] += 1

            # 2. Members
            while len(crew) < team_size:
                needs_m = not any(self.df[self.df['name']==p]['male'].str.lower().item()=='yes' for p in crew if p in members_pool)
                needs_s = not any(self.df[self.df['name']==p]['senior citizen'].str.lower().item()=='yes' for p in crew if p in members_pool)
                
                pool = [n for n in members_pool if n not in crew and n not in unav and n not in self.prev_week_crew]
                if not pool: pool = [n for n in members_pool if n not in crew and n not in unav]
                if not pool: break

                def rank_member(n):
                    score = self.total_load[n]
                    r = self.df[self.df['name'] == n].iloc[0]
                    if needs_m and str(r.get('male','')).lower() == 'yes': score -= 10
                    if needs_s and str(r.get('senior citizen','')).lower() == 'yes': score -= 10
                    return (score, random.uniform(0, 1))

                pool.sort(key=rank_member)
                pick = pool[0]
                
                # Couple Logic
                row_data = self.df[self.df['name'] == pick]
                c_id = str(row_data['couple'].iloc[0]).strip()
                partner = ""
                if c_id:
                    p_df = self.df[(self.df['couple'].astype(str)==c_id) & (self.df['name']!=pick)]
                    partner = p_df['name'].iloc[0] if not p_df.empty else ""

                if partner and len(crew) + 2 > team_size:
                    singles = [p for p in pool if not str(self.df[self.df['name']==p]['couple'].iloc[0]).strip()]
                    if not singles: break
                    pick = singles[0]
                    partner = ""

                row[f"Member {len(crew)}"] = self.get_ui_name(pick)
                crew.append(pick)
                self.total_load[pick] += 1
                if partner:
                    row[f"Member {len(crew)}"] = self.get_ui_name(partner)
                    crew.append(partner)
                    self.total_load[partner] += 1

            self.prev_week_crew = crew
            roster_data.append(row)
            
        return pd.DataFrame(roster_data)

# ==========================================
# 3. USER JOURNEY (4 STAGES)
# ==========================================
def main():
    if 'stage' not in st.session_state: st.session_state.stage = 1
    if 'ministry' not in st.session_state: st.session_state.ministry = None

    # --- STAGE 1: MINISTRY & PERIOD ---
    if st.session_state.stage == 1:
        st.title("🛡️ Step 1: Ministry & Period")
        
        # Ministry Selection
        st.session_state.ministry = st.selectbox("Which ministry are you from?", ["Media Tech", "Welcome Ministry"])
        
        col1, col2 = st.columns(2)
        year = col1.number_input("Year", value=date.today().year)
        
        # Auto-select next 3 months
        current_month_val = date.today().month
        next_3_months = []
        for i in range(1, 4):
            m_idx = (current_month_val + i - 1) % 12 + 1
            next_3_months.append(calendar.month_name[m_idx])
            
        months = col2.multiselect("Select Months", list(calendar.month_name)[1:], default=next_3_months)
        
        if st.button("Generate Dates"):
            m_idx_map = {m: i for i, m in enumerate(calendar.month_name)}
            st.session_state.roster_dates = [
                {"Date": date(year, m_idx_map[m], d), "HC": False, "Combined": False} 
                for m in months for d in range(1, calendar.monthrange(year, m_idx_map[m])[1]+1) 
                if date(year, m_idx_map[m], d).weekday() == 6
            ]
            st.session_state.stage = 2
            st.rerun()

    # --- STAGE 2: SERVICE TYPES ---
    elif st.session_state.stage == 2:
        st.title("⛪ Step 2: Service Types")
        st.info(f"Setting up the roster for **{st.session_state.ministry}**.")
        st.session_state.roster_dates = st.data_editor(st.session_state.roster_dates, use_container_width=True)
        if st.button("Next: Availability"):
            st.session_state.stage = 3
            st.rerun()

    # --- STAGE 3: UNAVAILABILITY ---
    elif st.session_state.stage == 3:
        st.title("❌ Step 3: Availability")
        df_members = fetch_sheet_data(st.session_state.ministry)
        names = sorted(df_members['name'].unique())
        date_options = [d['Date'].strftime("%Y-%m-%d") for d in st.session_state.roster_dates]
        
        with st.form("unav_form"):
            st.write("Tick the dates each person is **UNAVAILABLE**:")
            cols = st.columns(3)
            for i, name in enumerate(names):
                with cols[i%3]:
                    st.multiselect(name, options=date_options, key=f"unav_{name}")
            
            if st.form_submit_button("Generate Final Roster"):
                st.session_state.unavailability = {
                    d: [n for n in names if d in st.session_state.get(f"unav_{n}", [])] 
                    for d in date_options
                }
                st.session_state.stage = 4
                st.rerun()

    # --- STAGE 4: FINAL ROSTER ---
    elif st.session_state.stage == 4:
        st.title("📋 Step 4: Final Roster")
        df_members = fetch_sheet_data(st.session_state.ministry)
        
        if 'final_df' not in st.session_state:
            if st.session_state.ministry == "Welcome Ministry":
                engine = WelcomeEngine(df_members)
                st.session_state.final_df = engine.generate_roster(
                    st.session_state.roster_dates, 
                    st.session_state.unavailability
                )
            else:
                st.warning("Media Tech engine integration using same pipeline pattern...")
                # You can swap in your original Media Tech Engine here
        
        st.data_editor(st.session_state.final_df, use_container_width=True)
        
        if st.button("Start Over"):
            for key in list(st.session_state.keys()): del st.session_state[key]
            st.rerun()

if __name__ == "__main__":
    main()
