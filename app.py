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

if 'current_user' not in st.session_state:
    st.session_state.current_user = None

# ==========================================
# 2. HELPER FUNCTIONS & BOT LOGIC
# ==========================================
def get_all_users():
    return users_sheet.get_all_records()

def get_all_pending():
    return pending_sheet.get_all_records()

def check_expiry(user_record):
    expiry_date = datetime.strptime(user_record['expiry'], "%Y-%m-%d").date()
    today = datetime.now().date()
    return today <= expiry_date

# API Functions
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
            
            # Grabbing high probability safe bets (1.10 to 1.85)
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
def home_and_register():
    st.title("🤖 ValueBet Algorithm Pro")
    st.markdown("### The Smart Money Sports Betting Scanner")
    st.success("🔥 Yesterday's Results: 4/5 Value Bets Won. (+6.2 Units)")
    st.divider()
    
    col1, col2 = st.columns(2)
    with col1:
        st.header("🔓 Login")
        login_user = st.text_input("Username", key="log_user")
        login_pass = st.text_input("Password", type="password", key="log_pass")
        
        if st.button("Log In"):
            users = get_all_users()
            user_found = False
            for u in users:
                if str(u['username']) == login_user and str(u['password']) == login_pass:
                    user_found = True
                    if u['status'] == 'active':
                        if check_expiry(u):
                            st.session_state.current_user = login_user
                            st.rerun()
                        else:
                            st.error("❌ Your subscription has expired. Please renew below.")
                    else:
                        st.warning("⏳ Your account is pending admin approval.")
                    break
            if not user_found:
                st.error("Invalid Username or Password.")

    with col2:
        st.header("💎 Get Premium Access")
        st.markdown("**Step 1:** Send payment via M-Pesa Pochi La Biashara to **07XX-XXX-XXX**.")
        st.info("💰 **Weekly Plan:** 500 KES\n\n💰 **Monthly Plan:** 1,500 KES")
        st.markdown("**Step 2:** Fill out the form below with your M-Pesa Code.")
        
        reg_user = st.text_input("Choose a Username")
        reg_pass = st.text_input("Choose a Password", type="password")
        plan = st.selectbox("Select Your Plan", ["Weekly (500 KES)", "Monthly (1,500 KES)"])
        mpesa_code = st.text_input("M-Pesa Transaction Code (e.g., QAW5...)", max_chars=10)
        
        if st.button("Submit Payment", type="primary"):
            if len(mpesa_code) < 8:
                st.error("Please enter a valid M-Pesa code.")
            else:
                pending_sheet.append_row([reg_user, reg_pass, plan, mpesa_code.upper(), str(datetime.now().date())])
                st.success("✅ Details submitted! Please wait up to 10 minutes for activation.")

def admin_dashboard():
    st.title("🛡️ Admin Panel")
    st.write(f"Logged in as: **{st.session_state.current_user}**")
    
    if st.button("Logout"):
        st.session_state.current_user = None
        st.rerun()
        
    st.subheader("Pending M-Pesa Payments")
    pending_data = get_all_pending()
    
    if not pending_data:
        st.info("No pending payments right now.")
    else:
        for idx, payment in enumerate(pending_data):
            st.write(f"**User:** {payment['username']} | **Code:** {payment['mpesa_code']} | **Plan:** {payment['plan']}")
            
            col1, col2 = st.columns([1, 4])
            with col1:
                if st.button(f"Approve {payment['username']}", key=f"app_{idx}"):
                    days_to_add = 7 if "Weekly" in payment['plan'] else 30
                    expiry_date = (datetime.now() + timedelta(days=days_to_add)).date()
                    users_sheet.append_row([payment['username'], payment['password'], "user", str(expiry_date), "active"])
                    pending_sheet.delete_rows(idx + 2) 
                    st.success(f"User activated until {expiry_date}!")
                    st.rerun()

def premium_bot_dashboard():
    st.title("📈 Pro Dashboard: Daily Accumulators")
    st.success(f"Welcome back, {st.session_state.current_user}!")
    
    col1, col2 = st.columns([3, 1])
    with col2:
        if st.button("Logout", use_container_width=True):
            st.session_state.current_user = None
            st.rerun()
            
    st.divider()
    st.markdown("### 🚨 Smart Accumulator Builder")
    st.write("Click below to dynamically scan active global leagues for today's safest, highest-probability matches.")
    
    if st.button("🔍 Generate Today's Secure Slips", type="primary", use_container_width=True):
        with st.spinner("Dynamically scanning the globe for active matches today..."):
            API_KEY = '789faf8bb53e104396c0f8f6b6fba1aa' 
            
            # DYNAMIC LEAGUE FETCHER: Asks the API what is playing today
            sports_url = f'https://api.the-odds-api.com/v4/sports?api_key={API_KEY}'
            sports_response = requests.get(sports_url)
            
            SPORTS = []
            if sports_response.status_code == 200:
                all_sports = sports_response.json()
                # Grabs up to 15 active soccer leagues to protect your API limits
                SPORTS = [s['key'] for s in all_sports if 'soccer' in s['key'] and s.get('active')][:15]
            
            if not SPORTS:
                st.error("Could not connect to the global sports database to find active leagues.")
                return
            
            safe_bets_found = []
            
            for sport in SPORTS:
                matches = get_live_odds(sport, API_KEY)
                if not matches: continue
                    
                for match in matches:
                    # STRICT TODAY FILTER (Kenyan Time)
                    EAT_TZ = timezone(timedelta(hours=3))
                    match_time_utc = datetime.fromisoformat(match['commence_time'].replace('Z', '+00:00'))
                    if match_time_utc.astimezone(EAT_TZ).date() != datetime.now(EAT_TZ).date():
                        continue 

                    bookies = match.get('bookmakers', [])
                    pinnacle_data = next((b for b in bookies if b['key'] == 'pinnacle'), None)
                    if not pinnacle_data or not pinnacle_data.get('markets'): continue
                        
                    for market in pinnacle_data['markets']:
                        pinny_outcomes = market['outcomes']
                        
                        if market['key'] == 'totals':
                            points_available = set(item.get('point') for item in pinny_outcomes if 'point' in item)
                            for point in points_available:
                                pinny_line = {item['name']: item['price'] for item in pinny_outcomes if item.get('point') == point}
                                if len(pinny_line) < 2: continue
                                true_odds = calculate_true_odds(pinny_line)
                                check_safe_accumulators(bookies, market['key'], point, true_odds, match, safe_bets_found)
                                
                        elif market['key'] == 'h2h':
                            pinny_line = {item['name']: item['price'] for item in pinny_outcomes}
                            if len(pinny_line) < 2: continue
                            true_odds = calculate_true_odds(pinny_line)
                            check_safe_accumulators(bookies, market['key'], None, true_odds, match, safe_bets_found)
            
            if safe_bets_found:
                # Remove duplicates
                unique_bets = []
                seen = set()
                for bet in safe_bets_found:
                    identifier = f"{bet['Match']}_{bet['Market']}"
                    if identifier not in seen:
                        seen.add(identifier)
                        unique_bets.append(bet)
                
                df = pd.DataFrame(unique_bets)
                df['Odds Value'] = pd.to_numeric(df['Bookie Odds'])
                df = df.sort_values(by='Odds Value').reset_index(drop=True)
                
                st.success(f"✅ Scanning Complete! Found {len(df)} highly secure matches across the globe.")
                
                # --- NEW: EXACT 2-MATCH DOUBLE BUILDER ---
                def build_exact_double(available_df):
                    for i in range(len(available_df)):
                        for j in range(i + 1, len(available_df)):
                            m1 = available_df.iloc[i]
                            m2 = available_df.iloc[j]
                            # Make sure they are different matches
                            if m1['Match'] != m2['Match']:
                                combined = m1['Odds Value'] * m2['Odds Value']
                                # Looks for a combined odds between 1.70 and 2.50
                                if 1.70 <= combined <= 2.50:
                                    return pd.DataFrame([m1, m2]), round(combined, 2)
                    return pd.DataFrame(), 0.0

                # Standard Accumulator Builder
                def build_slip(target_odds, available_df):
                    slip_matches = []
                    current_slip_odds = 1.0
                    used_matches = set()
                    for _, row in available_df.iterrows():
                        if current_slip_odds < target_odds:
                            if row['Match'] not in used_matches:
                                slip_matches.append(row)
                                used_matches.add(row['Match'])
                                current_slip_odds *= row['Odds Value']
                    return pd.DataFrame(slip_matches), round(current_slip_odds, 2)

                # PACKAGE 1: 2 Odds Slip (Exact Double)
                st.subheader("🟢 2 Odds Slip (Safest Double)")
                st.write("This slip specifically combines exactly two high-probability matches to hit your daily target.")
                slip_2, odds_2 = build_exact_double(df)
                if not slip_2.empty:
                    st.dataframe(slip_2.drop(columns=['Odds Value']), use_container_width=True, hide_index=True)
                    st.info(f"**Total Combined Odds:** {odds_2}")
                else:
                    st.write("Could not find two perfectly matching games for a 2-odd double right now.")

                # PACKAGE 2: 5 Odds Slip
                st.subheader("🟡 5 Odds Slip (Value Multibet)")
                slip_5, odds_5 = build_slip(5.0, df)
                if not slip_5.empty and odds_5 >= 3.0:
                    st.dataframe(slip_5.drop(columns=['Odds Value']), use_container_width=True, hide_index=True)
                    st.info(f"**Total Combined Odds:** {odds_5}")
                else:
                    st.write("Not enough safe games to build a full 5-odd slip right now.")

                # PACKAGE 3: 10 Odds Slip
                st.subheader("🔴 10 Odds Slip (Mega Acca)")
                slip_10, odds_10 = build_slip(10.0, df)
                if not slip_10.empty and odds_10 >= 6.0:
                    st.dataframe(slip_10.drop(columns=['Odds Value']), use_container_width=True, hide_index=True)
                    st.info(f"**Total Combined Odds:** {odds_10}")
                else:
                    st.write("Not enough safe games to build a full 10-odd slip right now.")
                    
            else:
                st.warning("No highly secure matches found playing right now. Check back later today!")

# ==========================================
# 4. ROUTER LOGIC
# ==========================================
if st.session_state.current_user is None:
    home_and_register()
else:
    users = get_all_users()
    role = "user"
    for u in users:
        if str(u['username']) == st.session_state.current_user:
            role = u['role']
            break
            
    if role == 'admin':
        admin_dashboard()
    else:
        premium_bot_dashboard()
