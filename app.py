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
    # Checking both Match Winner (h2h) and Totals
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

def check_soft_bookies(bookies, market_key, point, true_odds, match, value_bets_found):
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
            
            if fair_price <= 15.00 and soft_price > fair_price:
                edge = round(((soft_price / fair_price) - 1) * 100, 2)
                if edge >= 2.0:
                    market_display = f"{bet_type} {point}" if point else f"To Win: {bet_type}"
                    value_bets_found.append({
                        "Match": f"{match['home_team']} vs {match['away_team']}",
                        "Market": market_display,
                        "True Fair Odds": fair_price,
                        "Bookie Found": bookie['title'].upper(),
                        "Bookie Odds": soft_price,
                        "Your Edge": f"{edge}%"
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
    st.title("📈 Pro Dashboard: Live Value Bets")
    st.success(f"Welcome back, {st.session_state.current_user}!")
    
    col1, col2 = st.columns([3, 1])
    with col2:
        if st.button("Logout", use_container_width=True):
            st.session_state.current_user = None
            st.rerun()
            
    st.divider()
    st.markdown("### 🚨 Global Market Scanner")
    st.write("Click below to scan 15 global leagues for mathematically profitable single bets happening **Today**. Sorted into your daily packages.")
    
    if st.button("🔍 Scan Global Markets (Live API)", type="primary", use_container_width=True):
        with st.spinner("Scanning Global Leagues for Today's Matches..."):
            API_KEY = '789faf8bb53e104396c0f8f6b6fba1aa' 
            SPORTS = [
                'soccer_epl', 'soccer_spain_la_liga', 'soccer_italy_serie_a', 'soccer_germany_bundesliga', 'soccer_france_ligue_one',
                'soccer_uefa_champs_league', 'soccer_uefa_europa_league', 'soccer_netherlands_eredivisie', 'soccer_portugal_primeira_liga',
                'soccer_turkey_super_league', 'soccer_brazil_campeonato', 'soccer_usa_mls', 'soccer_mexico_ligamx', 
                'soccer_japan_j_league', 'soccer_australia_aleague'
            ]
            
            value_bets_found = []
            
            for sport in SPORTS:
                matches = get_live_odds(sport, API_KEY)
                if not matches: continue
                    
                for match in matches:
                    # TIME FILTER: Only show games playing TODAY in Kenyan Time
                    EAT_TZ = timezone(timedelta(hours=3))
                    match_time_utc = datetime.fromisoformat(match['commence_time'].replace('Z', '+00:00'))
                    match_time_local = match_time_utc.astimezone(EAT_TZ)
                    today = datetime.now(EAT_TZ).date()
                    
                    if match_time_local.date() != today:
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
                                check_soft_bookies(bookies, market['key'], point, true_odds, match, value_bets_found)
                                
                        elif market['key'] == 'h2h':
                            pinny_line = {item['name']: item['price'] for item in pinny_outcomes}
                            if len(pinny_line) < 2: continue
                            true_odds = calculate_true_odds(pinny_line)
                            check_soft_bookies(bookies, market['key'], None, true_odds, match, value_bets_found)
            
            if value_bets_found:
                st.success(f"✅ Scanning Complete! Found {len(value_bets_found)} high-value single bets for today.")
                
                # Filter duplicates
                unique_bets = []
                seen = set()
                for bet in value_bets_found:
                    identifier = f"{bet['Match']}_{bet['Market']}_{bet['Bookie Found']}"
                    if identifier not in seen:
                        seen.add(identifier)
                        unique_bets.append(bet)
                
                df = pd.DataFrame(unique_bets)
                df['Odds Value'] = pd.to_numeric(df['Bookie Odds'])
                
                # PACKAGE 1: 2 Odds (Most Sure)
                st.subheader("🟢 2 Odds Package (Most Sure)")
                df_2 = df[(df['Odds Value'] >= 1.5) & (df['Odds Value'] <= 2.99)]
                if not df_2.empty:
                    st.dataframe(df_2.drop(columns=['Odds Value']), use_container_width=True, hide_index=True)
                else:
                    st.write("No safe 2-odd values found right now.")

                # PACKAGE 2: 5 Odds (Value)
                st.subheader("🟡 5 Odds Package (Value)")
                df_5 = df[(df['Odds Value'] >= 4.0) & (df['Odds Value'] <= 6.99)]
                if not df_5.empty:
                    st.dataframe(df_5.drop(columns=['Odds Value']), use_container_width=True, hide_index=True)
                else:
                    st.write("No 5-odd values found right now.")

                # PACKAGE 3: 10 Odds (Longshot)
                st.subheader("🔴 10 Odds Package (Longshot)")
                df_10 = df[(df['Odds Value'] >= 8.0)]
                if not df_10.empty:
                    st.dataframe(df_10.drop(columns=['Odds Value']), use_container_width=True, hide_index=True)
                else:
                    st.write("No massive 10-odd longshots found right now.")
                    
            else:
                st.warning("No value bets found right now. The global markets are tight. Check back in a few hours!")

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
