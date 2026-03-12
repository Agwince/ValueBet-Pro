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
                            
                            # Lowered slightly to 55% to ensure enough volume for accumulators
                            if highest_prob >= 55: 
                                pick = home_team if home_prob >= 55 else away_team
                                pick_odds = "N/A"
                                
                                # UPGRADED ODDS SCRAPER
                                haodd_div = row.find('div', class_='haodd')
                                if haodd_div:
                                    odds_vals = [s.text.strip() for s in haodd_div.find_all('span') if s.text.strip()]
                                    if len(odds_vals) >= 3:
                                        # Home is usually first [0], Away is usually last [-1]
                                        pick_odds = odds_vals[0] if home_prob >= 55 else odds_vals[-1]

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
        
    return all_targets[:20] 

# ==========================================
# 3. ENGINE 2: API-FOOTBALL FACT-CHECKER
# ==========================================
# 🛑 PASTE YOUR API KEY HERE ONCE 🛑
API_KEY = "PASTE_YOUR_KEY_HERE"

@st.cache_data(ttl=3600)
def get_todays_fixtures_master_list():
    today = datetime.now().strftime("%Y-%m-%d")
    url = f"https://v3.football.api-sports.io/fixtures?date={today}"
    headers = {'x-apisports-key': API_KEY}
    try:
        res = requests.get(url, headers=headers).json()
        return res.get('response', [])
    except:
        return []

def get_api_football_facts(team_name, todays_fixtures):
    words = team_name.replace('-', ' ').split()
    clean_words = [w for w in words if len(w) > 3 and w.lower() not in ['fc', 'nk', 'fk', 'žnk', 'sbv', 'psv']]
    
    search_term = max(clean_words, key=len).lower() if clean_words else team_name[:5].lower()
    
    fixture_id = None
    for match in todays_fixtures:
        api_home = match['teams']['home']['name'].lower()
        api_away = match['teams']['away']['name'].lower()
        
        if search_term in api_home or search_term in api_away:
            fixture_id = match['fixture']['id']
            break
            
    if not fixture_id:
        return None 
        
    headers = {'x-apisports-key': API_KEY}
    pred_url = f"https://v3.football.api-sports.io/predictions?fixture={fixture_id}"
    
    try:
        pred_res = requests.get(pred_url, headers=headers).json()
        if pred_res.get('response'):
            data = pred_res['response'][0]
            advice = data['predictions']['advice']
            home_form = data['teams']['home']['league'].get('form', 'N/A') if data['teams']['home'].get('league') else 'N/A'
            away_form = data['teams']['away']['league'].get('form', 'N/A') if data['teams']['away'].get('league') else 'N/A'
            
            return {
                "API Advice": advice,
                "Home Form": home_form[-5:] if home_form != 'N/A' else 'N/A', 
                "Away Form": away_form[-5:] if away_form != 'N/A' else 'N/A'
            }
    except:
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
        
        with st.spinner("🧠 Engine 1: Forebet scanning global matches for safe picks..."):
            premium_targets = get_forebet_premium_targets()
            
        if not premium_targets:
            st.warning("⚠️ Engine 1 says: No exceptionally safe matches today. Protect your bankroll!")
            return
            
        st.success(f"✅ Engine 1 found {len(premium_targets)} highly secure matches! Handing over to Engine 2...")
        
        verified_picks = []
        my_bar = st.progress(0, text="🕵️ Engine 2: Downloading Master Daily Database...")
        todays_fixtures = get_todays_fixtures_master_list() 
        
        for i, target in enumerate(premium_targets):
            progress = (i + 1) / len(premium_targets)
            my_bar.progress(progress, text=f"Fact-Checking against Master Database: {target['Home Team']}...")
            
            facts = get_api_football_facts(target['Home Team'], todays_fixtures)
            
            if facts:
                target['API-Sports Advice'] = facts['API Advice']
                target['Home Form'] = facts['Home Form']
                target['Away Form'] = facts['Away Form']
            else:
                target['API-Sports Advice'] = "No Match in Database"
                target['Home Form'] = "N/A"
                target['Away Form'] = "N/A"
                
            verified_picks.append(target)
            
        my_bar.empty() 
        
        # DISPLAY THE MASTER TABLE (SINGLES)
        st.subheader("💎 The God Mode Consensus Singles")
        st.caption("Your core bankroll protection strategy. Look for matches where Forebet and API-Sports agree.")
        df_vip = pd.DataFrame(verified_picks)
        st.dataframe(df_vip, use_container_width=True, hide_index=True)
        
        # ==========================================
        # MULTI-ODD VIP SLIP GENERATOR
        # ==========================================
        st.divider()
        st.header("🎟️ VIP Auto-Builders")
        st.write("Automatically mathematically assembled combination slips from today's highest-probability matches.")
        
        valid_matches = []
        for p in verified_picks:
            try:
                # We only want matches that both have odds AND were found in the API Database
                if p['Forebet Odds'] not in ["N/A", "-", ""] and p['API-Sports Advice'] != "No Match in Database":
                    p['float_odds'] = float(p['Forebet Odds'])
                    p['raw_prob'] = int(p['Win Probability'].replace('%', ''))
                    valid_matches.append(p)
            except:
                continue
                
        valid_matches.sort(key=lambda x: x['raw_prob'], reverse=True)
        
        if len(valid_matches) < 2:
            st.warning("Not enough high-quality matches with bookmaker odds to build accumulators today. Stick to singles from the table above!")
        else:
            col1, col2, col3 = st.columns(3)
            
            # --- 2-ODD DOUBLE ---
            with col1:
                st.subheader("🔥 2-Odd Double")
                current_odds = 1.0
                slip_2 = []
                for match in valid_matches:
                    if current_odds < 2.0 and len(slip_2) < 3: 
                        slip_2.append(match)
                        current_odds *= match['float_odds']
                
                for m in slip_2:
                    st.success(f"**{m['Algorithm Pick']}**\n\nProb: {m['Win Probability']} | Odds: {m['Forebet Odds']}")
                st.metric("Total Slip Odds", f"{current_odds:.2f}")

            # --- 3-ODD TREBLE ---
            with col2:
                st.subheader("🚀 3-Odd Slip")
                current_odds = 1.0
                slip_3 = []
                for match in valid_matches:
                    if current_odds < 3.5: 
                        slip_3.append(match)
                        current_odds *= match['float_odds']
                
                if current_odds >= 2.5: 
                    for m in slip_3:
                        st.info(f"**{m['Algorithm Pick']}**\n\nOdds: {m['Forebet Odds']}")
                    st.metric("Total Slip Odds", f"{current_odds:.2f}")
                else:
                    st.write("Not enough safe matches to hit 3+ odds.")

            # --- 5-ODD ACCUMULATOR ---
            with col3:
                st.subheader("💎 5-Odd Slip")
                current_odds = 1.0
                slip_5 = []
                for match in valid_matches:
                    if current_odds < 5.5: 
                        slip_5.append(match)
                        current_odds *= match['float_odds']
                
                if current_odds >= 4.0:
                    for m in slip_5:
                        st.warning(f"**{m['Algorithm Pick']}**\n\nOdds: {m['Forebet Odds']}")
                    st.metric("Total Slip Odds", f"{current_odds:.2f}")
                else:
                    st.write("Not enough safe matches to hit 5+ odds.")

if st.session_state.current_user is None: home_and_register()
else: premium_bot_dashboard()
