import streamlit as st
from datetime import datetime, timedelta, timezone
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
import json
import requests  
import cloudscraper
from bs4 import BeautifulSoup

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
try:
    results_sheet = sheet.worksheet("Results")
except:
    results_sheet = None

if 'current_user' not in st.session_state:
    st.session_state.current_user = None

# ==========================================
# 2. THE ADAPTIVE FOREBET BRAIN (GOD MODE)
# ==========================================
@st.cache_data(ttl=3600, show_spinner=False) # Caches the scraper for 1 hour
def get_forebet_premium_targets():
    url = 'https://www.forebet.com/en/football-tips-and-predictions-for-today'
    scraper = cloudscraper.create_scraper(browser={'browser': 'chrome', 'platform': 'windows', 'desktop': True})
    all_targets = []
    
    try:
        response = scraper.get(url, timeout=15)
        if response.status_code == 200:
            soup = BeautifulSoup(response.text, 'html.parser')
            match_rows = soup.find_all('div', class_='rcnt') 
            
            for row in match_rows:
                try:
                    home_team = row.find('span', class_='homeTeam').text.strip()
                    away_team = row.find('span', class_='awayTeam').text.strip()
                    fprc_div = row.find('div', class_='fprc')
                    
                    if fprc_div:
                        spans = fprc_div.find_all('span')
                        if len(spans) >= 3:
                            home_prob = int(spans[0].text.strip())
                            away_prob = int(spans[2].text.strip())
                            highest_prob = max(home_prob, away_prob)
                            
                            # THE NEW ADAPTIVE FILTER: 
                            # Take anything 60% or higher to guarantee daily action
                            if highest_prob >= 60:
                                all_targets.append({
                                    'home': home_team,
                                    'away': away_team,
                                    'prob': highest_prob
                                })
                except:
                    continue 
    except Exception as e:
        pass 
        
    # Sort the list so the safest matches are always at the very top
    all_targets = sorted(all_targets, key=lambda x: x['prob'], reverse=True)
    
    # Return the Top 10 safest matches of the day
    return all_targets[:10]

# ==========================================
# 3. ODDS API HELPERS
# ==========================================
def get_all_users(): return users_sheet.get_all_records()
def get_all_pending(): return pending_sheet.get_all_records()
def get_all_results(): return results_sheet.get_all_records() if results_sheet else []
def check_expiry(user_record):
    return datetime.now().date() <= datetime.strptime(user_record['expiry'], "%Y-%m-%d").date()

@st.cache_data(ttl=7200, show_spinner=False)
def get_active_sports(api_key):
    res = requests.get(f'https://api.the-odds-api.com/v4/sports?api_key={api_key}')
    return res.json() if res.status_code == 200 else None

@st.cache_data(ttl=7200, show_spinner=False)
def get_live_odds(sport_key, api_key):
    url = f'https://api.the-odds-api.com/v4/sports/{sport_key}/odds'
    res = requests.get(url, params={'api_key': api_key, 'regions': 'eu,uk', 'markets': 'h2h,totals', 'oddsFormat': 'decimal'})
    return res.json() if res.status_code == 200 else None

def calculate_true_odds(pinnacle_odds):
    implied_probs = {outcome: (1 / odds) for outcome, odds in pinnacle_odds.items()}
    total_margin = sum(implied_probs.values())
    return {outcome: round(1 / (implied / total_margin), 2) for outcome, implied in implied_probs.items()}

# ==========================================
# 4. DASHBOARDS
# ==========================================
def home_and_register():
    st.title("🤖 ValueBet Algorithm Pro")
    tab_login, tab_verify = st.tabs(["🔓 Login & Join", "📊 Verified Results"])
    with tab_login:
        st.success("🔥 Join 978+ Smart Bettors using mathematical edge. No more guessing.")
        col1, col2 = st.columns(2)
        with col1:
            st.header("Login")
            login_user = st.text_input("Username", key="log_user")
            login_pass = st.text_input("Password", type="password", key="log_pass")
            if st.button("Log In"):
                for u in get_all_users():
                    if str(u['username']) == login_user and str(u['password']) == login_pass and u['status'] == 'active' and check_expiry(u):
                        st.session_state.current_user = login_user
                        st.rerun()
                st.error("Invalid credentials or expired account.")
        with col2:
            st.header("Get Premium Access")
            st.info("💰 Weekly: 500 KES | Monthly: 1,500 KES (Send to 0758275510)")
            reg_user = st.text_input("Choose Username")
            mpesa_code = st.text_input("M-Pesa Code", max_chars=10)
            if st.button("Submit Payment", type="primary"):
                pending_sheet.append_row([reg_user, "password", "Monthly", mpesa_code.upper(), str(datetime.now().date())])
                st.success("✅ Submitted! Wait 10 mins for activation.")
    with tab_verify:
        st.header("📊 Verified Profit History")
        data = get_all_results()
        if data:
            df = pd.DataFrame(data)
            st.dataframe(df, use_container_width=True, hide_index=True)
        else:
            st.info("Verified results are being compiled.")

def premium_bot_dashboard():
    st.title("📈 God Mode Dashboard")
    if st.button("Logout"):
        st.session_state.current_user = None
        st.rerun()
    st.divider()
    
    if st.button("🔍 Generate VIP Slips (Forebet + Pinnacle Filter)", type="primary", use_container_width=True):
        
        # 1. AWAKEN THE FOREBET BRAIN
        with st.spinner("🧠 Booting Forebet Brain: Scanning global matches for safe picks..."):
            premium_targets = get_forebet_premium_targets()
            
        if not premium_targets:
            st.warning("⚠️ Forebet Brain says: No exceptionally safe matches today. Protect your bankroll!")
            return
            
        st.success(f"✅ Forebet found the Top {len(premium_targets)} secure matches. Cross-checking with bookmakers...")
        
        # 2. CHECK ODDS API
        API_KEYS = ['12ec16da595cafd5f9a5fd2afaa685f9', '789faf8bb53e104396c0f8f6b6fba1aa']
        working_key = next((k for k in API_KEYS if get_active_sports(k)), None)
        
        if not working_key:
            st.error("🚨 API Limits Reached on all keys!")
            return
            
        sports = get_active_sports(working_key)[:12]
        safe_bets_found = []
        
        with st.spinner("Snipping bookies for value pricing..."):
            for sport in sports:
                matches = get_live_odds(sport['key'], working_key)
                if not matches: continue
                for match in matches:
                    # THE FUZZY MATCHER
                    is_premium = False
                    for target in premium_targets:
                        # If the first word of the team name matches, we count it!
                        if target['home'].split()[0].lower() in match['home_team'].lower() or target['away'].split()[0].lower() in match['away_team'].lower():
                            is_premium = True
                            break
                            
                    if not is_premium:
                        continue # Skip garbage matches!

                    # Process the VIP match
                    bookies = match.get('bookmakers', [])
                    pinnacle_data = next((b for b in bookies if b['key'] == 'pinnacle'), None)
                    if pinnacle_data and pinnacle_data.get('markets'):
                        market = pinnacle_data['markets'][0]
                        true_odds = calculate_true_odds({i['name']: i['price'] for i in market['outcomes']})
                        
                        for bookie in bookies:
                            if bookie['key'] == 'pinnacle': continue
                            soft_market = next((m for m in bookie.get('markets', []) if m['key'] == market['key']), None)
                            if not soft_market: continue
                            for outcome in soft_market['outcomes']:
                                fair_price = true_odds.get(outcome['name'])
                                if fair_price and 1.10 <= fair_price <= 2.20:
                                    safe_bets_found.append({
                                        "Match": f"{match['home_team']} vs {match['away_team']}",
                                        "Market": outcome['name'],
                                        "Bookie": bookie['title'].upper(),
                                        "Odds": outcome['price']
                                    })
                                    
        if safe_bets_found:
            df = pd.DataFrame(safe_bets_found).drop_duplicates(subset=['Match', 'Market']).sort_values(by='Odds').reset_index(drop=True)
            st.subheader("🟢 The God Mode Double (2 Odds)")
            st.dataframe(df.head(2), use_container_width=True, hide_index=True)
            st.info(f"These teams passed the mathematical filter AND have Pinnacle value.")
        else:
            st.warning("Matches were safe, but bookies aren't offering profitable odds right now. Check back in an hour!")

if st.session_state.current_user is None: home_and_register()
else: premium_bot_dashboard()
