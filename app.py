import streamlit as st
from datetime import datetime, timedelta, timezone
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
import json
import requests  
from curl_cffi import requests as curl_requests 
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
# 2. ENGINE 1: BULLETPROOF FOREBET BRAIN
# ==========================================
def get_forebet_premium_targets():
    url = 'https://www.forebet.com/en/football-tips-and-predictions-for-today'
    all_targets = []
    
    headers = {
        'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36'
    }
    
    try:
        response = curl_requests.get(url, headers=headers, impersonate="chrome110", timeout=20)
        
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
                            
                            if highest_prob >= 60:
                                pick = home_team if home_prob >= 60 else away_team
                                pick_odds = "N/A"
                                haodd_div = row.find('div', class_='haodd')
                                if haodd_div:
                                    odds_vals = [s.text.strip() for s in haodd_div.find_all('span') if '.' in s.text.strip()]
                                    if len(odds_vals) >= 3:
                                        pick_odds = odds_vals[0] if home_prob >= 60 else odds_vals[2]

                                all_targets.append({
                                    'Home Team': home_team,
                                    'Away Team': away_team,
                                    'Win Probability': f"{highest_prob}%",
                                    'Algorithm Pick': f"🎯 {pick} to Win",
                                    'Forebet Odds': pick_odds,
                                    '_raw_prob': highest_prob 
                                })
                except:
                    continue 
    except Exception as e:
        st.error(f"❌ Engine 1 crashed: {e}")
        
    all_targets = sorted(all_targets, key=lambda x: x['_raw_prob'], reverse=True)
    for target in all_targets:
        del target['_raw_prob']
        
    return all_targets[:10]

# ==========================================
# 3. ENGINE 2: API-FOOTBALL FACT-CHECKER (WITH SMART FILTER)
# ==========================================
def get_api_football_facts(team_name):
    # 🛑 PASTE YOUR API KEY HERE 🛑
    api_key = "3b0601a38ca386edc1a448c3fb760a6e"
    headers = {'x-apisports-key': api_key}
    today = datetime.now().strftime("%Y-%m-%d")
    
    # --- NEW SMART NAME CLEANER ---
    words = team_name.replace('-', ' ').split()
    clean_words = [w for w in words if len(w) > 2 and w.lower() not in ['fc', 'nk', 'fk', 'u20', 'u21', 'žnk', 'sbv', 'psv', 'w']]
    
    if clean_words:
        search_term = max(clean_words, key=len)
    else:
        search_term = team_name[:5] 
    # ------------------------------
    
    search_url = f"https://v3.football.api-sports.io/fixtures?date={today}&search={search_term}" 
    
    try:
        search_res = requests.get(search_url, headers=headers).json()
        if search_res.get('response'):
            fixture_id = search_res['response'][0]['fixture']['id']
            
            pred_url = f"https://v3.football.api-sports.io/predictions?fixture={fixture_id}"
            pred_res = requests.get(pred_url, headers=headers).json()
            
            if pred_res.get('response'):
                data = pred_res['response'][0]
                advice = data['predictions']['advice']
                
                home_form = data['teams']['home']['league'].get('form', 'N/A') if data['teams']['home'].get('league') else 'N/A'
                away_form = data['teams']['away']['league'].get('form', 'N/A') if data['teams']['away'].get('league') else 'N/A'
                
                return {
                    "API Advice": advice,
                    "Home Form": home_form,
                    "Away Form": away_form
                }
    except Exception as e:
        pass 
        
    return None

# ==========================================
# 4. DASHBOARDS
# ==========================================
def get_all_users(): return users_sheet.get_all_records()
def get_all_pending(): return pending_sheet.get_all_records()
def get_all_results(): return results_sheet.get_all_records() if results_sheet else []
def check_expiry(user_record):
    return datetime.now().date() <= datetime.strptime(user_record['expiry'], "%Y-%m-%d").date()

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
    
    if st.button("🔍 Generate VIP Slips (Dual Engine Consensus)", type="primary", use_container_width=True):
        
        # 1. AWAKEN THE FOREBET BRAIN
        with st.spinner("🧠 Engine 1: Forebet scanning global matches for safe picks..."):
            premium_targets = get_forebet_premium_targets()
            
        if not premium_targets:
            st.warning("⚠️ Engine 1 says: No exceptionally safe matches today. Protect your bankroll!")
            return
            
        st.success(f"✅ Engine 1 found {len(premium_targets)} highly secure matches! Handing over to Engine 2...")
        
        # 2. AWAKEN THE FACT-CHECKER
        verified_picks = []
        progress_text = "🕵️ Engine 2: Fact-Checking matches via API-Football..."
        my_bar = st.progress(0, text=progress_text)
        
        for i, target in enumerate(premium_targets):
            # Update progress bar
            progress = (i + 1) / len(premium_targets)
            my_bar.progress(progress, text=f"Fact-Checking: {target['Home Team']}...")
            
            # Ping API-Football
            facts = get_api_football_facts(target['Home Team'])
            
            # Combine the data
            if facts:
                target['API-Sports Advice'] = facts['API Advice']
                target['Home Form'] = facts['Home Form']
                target['Away Form'] = facts['Away Form']
            else:
                target['API-Sports Advice'] = "Data Unavailable"
                target['Home Form'] = "N/A"
                target['Away Form'] = "N/A"
                
            verified_picks.append(target)
            
        my_bar.empty() # Clear the progress bar when done
        
        # DISPLAY THE MASTER TABLE
        st.subheader("💎 The God Mode Consensus Singles")
        df_vip = pd.DataFrame(verified_picks)
        st.dataframe(df_vip, use_container_width=True, hide_index=True)
        st.info("👆 Use these picks for your single daily bets. If Forebet's Pick matches the API-Sports Advice, you have a Diamond Tier lock.")

if st.session_state.current_user is None: home_and_register()
else: premium_bot_dashboard()
