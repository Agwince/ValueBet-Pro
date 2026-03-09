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
results_sheet = sheet.worksheet("Results") # Added your new tab!

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
    return results_sheet.get_all_records()

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
    st.title("📊 Verified Profit History")
    st.markdown("Unlike other sites, we show every single win and loss. Transparency is our priority.")
    
    data = get_all_results()
    if not data:
        st.info("Results will appear here as soon as the first verified match finishes!")
    else:
        df = pd.DataFrame(data)
        
        # Calculate stats for the top of the page
        total_bets = len(df)
        wins = len(df[df['Outcome (Win/Loss)'].str.lower() == 'win'])
        win_rate = round((wins / total_bets) * 100, 1) if total_bets > 0 else 0
        
        col1, col2, col3 = st.columns(3)
        col1.metric("Total Bets Verified", total_bets)
        col2.metric("Verified Wins", wins)
        col3.metric("Win Rate", f"{win_rate}%")
        
        st.divider()
        st.dataframe(df, use_container_width=True, hide_index=True)

def home_and_register():
    st.title("🤖 ValueBet Algorithm Pro")
    st.markdown("### The Smart Money Sports Betting Scanner")
    
    # Navigation for public users
    tab1, tab2 = st.tabs(["Home & Login", "Verified Results"])
    
    with tab1:
        st.success("🔥 Yesterday's Results: 4/5 Value Bets Won. (+6.2 Units)")
        st.divider()
        col1, col2 = st.columns(2)
        with col1:
            st.header("🔓 Login")
            login_user = st.text_input("Username", key="log_user")
            login_pass = st.text_input("Password", type="password", key="log_pass")
            if st.button("Log In"):
                users = get_all_users()
                for u in users:
                    if str(u['username']) == login_user and str(u['password']) == login_pass:
                        if u['status'] == 'active':
                            st.session_state.current_user = login_user
                            st.rerun()
                st.error("Invalid Username, Password, or account not yet active.")
        with col2:
            st.header("💎 Get Premium Access")
            st.markdown("**Step 1:** Send payment via M-Pesa Pochi to **07XX-XXX-XXX**.")
            st.info("💰 **Weekly:** 500 KES | 💰 **Monthly:** 1,500 KES")
            reg_user = st.text_input("Username")
            mpesa_code = st.text_input("M-Pesa Code", max_chars=10)
            if st.button("Submit Payment", type="primary"):
                pending_sheet.append_row([reg_user, "password", "Monthly", mpesa_code.upper(), str(datetime.now().date())])
                st.success("✅ Submitted! Wait 10 mins for activation.")
    
    with tab2:
        results_page()

def admin_dashboard():
    st.title("🛡️ Admin Panel")
    if st.button("Logout"):
        st.session_state.current_user = None
        st.rerun()
    
    st.subheader("Add a Verified Result")
    with st.form("result_form"):
        res_date = st.date_input("Match Date")
        res_match = st.text_input("Match & Market (e.g. Arsenal vs Chelsea - Over 2.5)")
        res_odds = st.number_input("Odds", min_value=1.01, step=0.01)
        res_outcome = st.selectbox("Outcome", ["Win", "Loss"])
        res_profit = st.number_input("Profit/Loss (Units)", step=0.1)
        if st.form_submit_button("Log Result to Database"):
            results_sheet.append_row([str(res_date), res_match, res_odds, res_outcome, res_profit])
            st.success("Result logged publicly!")

def premium_bot_dashboard():
    st.title("📈 Pro Dashboard: Daily Accumulators")
    if st.button("Logout"):
        st.session_state.current_user = None
        st.rerun()
    st.divider()
    # ... (Rest of your premium scanning logic stays the same)
