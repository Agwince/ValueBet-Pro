import streamlit as st
from datetime import datetime, timedelta, timezone
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
import json
import requests  

st.set_page_config(page_title="ValueBet Algorithm Pro", layout="wide", page_icon="🤖")

# ==========================================
# 1. CONNECT TO GOOGLE SHEETS
# ==========================================
@st.cache_resource
def init_connection():
    scopes = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
    creds_dict = json.loads(st.secrets["google_sheets_creds"])
    creds = Credentials.from_service_account_info(creds_dict, scopes=scopes)
    client = gspread.authorize(creds)
    return client.open("ValueBet Database")

sheet = init_connection()
users_sheet = sheet.worksheet("Users")
pending_sheet = sheet.worksheet("Pending")

# Fail-safe check for the Results tab
try:
    results_sheet = sheet.worksheet("Results")
except:
    results_sheet = None

if 'current_user' not in st.session_state:
    st.session_state.current_user = None

# ==========================================
# 2. HELPER FUNCTIONS & BOT LOGIC
# ==========================================
def get_all_users():
    return users_sheet.get_all_records()

def get_all_pending():
    return pending_sheet.get_all_records()

def get_all_results():
    if results_sheet:
        return results_sheet.get_all_records()
    return []

def check_expiry(user_record):
    expiry_date = datetime.strptime(user_record['expiry'], "%Y-%m-%d").date()
    today = datetime.now().date()
    return today <= expiry_date

def get_live_odds(sport_key, api_key):
    url = f'https://api.the-odds-api.com/v4/sports/{sport_key}/odds'
    params = {'api_key': api_key, 'regions': 'eu,uk', 'markets': 'h2h,totals', 'oddsFormat': 'decimal'}
    response = requests.get(url, params=params)
    if response.status_code == 200:
        return response.json()
    return None

def calculate_true_odds(pinnacle_odds):
    implied_probs = {outcome: (1 / odds) for outcome, odds in pinnacle_odds.items()}
    total_margin = sum(implied_probs.values())
    true_odds = {}
    for outcome, implied in implied_probs.items():
        true_prob = implied / total_margin
        true_odds[outcome] = round(1 / true_prob, 2)
    return true_odds

def check_safe_accumulators(bookies, market_key, point, true_odds, match, safe_bets_found):
    for bookie in bookies:
        if bookie['key'] == 'pinnacle': continue
        soft_market = next((m for m in bookie.get('markets', []) if m['key'] == market_key), None)
        if not soft_market: continue
        for outcome in soft_market['outcomes']:
            if point and outcome.get('point') != point: continue
            bet_type = outcome['name']
            soft_price = outcome['price']
            fair_price = true_odds.get(bet_type)
            if not fair_price: continue
            # The Legit Filter (1.10 to 1.85 odds)
            if fair_price >= 1.10 and fair_price <= 1.85:
                market_display = f"{bet_type} {point}" if point else f"To Win: {bet_type}"
                safe_bets_found.append({
                    "Match": f"{match['home_team']} vs {match['away_team']}",
                    "Market": market_display,
                    "Bookie Found": bookie['title'].upper(),
                    "Bookie Odds": soft_price,
                    "Win Prob": f"{round((1/fair_price)*100, 1)}%" 
                })

# ==========================================
# 3. PAGES
# ==========================================
def results_page():
    st.header("📊 Verified Profit History")
    st.markdown("Transparency is our priority. We log every win and loss to keep the system legit.")
    data = get_all_results()
    if not data:
        st.info("Verified results are being compiled. Log your first wins in the Admin panel!")
    else:
        df = pd.DataFrame(data)
        total = len(df)
        wins = len(df[df['Outcome (Win/Loss)'].str.lower() == 'win'])
        rate = round((wins / total) * 100, 1) if total > 0 else 0
        c1, c2, c3 = st.columns(3)
        c1.metric("Total Bets", total)
        c2.metric("Wins", wins)
        c3.metric("Verified Win Rate", f"{rate}%")
        st.divider()
        st.dataframe(df, use_container_width=True, hide_index=True)

def home_and_register():
    st.title("🤖 ValueBet Algorithm Pro")
    tab_login, tab_verify = st.tabs(["🔓 Login & Join", "📊 Verified Results"])
    with tab_login:
        st.success("🔥 Join 978+ Smart Bettors using mathematical edge. No more guessing.")
        st.divider()
        col1, col2 = st.columns(2)
        with col1:
            st.header("Login")
            login_user = st.text_input("Username", key="log_user")
            login_pass = st.text_input("Password", type="password", key="log_pass")
            if st.button("Log In"):
                users = get_all_users()
                for u in users:
                    if str(u['username']) == login_user and str(u['password']) == login_pass:
                        if u['status'] == 'active' and check_expiry(u):
                            st.session_state.current_user = login_user
                            st.rerun()
                st.error("Invalid credentials or expired account.")
        with col2:
            st.header("Get Premium Access")
            st.markdown("Send M-Pesa Pochi La Biashara to **0758275510**.")
            st.info("💰 Weekly: 500 KES | Monthly: 1,500 KES")
            reg_user = st.text_input("Choose Username")
            mpesa_code = st.text_input("M-Pesa Code", max_chars=10)
            if st.button("Submit Payment", type="primary"):
                pending_sheet.append_row([reg_user, "password", "Monthly", mpesa_code.upper(), str(datetime.now().date())])
                st.success("✅ Submitted! Wait 10 mins for activation.")
    with tab_verify:
        results_page()

def admin_dashboard():
    st.title("🛡️ Admin Panel")
    if st.button("Logout"):
        st.session_state.current_user = None
        st.rerun()
    st.subheader("Log A Win/Loss (Publicly)")
    with st.form("result_form"):
        res_date = st.date_input("Match Date")
        res_match = st.text_input("Match & Market")
        res_odds = st.number_input("Odds", min_value=1.01, step=0.01)
        res_outcome = st.selectbox("Outcome", ["Win", "Loss"])
        res_pl = st.number_input("Profit/Loss (Units)", step=0.1)
        if st.form_submit_button("Verified Result Log"):
            if results_sheet:
                results_sheet.append_row([str(res_date), res_match, res_odds, res_outcome, res_pl])
                st.success("Result added to public verified list!")
            else:
                st.error("Missing 'Results' tab in Google Sheets.")
    st.divider()
    st.subheader("Pending M-Pesa Payments")
    pending_data = get_all_pending()
    if not pending_data: st.info("No pending payments.")
    else:
        for idx, p in enumerate(pending_data):
            st.write(f"**{p['username']}** | Code: {p['mpesa_code']} | Plan: {p['plan']}")
            if st.button(f"Approve {p['username']}", key=f"app_{idx}"):
                expiry = (datetime.now() + timedelta(days=30)).date()
                users_sheet.append_row([p['username'], "password", "user", str(expiry), "active"])
                pending_sheet.delete_rows(idx + 2)
                st.rerun()

def premium_bot_dashboard():
    st.title("📈 Pro Dashboard: Smart Slips")
    if st.button("Logout", use_container_width=True):
        st.session_state.current_user = None
        st.rerun()
    st.divider()
    st.markdown("### 🚨 Global Market Scanner (Prioritizing Women's & U21 Leagues)")
    if st.button("🔍 Generate Today's Secure Slips", type="primary", use_container_width=True):
        with st.spinner("Hunting for high-consistency matches (Women's, U21, & Top Tiers)..."):
            API_KEY = '789faf8bb53e104396c0f8f6b6fba1aa' 
            sports_url = f'https://api.the-odds-api.com/v4/sports?api_key={API_KEY}'
            sports_response = requests.get(sports_url)
            
            if sports_response.status_code == 200:
                all_sports = sports_response.json()
                
                # Filter for active soccer leagues
                active_soccer = [s['key'] for s in all_sports if 'soccer' in s['key'] and s.get('active')]
                
                # --- THE NEW PRIORITY SYSTEM ---
                priority_keywords = ['women', 'wsl', 'u21', 'youth', 'u23', 'u20']
                priority_leagues = [s for s in active_soccer if any(kw in s.lower() for kw in priority_keywords)]
                regular_leagues = [s for s in active_soccer if s not in priority_leagues]
                
                # Combine them, putting priority leagues at the very top, and limit to 12 to save API limits
                SPORTS = (priority_leagues + regular_leagues)[:12]
            else:
                st.error("API Error.")
                return
                
            safe_bets_found = []
            for sport in SPORTS:
                matches = get_live_odds(sport, API_KEY)
                if not matches: continue
                for match in matches:
                    EAT_TZ = timezone(timedelta(hours=3))
                    match_time = datetime.fromisoformat(match['commence_time'].replace('Z', '+00:00'))
                    if match_time.astimezone(EAT_TZ).date() == datetime.now(EAT_TZ).date():
                        bookies = match.get('bookmakers', [])
                        pinnacle_data = next((b for b in bookies if b['key'] == 'pinnacle'), None)
                        if pinnacle_data and pinnacle_data.get('markets'):
                            for market in pinnacle_data['markets']:
                                if market['key'] in ['totals', 'h2h']:
                                    true_odds = calculate_true_odds({i['name']: i['price'] for i in market['outcomes']})
                                    check_safe_accumulators(bookies, market['key'], market['outcomes'][0].get('point'), true_odds, match, safe_bets_found)
                                    
            if safe_bets_found:
                df = pd.DataFrame(safe_bets_found).drop_duplicates(subset=['Match', 'Market'])
                df['Odds Value'] = pd.to_numeric(df['Bookie Odds'])
                df = df.sort_values(by='Odds Value').reset_index(drop=True)
                
                st.subheader("🟢 2 Odds Slip (Surest Double)")
                double_found = False
                for i in range(len(df)):
                    for j in range(i + 1, len(df)):
                        if df.iloc[i]['Match'] != df.iloc[j]['Match']:
                            combined = df.iloc[i]['Odds Value'] * df.iloc[j]['Odds Value']
                            if 1.75 <= combined <= 2.50:
                                st.dataframe(pd.DataFrame([df.iloc[i], df.iloc[j]]).drop(columns=['Odds Value']), use_container_width=True, hide_index=True)
                                st.info(f"**Total Combined Odds:** {round(combined, 2)}")
                                double_found = True
                                break
                    if double_found: break
                    
                # Standard Accumulator Builder
                def build_slip(target_odds, available_df):
                    slip_matches, current_slip_odds, used_matches = [], 1.0, set()
                    for _, row in available_df.iterrows():
                        if current_slip_odds < target_odds:
                            if row['Match'] not in used_matches:
                                slip_matches.append(row)
                                used_matches.add(row['Match'])
                                current_slip_odds *= row['Odds Value']
                    return pd.DataFrame(slip_matches), round(current_slip_odds, 2)

                st.subheader("🟡 5 Odds Slip (Value Multibet)")
                slip_5, odds_5 = build_slip(5.0, df)
                if not slip_5.empty and odds_5 >= 3.0:
                    st.dataframe(slip_5.drop(columns=['Odds Value']), use_container_width=True, hide_index=True)
                    st.info(f"**Total Combined Odds:** {odds_5}")

                st.subheader("🔴 10 Odds Slip (Mega Acca)")
                slip_10, odds_10 = build_slip(10.0, df)
                if not slip_10.empty and odds_10 >= 6.0:
                    st.dataframe(slip_10.drop(columns=['Odds Value']), use_container_width=True, hide_index=True)
                    st.info(f"**Total Combined Odds:** {odds_10}")
            else:
                st.warning("No secure matches today. Math says: Stay safe and skip today!")

if st.session_state.current_user is None: home_and_register()
else:
    users = get_all_users()
    role = next((u['role'] for u in users if str(u['username']) == st.session_state.current_user), "user")
    if role == 'admin': admin_dashboard()
    else: premium_bot_dashboard()
