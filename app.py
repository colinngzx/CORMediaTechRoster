import streamlit as st
import pandas as pd
import random
import calendar
from datetime import datetime, date
from collections import defaultdict

# ==========================================
# 1. INITIAL SETTINGS & DATA FETCH
# ==========================================
SHEET_ID = "1jh6ScfqpHe7rRN1s-9NYPsm7hwqWWLjdLKTYThRRGUo"
GIDS = {"Media Tech": "0", "Welcome Ministry": "2080125013"}

st.set_page_config(page_title="SWS Roster Wizard", layout="wide")

@st.cache_data(ttl=600)
def fetch_sheet_data(ministry):
    gid = GIDS.get(ministry, "0")
    url = f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/export?format=csv&gid={gid}"
    try:
        df = pd.read_csv(url).fillna("")
        df.columns = df.columns.str.strip().str.lower()
        return df
    except:
        return pd.DataFrame()

# ==========================================
# 2. ENGINES (LOGIC REMAINS SAME)
# ==========================================

class RosterEngine:
    def __init__(self, df, ministry):
        self.df = df
        self.ministry = ministry
        self.total_load = defaultdict(int)
        self.prev_week_crew = []

    def get_ui_name(self, name):
        if not name or self.ministry == "Media Tech": return name
        row = self.df[self.df['name'] == name].iloc[0]
        tags = []
        if str(row.get('male', '')).lower() == 'yes': tags.append("M")
        if str(row.get('senior citizen', '')).lower() == 'yes': tags.append("S")
        return f"{name} ({', '.join(tags)})" if tags else name

    def generate(self, dates_meta, unavailability):
        return self._generate_welcome(dates_meta, unavailability) if self.ministry == "Welcome Ministry" else self._generate_media(dates_meta, unavailability)

    def _generate_welcome(self, dates_meta, unavailability):
        roster_data = []
        leads_pool = self.df[self.df['team lead'].astype(str).str.lower() == 'yes']['name'].tolist()
        members_pool = self.df[self.df['member'].astype(str).str.lower() == 'yes']['name'].tolist()
        for meta in dates_meta:
            d_str = meta['Date']
            team_size = 5 if (meta.get('HC') or meta.get('Combined')) else 4
            unav = unavailability.get(d_str, [])
            crew = []
            row = {"Date": d_str, "Note": "HC" if meta.get('HC') else ("Combined" if meta.get('Combined') else "Regular")}
            avail_l = [l for l in leads_pool if l not in unav and l not in self.prev_week_crew]
            if not avail_l: avail_l = [l for l in leads_pool if l not in unav]
            if avail_l:
                avail_l.sort(key=lambda x: (self.total_load[x], random.uniform(0, 1)))
                leader = avail_l[0]; row["Team Lead"] = self.get_ui_name(leader); crew.append(leader); self.total_load[leader] += 1
            while len(crew) < team_size:
                needs_m = not any(self.df[self.df['name']==p]['male'].str.lower().item()=='yes' for p in crew if p in members_pool)
                needs_s = not any(self.df[self.df['name']==p]['senior citizen'].str.lower().item()=='yes' for p in crew if p in members_pool)
                pool = [n for n in members_pool if n not in crew and n not in unav and n not in self.prev_week_crew]
                if not pool: pool = [n for n in members_pool if n not in crew and n not in unav]
                if not pool: break
                pool.sort(key=lambda n: (self.total_load[n] - (10 if needs_m and str(self.df[self.df['name']==n]['male'].iloc[0]).lower()=='yes' else 0) - (10 if needs_s and str(self.df[self.df['name']==n]['senior citizen'].iloc[0]).lower()=='yes' else 0), random.uniform(0,1)))
                pick = pool[0]; c_id = str(self.df[self.df['name'] == pick]['couple'].iloc[0]).strip()
                partner = ""
                if c_id:
                    p_df = self.df[(self.df['couple'].astype(str)==c_id) & (self.df['name']!=pick)]
                    partner = p_df['name'].iloc[0] if not p_df.empty else ""
                if partner and len(crew) + 2 > team_size:
                    singles = [p for p in pool if not str(self.df[self.df['name']==p]['couple'].iloc[0]).strip()]
                    if not singles: break
                    pick = singles[0]; partner = ""
                row[f"Member {len(crew)}"] = self.get_ui_name(pick); crew.append(pick); self.total_load[pick] += 1
                if partner: row[f"Member {len(crew)}"] = self.get_ui_name(partner); crew.append(partner); self.total_load[partner] += 1
            self.prev_week_crew = crew; roster_data.append(row)
        return pd.DataFrame(roster_data)

    def _generate_media(self, dates_meta, unavailability):
        roster_data = []
        roles = [("Sound Crew", "sound"), ("Projectionist", "projection"), ("Stream Director", "stream director"), ("Cam 1", "camera")]
        for meta in dates_meta:
            d_str = meta['Date']
            unav = unavailability.get(d_str, [])
            crew = []
            row = {"Date": d_str, "Note": "Combined" if meta.get('Combined') else ""}
            for label, col in roles:
                pool = self.df[self.df[col].astype(str).str.strip() != ""]['name'].tolist()
                avail = [p for p in pool if p not in unav and p not in crew and p not in self.prev_week_crew]
                if not avail: avail = [p for p in pool if p not in unav and p not in crew]
                if avail:
                    avail.sort(key=lambda x: (self.total_load[x], random.uniform(0, 1)))
                    pick = avail[0]; row[label] = pick; crew.append(pick); self.total_load[pick] += 1
            row["Cam 2"] = ""; row["Team Lead"] = row.get("Stream Director", "")
            self.prev_week_crew = crew; roster_data.append(row)
        return pd.DataFrame(roster_data)

# ==========================================
# 3. UI JOURNEY
# ==========================================

def main():
    if 'stage' not in st.session_state: st.session_state.stage = 1
    
    # Navigation Buttons Logic
    cols_nav = st.columns([1, 8, 1])
    if st.session_state.stage > 1:
        if cols_nav[0].button("← Back"):
            st.session_state.stage -= 1
            if st.session_state.stage == 3: st.session_state.pop('final_df', None)
            st.rerun()

    # --- STAGE 1 ---
    if st.session_state.stage == 1:
        st.title("🛡️ Step 1: Ministry & Period")
        st.session_state.ministry = st.selectbox("Ministry", ["Media Tech", "Welcome Ministry"], index=0)
        col1, col2 = st.columns(2)
        year = col1.number_input("Year", value=2026)
        cur_m = date.today().month
        next_3 = [calendar.month_name[(cur_m + i - 1) % 12 + 1] for i in range(1, 4)]
        months = col2.multiselect("Months", list(calendar.month_name)[1:], default=next_3)
        if st.button("Next: Generate Dates"):
            m_map = {m: i for i, m in enumerate(calendar.month_name)}
            st.session_state.roster_dates = [{"Date": date(year, m_map[m], d).strftime("%Y-%m-%d"), "HC": False, "Combined": False} 
                                           for m in months for d in range(1, calendar.monthrange(year, m_map[m])[1]+1) 
                                           if date(year, m_map[m], d).weekday() == 6]
            st.session_state.stage = 2; st.rerun()

    # --- STAGE 2 ---
    elif st.session_state.stage == 2:
        st.title("⛪ Step 2: Service Types")
        st.info("You can add extra dates using the (+) below or delete Sundays using the (🗑️).")
        st.session_state.roster_dates = st.data_editor(st.session_state.roster_dates, num_rows="dynamic", use_container_width=True, key="date_edit")
        if st.button("Next: Availability"): st.session_state.stage = 3; st.rerun()

    # --- STAGE 3 ---
    elif st.session_state.stage == 3:
        st.title("❌ Step 3: Availability")
        df_members = fetch_sheet_data(st.session_state.ministry)
        names = sorted(df_members['name'].unique())
        date_opts = [d['Date'] for d in st.session_state.roster_dates]
        with st.form("unav_form"):
            cols = st.columns(3)
            for i, name in enumerate(names):
                with cols[i%3]: st.multiselect(name, options=date_opts, key=f"unav_{name}")
            if st.form_submit_button("Generate Final Roster"):
                st.session_state.unavailability = {d: [n for n in names if d in st.session_state.get(f"unav_{n}", [])] for d in date_opts}
                st.session_state.stage = 4; st.rerun()

    # --- STAGE 4 ---
    elif st.session_state.stage == 4:
        st.title("📋 Step 4: Final Roster")
        df_members = fetch_sheet_data(st.session_state.ministry)
        if 'final_df' not in st.session_state:
            engine = RosterEngine(df_members, st.session_state.ministry)
            st.session_state.final_df = engine.generate(st.session_state.roster_dates, st.session_state.unavailability)
        
        # TRANSPOSE FOR EXCEL VIEW
        view_df = st.session_state.final_df.set_index("Date").T
        edited_view = st.data_editor(view_df, use_container_width=True)
        st.session_state.final_df = edited_view.T.reset_index()

        # LIVE STATS
        with st.expander("📊 Live Load Statistics"):
            stats = defaultdict(int)
            for col in st.session_state.final_df.columns:
                if col not in ["Date", "Note"]:
                    for val in st.session_state.final_df[col]:
                        if val: stats[val.split(" (")[0]] += 1
            st.dataframe(pd.DataFrame([{"Name": k, "Shifts": v} for k,v in stats.items()]).sort_values("Shifts", ascending=False))

        if st.button("Start Over"):
            for k in list(st.session_state.keys()): del st.session_state[k]
            st.rerun()

if __name__ == "__main__":
    main()
