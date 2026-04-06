import streamlit as st
from datetime import datetime
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
# 2. CONSTANTS - TUNE THESE
# ==========================================
API_KEY = "3b0601a38ca386edc1a448c3fb760a6e"

# THE CORE PHILOSOPHY: Only take bets where we have HIGH CERTAINTY
# A 65%+ probability with odds between 1.30-1.90 is our sweet spot
MIN_WIN_PROBABILITY = 65       # Minimum % - was 55, that's too low
MAX_ODDS_FOR_SINGLE = 1.90    # Don't go above this - too risky
MIN_ODDS_FOR_SINGLE = 1.25    # Don't go below this - not worth it
TARGET_DAILY_COMBINED_ODDS = (2.0, 3.0)  # Our goal range

# These league IDs are well-tracked by API-Football (reliable data)
TRUSTED_LEAGUE_IDS = {
    39,   # England Premier League
    140,  # Spain La Liga
    135,  # Italy Serie A
    78,   # Germany Bundesliga
    61,   # France Ligue 1
    2,    # UEFA Champions League
    3,    # UEFA Europa League
    94,   # Portugal Primeira Liga
    88,   # Netherlands Eredivisie
    144,  # Belgium Pro League
    203,  # Turkey Super Lig
    179,  # Scotland Premier League
    283,  # Kenya Premier League (local support)
}

# ==========================================
# 3. ENGINE 1: FOREBET SCRAPER (STRICT MODE)
# ==========================================
def scrape_forebet_strict():
    """
    Scrape Forebet but ONLY keep matches that pass strict filters.
    Returns list of candidate matches sorted by probability descending.
    """
    url = 'https://www.forebet.com/en/football-tips-and-predictions-for-today'
    candidates = []

    headers = {
        'user-agent': (
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
            'AppleWebKit/537.36 (KHTML, like Gecko) '
            'Chrome/122.0.0.0 Safari/537.36'
        )
    }

    try:
        response = curl_requests.get(
            url, headers=headers, impersonate="chrome110", timeout=20
        )

        if response.status_code != 200:
            st.error(f"❌ Forebet returned status {response.status_code}")
            return []

        soup = BeautifulSoup(response.text, 'html.parser')
        match_rows = soup.find_all('div', class_='rcnt')

        if not match_rows:
            st.warning("⚠️ Forebet HTML structure may have changed. No match rows found.")
            return []

        for row in match_rows:
            try:
                home_team = row.find('span', class_='homeTeam')
                away_team = row.find('span', class_='awayTeam')
                fprc_div  = row.find('div', class_='fprc')

                # Skip if any essential element is missing
                if not home_team or not away_team or not fprc_div:
                    continue

                home_team = home_team.text.strip()
                away_team = away_team.text.strip()

                spans = fprc_div.find_all('span')
                if len(spans) < 3:
                    continue

                # Parse probabilities (Home Win, Draw, Away Win)
                try:
                    home_prob = int(spans[0].text.strip())
                    draw_prob = int(spans[1].text.strip())
                    away_prob = int(spans[2].text.strip())
                except ValueError:
                    continue

                # --- STRICT FILTER 1: Must have a clear winner ---
                # We only back HOME WIN or AWAY WIN, never draws
                # The leading side must have >= MIN_WIN_PROBABILITY
                if home_prob >= MIN_WIN_PROBABILITY:
                    pick_side = "home"
                    pick_prob = home_prob
                    pick_label = f"🏠 {home_team} to Win"
                elif away_prob >= MIN_WIN_PROBABILITY:
                    pick_side = "away"
                    pick_prob = away_prob
                    pick_label = f"✈️ {away_team} to Win"
                else:
                    continue  # Not confident enough — skip

                # --- STRICT FILTER 2: Draw probability must be low ---
                # High draw probability is a red flag even if one team leads
                if draw_prob > 28:
                    continue  # Too much draw risk

                # --- Extract odds ---
                pick_odds_raw = "N/A"
                haodd_div = row.find('div', class_='haodd')
                if haodd_div:
                    odds_spans = [
                        s.text.strip()
                        for s in haodd_div.find_all('span')
                        if s.text.strip()
                    ]
                    if len(odds_spans) >= 3:
                        pick_odds_raw = odds_spans[0] if pick_side == "home" else odds_spans[-1]

                # Convert American odds → Decimal
                pick_odds_decimal = None
                try:
                    if pick_odds_raw not in ["N/A", "-", "no", ""]:
                        val = float(pick_odds_raw.replace('+', ''))
                        if val <= -100:
                            pick_odds_decimal = round(1 - (100 / val), 2)
                        elif val >= 100:
                            pick_odds_decimal = round(1 + (val / 100), 2)
                        else:
                            pick_odds_decimal = round(float(pick_odds_raw), 2)
                except (ValueError, ZeroDivisionError):
                    pass

                # --- STRICT FILTER 3: Odds must be in our value range ---
                if pick_odds_decimal is None:
                    continue
                if not (MIN_ODDS_FOR_SINGLE <= pick_odds_decimal <= MAX_ODDS_FOR_SINGLE):
                    continue

                candidates.append({
                    'home_team':    home_team,
                    'away_team':    away_team,
                    'home_prob':    home_prob,
                    'draw_prob':    draw_prob,
                    'away_prob':    away_prob,
                    'pick_side':    pick_side,
                    'pick_prob':    pick_prob,
                    'pick_label':   pick_label,
                    'odds':         pick_odds_decimal,
                })

            except Exception:
                continue  # Never crash on a single row

    except Exception as e:
        st.error(f"❌ Forebet scrape failed: {e}")
        return []

    # Sort by probability descending — highest confidence first
    candidates.sort(key=lambda x: x['pick_prob'], reverse=True)
    return candidates


# ==========================================
# 4. ENGINE 2: API-FOOTBALL VALIDATOR
# ==========================================
@st.cache_data(ttl=3600)
def get_todays_fixtures():
    today = datetime.now().strftime("%Y-%m-%d")
    url = f"https://v3.football.api-sports.io/fixtures?date={today}"
    headers = {'x-apisports-key': API_KEY}
    try:
        res = requests.get(url, headers=headers, timeout=10).json()
        return res.get('response', [])
    except Exception as e:
        st.warning(f"API-Football fixtures fetch failed: {e}")
        return []


def validate_with_api_football(candidate, all_fixtures):
    """
    For a Forebet candidate, find it in API-Football and apply extra filters:
    - Must be in a TRUSTED league
    - Check head-to-head and recent form signals
    Returns: dict with validation results, or None if disqualified.
    """
    # Build a search keyword from the team name
    search_name = candidate['home_team'].lower().replace('-', ' ')
    words = [w for w in search_name.split() if len(w) > 3 and w not in {'city', 'town', 'united', 'sport', 'club'}]
    keyword = max(words, key=len) if words else search_name[:5]

    # Find fixture in API-Football
    fixture = None
    for f in all_fixtures:
        api_home = f['teams']['home']['name'].lower()
        api_away = f['teams']['away']['name'].lower()
        if keyword in api_home or keyword in api_away:
            fixture = f
            break

    if not fixture:
        return {'status': 'unverified', 'reason': 'Not in API database'}

    # --- STRICT FILTER 4: Trusted league only ---
    league_id = fixture['league']['id']
    if league_id not in TRUSTED_LEAGUE_IDS:
        return {'status': 'rejected', 'reason': f"Untrusted league (ID {league_id})"}

    fixture_id = fixture['fixture']['id']
    league_name = fixture['league']['name']

    # Fetch predictions from API-Football
    headers = {'x-apisports-key': API_KEY}
    try:
        pred_res = requests.get(
            f"https://v3.football.api-sports.io/predictions?fixture={fixture_id}",
            headers=headers,
            timeout=10
        ).json()
    except Exception:
        return {'status': 'unverified', 'reason': 'Prediction fetch failed'}

    if not pred_res.get('response'):
        return {'status': 'unverified', 'reason': 'No prediction data'}

    data = pred_res['response'][0]
    predictions = data.get('predictions', {})
    teams_data  = data.get('teams', {})

    # Extract API win percentages
    home_win_pct_str = predictions.get('percent', {}).get('home', '0%')
    away_win_pct_str = predictions.get('percent', {}).get('away', '0%')
    try:
        api_home_pct = int(home_win_pct_str.replace('%', ''))
        api_away_pct = int(away_win_pct_str.replace('%', ''))
    except ValueError:
        api_home_pct = api_away_pct = 0

    # Extract recent form (last 5 games)
    def get_form(team_key):
        try:
            form = teams_data[team_key]['league'].get('form', '')
            return form[-5:] if form else 'N/A'
        except (KeyError, TypeError):
            return 'N/A'

    home_form = get_form('home')
    away_form = get_form('away')

    # --- STRICT FILTER 5: API-Football must AGREE with Forebet ---
    # If Forebet says home wins, API must also favour home (>= 50%)
    if candidate['pick_side'] == 'home' and api_home_pct < 50:
        return {
            'status': 'rejected',
            'reason': f"API disagrees (gives home only {api_home_pct}%)"
        }
    if candidate['pick_side'] == 'away' and api_away_pct < 50:
        return {
            'status': 'rejected',
            'reason': f"API disagrees (gives away only {api_away_pct}%)"
        }

    # --- STRICT FILTER 6: Form check ---
    # Count recent wins in form string
    pick_form = home_form if candidate['pick_side'] == 'home' else away_form
    if pick_form != 'N/A':
        wins_in_form = pick_form.count('W')
        losses_in_form = pick_form.count('L')
        # Reject if team lost 2 or more of last 5
        if losses_in_form >= 2:
            return {
                'status': 'rejected',
                'reason': f"Poor recent form: {pick_form}"
            }

    return {
        'status': 'verified',
        'league':     league_name,
        'api_home_pct': api_home_pct,
        'api_away_pct': api_away_pct,
        'home_form':  home_form,
        'away_form':  away_form,
    }


# ==========================================
# 5. SLIP BUILDER — TARGET 2.0 TO 3.0 ODDS
# ==========================================
def build_daily_slip(verified_picks):
    """
    Build ONE clean slip targeting 2.0 - 3.0 combined odds.
    Strategy: start with the highest-confidence pick, add one more if needed.
    Never force-add picks just to hit a number.
    """
    if not verified_picks:
        return [], 1.0

    lo, hi = TARGET_DAILY_COMBINED_ODDS

    # Strategy A: Can a single pick already sit in our target range?
    best = verified_picks[0]
    if lo <= best['odds'] <= hi:
        return [best], best['odds']

    # Strategy B: Combine top 2 picks
    if len(verified_picks) >= 2:
        combined = verified_picks[0]['odds'] * verified_picks[1]['odds']
        if lo <= combined <= hi:
            return [verified_picks[0], verified_picks[1]], round(combined, 2)

    # Strategy C: Combine top 3 picks (never go beyond 3)
    if len(verified_picks) >= 3:
        combined = verified_picks[0]['odds'] * verified_picks[1]['odds'] * verified_picks[2]['odds']
        if combined <= hi + 0.5:  # Small tolerance
            return [verified_picks[0], verified_picks[1], verified_picks[2]], round(combined, 2)

    # If nothing fits, return just the single best pick
    return [verified_picks[0]], verified_picks[0]['odds']


# ==========================================
# 6. USER MANAGEMENT (UNCHANGED)
# ==========================================
def get_all_users():    return users_sheet.get_all_records()
def get_all_results():  return results_sheet.get_all_records() if results_sheet else []

def check_expiry(user_record):
    return datetime.now().date() <= datetime.strptime(
        user_record['expiry'], "%Y-%m-%d"
    ).date()


# ==========================================
# 7. UI — HOME / REGISTRATION
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
                    if (
                        str(u['username']) == login_user
                        and str(u['password']) == login_pass
                        and u['status'] == 'active'
                        and check_expiry(u)
                    ):
                        st.session_state.current_user = login_user
                        st.rerun()
                st.error("Invalid credentials or expired account.")

        with col2:
            st.header("Get Premium Access")
            st.info("💰 Weekly: 500 KES | Monthly: 1,500 KES (Send to 0758275510)")
            reg_user   = st.text_input("Choose Username")
            mpesa_code = st.text_input("M-Pesa Code", max_chars=10)
            if st.button("Submit Payment", type="primary"):
                pending_sheet = sheet.worksheet("Pending")
                pending_sheet.append_row([
                    reg_user, "password", "Monthly",
                    mpesa_code.upper(), str(datetime.now().date())
                ])
                st.success("✅ Submitted! Wait 10 mins for activation.")

    with tab_verify:
        st.header("📊 Verified Profit History")
        data = get_all_results()
        if data:
            st.dataframe(pd.DataFrame(data), use_container_width=True, hide_index=True)
        else:
            st.info("Verified results are being compiled.")


# ==========================================
# 8. UI — PREMIUM DASHBOARD
# ==========================================
def premium_bot_dashboard():
    st.title("📈 ValueBet God Mode")
    if st.button("Logout"):
        st.session_state.current_user = None
        st.rerun()

    st.info(
        "**Philosophy:** We do NOT chase high odds. We find 2-3 matches where "
        "the math is overwhelmingly in our favour, combine them to hit 2.0-3.0, "
        "and repeat that daily. Consistency beats jackpots."
    )
    st.divider()

    if st.button("🔍 Generate Today's Slip", type="primary", use_container_width=True):

        # --- Step 1: Scrape Forebet with strict filters ---
        with st.spinner("🧠 Engine 1: Scanning Forebet with strict filters (65%+ only)..."):
            raw_candidates = scrape_forebet_strict()

        if not raw_candidates:
            st.error(
                "❌ No matches passed the strict probability filter today. "
                "This is the system protecting your bankroll. **Do not bet today.**"
            )
            return

        st.success(f"✅ {len(raw_candidates)} candidates passed initial filter. Verifying with API-Football...")

        # --- Step 2: Validate each candidate with API-Football ---
        all_fixtures = get_todays_fixtures()
        verified_picks = []
        rejected_log   = []

        progress = st.progress(0, text="Validating candidates...")
        for i, candidate in enumerate(raw_candidates):
            progress.progress((i + 1) / len(raw_candidates), text=f"Checking: {candidate['home_team']} vs {candidate['away_team']}")
            result = validate_with_api_football(candidate, all_fixtures)
            candidate['validation'] = result

            if result['status'] == 'verified':
                candidate.update(result)
                verified_picks.append(candidate)
            else:
                rejected_log.append({
                    'Match': f"{candidate['home_team']} vs {candidate['away_team']}",
                    'Reason': result['reason'],
                    'Our Pick': candidate['pick_label'],
                    'Forebet Prob': f"{candidate['pick_prob']}%",
                })
        progress.empty()

        # --- Step 3: Build the daily slip ---
        slip, slip_odds = build_daily_slip(verified_picks)

        # =====================
        # DISPLAY: Today's Slip
        # =====================
        st.header("🎯 Today's Recommended Slip")

        if not slip:
            st.warning(
                "⚠️ No picks survived dual-engine verification today. "
                "The system says: **skip today**. Your bankroll is safe."
            )
        else:
            lo, hi = TARGET_DAILY_COMBINED_ODDS
            if lo <= slip_odds <= hi:
                st.success(f"✅ Slip is within target range: **{slip_odds:.2f} odds**")
            else:
                st.info(f"ℹ️ Best available slip odds: **{slip_odds:.2f}** (slightly outside 2.0-3.0 target)")

            for idx, pick in enumerate(slip, 1):
                with st.container(border=True):
                    col_a, col_b, col_c = st.columns([3, 1, 1])
                    with col_a:
                        st.subheader(f"Pick {idx}: {pick['pick_label']}")
                        st.caption(f"{pick['home_team']} vs {pick['away_team']}")
                        if pick.get('league'):
                            st.caption(f"🏆 League: {pick['league']}")
                    with col_b:
                        st.metric("Confidence", f"{pick['pick_prob']}%")
                        st.metric("Draw Risk", f"{pick['draw_prob']}%")
                    with col_c:
                        st.metric("Odds", f"{pick['odds']:.2f}")
                        form_key = 'home_form' if pick['pick_side'] == 'home' else 'away_form'
                        if pick.get(form_key) and pick[form_key] != 'N/A':
                            st.metric("Last 5", pick[form_key])

            st.metric("🎟️ Combined Slip Odds", f"{slip_odds:.2f}")

        # =====================
        # DISPLAY: Full Verified Table
        # =====================
        if verified_picks:
            st.divider()
            st.subheader("📋 All Verified Picks (Singles Reference)")
            display_rows = []
            for p in verified_picks:
                display_rows.append({
                    'Match':       f"{p['home_team']} vs {p['away_team']}",
                    'Pick':        p['pick_label'],
                    'Confidence':  f"{p['pick_prob']}%",
                    'Draw Risk':   f"{p['draw_prob']}%",
                    'Odds':        p['odds'],
                    'League':      p.get('league', 'N/A'),
                    'Home Form':   p.get('home_form', 'N/A'),
                    'Away Form':   p.get('away_form', 'N/A'),
                    'API Home%':   p.get('api_home_pct', 'N/A'),
                    'API Away%':   p.get('api_away_pct', 'N/A'),
                })
            st.dataframe(pd.DataFrame(display_rows), use_container_width=True, hide_index=True)

        # =====================
        # DISPLAY: Rejected (transparency)
        # =====================
        if rejected_log:
            with st.expander(f"🗑️ {len(rejected_log)} matches rejected (tap to see why)"):
                st.caption("Transparency log — these matches failed our strict dual-engine filter.")
                st.dataframe(pd.DataFrame(rejected_log), use_container_width=True, hide_index=True)


# ==========================================
# 9. ROUTER
# ==========================================
if st.session_state.current_user is None:
    home_and_register()
else:
    premium_bot_dashboard()
