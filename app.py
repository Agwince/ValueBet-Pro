import streamlit as st
from datetime import datetime
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
import json
import requests

st.set_page_config(page_title="ValueBet Algorithm Pro", layout="wide", page_icon="🤖")

# ==========================================
# 1. GOOGLE SHEETS CONNECTION
# ==========================================
@st.cache_resource
def init_connection():
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive"
    ]
    creds_dict = json.loads(st.secrets["google_sheets_creds"])
    creds = Credentials.from_service_account_info(creds_dict, scopes=scopes)
    client = gspread.authorize(creds)
    return client.open("ValueBet Database")

sheet         = init_connection()
users_sheet   = sheet.worksheet("Users")
pending_sheet = sheet.worksheet("Pending")
try:
    results_sheet = sheet.worksheet("Results")
except Exception:
    results_sheet = None

if "current_user" not in st.session_state:
    st.session_state.current_user = None

# ==========================================
# 2. CONFIGURATION
# ==========================================
API_KEY = "3b0601a38ca386edc1a448c3fb760a6e"

# Only analyse matches from these leagues.
# These are well-tracked with reliable stats and low match-fixing risk.
TRUSTED_LEAGUE_IDS = {
    39,   # England - Premier League
    40,   # England - Championship
    78,   # Germany - Bundesliga
    79,   # Germany - 2. Bundesliga
    61,   # France - Ligue 1
    135,  # Italy - Serie A
    140,  # Spain - La Liga
    94,   # Portugal - Primeira Liga
    88,   # Netherlands - Eredivisie
    144,  # Belgium - Pro League
    203,  # Turkey - Super Lig
    179,  # Scotland - Premier League
    2,    # UEFA - Champions League
    3,    # UEFA - Europa League
    848,  # UEFA - Conference League
    283,  # Kenya - Premier League
}

# Scoring weights — must add up to 1.0
W_API_PROB   = 0.40   # API-Football win probability
W_FORM       = 0.25   # Recent form vs opponent form
W_ATTACK     = 0.20   # Goals scored vs opponent defence
W_DEFENCE    = 0.15   # Goals conceded vs opponent attack

# Thresholds
MIN_CONFIDENCE   = 65    # Our score out of 100 — raise to be stricter
MIN_ODDS         = 1.25  # Below this, not worth the risk
MAX_ODDS         = 1.90  # Above this, too uncertain for singles
TARGET_ODDS_LOW  = 2.00  # Slip target (low end)
TARGET_ODDS_HIGH = 3.20  # Slip target (high end)
MAX_SLIP_PICKS   = 3     # Never combine more than 3

# ==========================================
# 3. API HELPER
# ==========================================
BASE_URL = "https://v3.football.api-sports.io"

def api_get(endpoint, params=None):
    """Central API caller. Returns response list or [] on failure."""
    try:
        r = requests.get(
            f"{BASE_URL}/{endpoint}",
            headers={"x-apisports-key": API_KEY},
            params=params,
            timeout=15
        )
        data = r.json()
        if data.get("errors"):
            st.warning(f"API error on /{endpoint}: {data['errors']}")
        return data.get("response", [])
    except Exception as e:
        st.warning(f"Request failed ({endpoint}): {e}")
        return []


@st.cache_data(ttl=3600)
def get_todays_fixtures():
    today = datetime.now().strftime("%Y-%m-%d")
    return api_get("fixtures", {"date": today})


@st.cache_data(ttl=3600)
def get_predictions(fixture_id):
    return api_get("predictions", {"fixture": fixture_id})


@st.cache_data(ttl=3600)
def get_odds(fixture_id):
    return api_get("odds", {"fixture": fixture_id, "bet": 1})


@st.cache_data(ttl=86400)
def get_team_stats(team_id, league_id, season=2024):
    result = api_get("teams/statistics", {
        "team": team_id, "league": league_id, "season": season
    })
    return result if result else None


# ==========================================
# 4. CONFIDENCE SCORING ENGINE
# ==========================================
def score_pick(prediction_data, home_stats, away_stats, pick_side):
    """
    Return a 0-100 confidence score and a breakdown dict.

    4 signals:
      1. API-Football predicted win % (40%)
      2. Recent form relative to opponent (25%)
      3. Attack edge: goals scored vs opponent defence (20%)
      4. Defence edge: goals conceded vs opponent attack (15%)
    """
    score = 0
    breakdown = {}

    # ---- Signal 1: API Win Probability ----
    key = "home" if pick_side == "home" else "away"
    pct_str = (
        prediction_data
        .get("predictions", {})
        .get("percent", {})
        .get(key, "0%")
    )
    try:
        api_pct = int(pct_str.replace("%", ""))
    except ValueError:
        api_pct = 0

    s1 = api_pct * W_API_PROB
    score += s1
    breakdown["API Win %"] = f"{api_pct}% → {s1:.1f} pts"

    # ---- Signal 2: Form ----
    def form_to_score(stats):
        """Convert form string to 0-100 score."""
        if not stats:
            return 50
        form = stats.get("form", "") or ""
        recent = form[-5:]
        if not recent:
            return 50
        wins   = recent.count("W")
        losses = recent.count("L")
        return max(0, min(100, 50 + (wins * 20) - (losses * 10)))

    pick_stats = home_stats if pick_side == "home" else away_stats
    opp_stats  = away_stats if pick_side == "home" else home_stats
    pick_form  = form_to_score(pick_stats)
    opp_form   = form_to_score(opp_stats)
    relative   = (pick_form - opp_form + 100) / 2
    s2 = relative * W_FORM
    score += s2
    breakdown["Form"] = f"Pick={pick_form} Opp={opp_form} → {s2:.1f} pts"

    # ---- Signal 3: Attack Edge ----
    def avg_scored(stats):
        try:
            return float(stats["goals"]["for"]["average"]["total"])
        except (TypeError, KeyError):
            return 1.2

    def avg_conceded(stats):
        try:
            return float(stats["goals"]["against"]["average"]["total"])
        except (TypeError, KeyError):
            return 1.2

    p_scored  = avg_scored(pick_stats)
    o_concede = avg_conceded(opp_stats)
    attack_edge = min(100, (p_scored / max(o_concede, 0.5) / 3) * 100)
    s3 = attack_edge * W_ATTACK
    score += s3
    breakdown["Attack"] = f"{p_scored:.2f} scored vs {o_concede:.2f} conceded → {s3:.1f} pts"

    # ---- Signal 4: Defence Edge ----
    p_concede = avg_conceded(pick_stats)
    o_scored  = avg_scored(opp_stats)
    defence_score = min(100, (1 - p_concede / max(o_scored + p_concede, 1)) * 100)
    s4 = defence_score * W_DEFENCE
    score += s4
    breakdown["Defence"] = f"{p_concede:.2f} conceded vs {o_scored:.2f} opp attack → {s4:.1f} pts"

    return round(score, 1), breakdown


def extract_odds(odds_response, pick_side):
    """Pull decimal odds for home or away win from API odds response."""
    target = "Home" if pick_side == "home" else "Away"
    try:
        for bookmaker in odds_response[0].get("bookmakers", []):
            for bet in bookmaker.get("bets", []):
                if bet.get("id") == 1:
                    for v in bet.get("values", []):
                        if v["value"] == target:
                            return float(v["odd"])
    except (IndexError, KeyError, TypeError, ValueError):
        pass
    return None


# ==========================================
# 5. MAIN PIPELINE
# ==========================================
def run_analysis(debug=False):
    picks    = []
    rejected = []

    # --- Fetch all fixtures today ---
    all_fixtures = get_todays_fixtures()
    if not all_fixtures:
        st.error("❌ API-Football returned no fixtures. Check your API key or internet connection.")
        return [], []

    # --- Filter: trusted leagues, not started ---
    trusted = [
        f for f in all_fixtures
        if f["league"]["id"] in TRUSTED_LEAGUE_IDS
        and f["fixture"]["status"]["short"] in ("NS", "TBD")
    ]

    if debug:
        st.info(f"Total fixtures today: {len(all_fixtures)} | Trusted & not started: {len(trusted)}")

    if not trusted:
        st.warning(
            "No fixtures in trusted leagues today (could be an international break "
            "or mid-week gap). The system will have picks on matchdays."
        )
        return [], []

    bar = st.progress(0, text="Analysing matches...")

    for i, f in enumerate(trusted):
        bar.progress(
            (i + 1) / len(trusted),
            text=f"Checking: {f['teams']['home']['name']} vs {f['teams']['away']['name']}"
        )

        fid        = f["fixture"]["id"]
        league_id  = f["league"]["id"]
        league     = f["league"]["name"]
        home_name  = f["teams"]["home"]["name"]
        away_name  = f["teams"]["away"]["name"]
        home_id    = f["teams"]["home"]["id"]
        away_id    = f["teams"]["away"]["id"]

        # Kick-off time
        try:
            ko = datetime.fromisoformat(
                f["fixture"]["date"].replace("Z", "+00:00")
            ).strftime("%H:%M")
        except Exception:
            ko = "TBD"

        def reject(reason):
            rejected.append({
                "Match":  f"{home_name} vs {away_name}",
                "League": league,
                "Reason": reason,
            })

        # --- Predictions ---
        pred_resp = get_predictions(fid)
        if not pred_resp:
            reject("No prediction data")
            continue

        pred_data  = pred_resp[0]
        winner_id  = pred_data.get("predictions", {}).get("winner", {}).get("id")

        if winner_id == home_id:
            pick_side = "home"
        elif winner_id == away_id:
            pick_side = "away"
        else:
            reject("API predicts draw or no winner")
            continue

        # Draw risk check
        draw_str = pred_data.get("predictions", {}).get("percent", {}).get("draws", "0%")
        try:
            draw_pct = int(draw_str.replace("%", ""))
        except ValueError:
            draw_pct = 0

        if draw_pct > 28:
            reject(f"Draw risk too high ({draw_pct}%)")
            continue

        # --- Team stats ---
        home_stats_list = get_team_stats(home_id, league_id)
        away_stats_list = get_team_stats(away_id, league_id)

        # api returns a list; we want the first item dict
        home_stats = home_stats_list[0] if home_stats_list else None
        away_stats = away_stats_list[0] if away_stats_list else None

        # --- Score ---
        confidence, breakdown = score_pick(pred_data, home_stats, away_stats, pick_side)

        if confidence < MIN_CONFIDENCE:
            reject(f"Confidence too low ({confidence}/100)")
            continue

        # --- Odds ---
        odds_resp = get_odds(fid)
        odds      = extract_odds(odds_resp, pick_side)

        if odds is not None and not (MIN_ODDS <= odds <= MAX_ODDS):
            reject(f"Odds {odds} outside range ({MIN_ODDS}–{MAX_ODDS})")
            continue

        # --- Form strings for display ---
        def form_str(stats):
            try:
                return (stats.get("form") or "")[-5:] or "N/A"
            except Exception:
                return "N/A"

        picks.append({
            "match":      f"{home_name} vs {away_name}",
            "home":       home_name,
            "away":       away_name,
            "league":     league,
            "ko":         ko,
            "pick_side":  pick_side,
            "pick_label": f"🏠 {home_name} to Win" if pick_side == "home" else f"✈️ {away_name} to Win",
            "confidence": confidence,
            "draw_pct":   draw_pct,
            "odds":       odds,
            "odds_str":   f"{odds:.2f}" if odds else "No odds data",
            "home_form":  form_str(home_stats),
            "away_form":  form_str(away_stats),
            "breakdown":  breakdown,
        })

        if debug:
            with st.expander(f"🔬 {home_name} vs {away_name} — score breakdown"):
                for k, v in breakdown.items():
                    st.caption(f"**{k}:** {v}")
                st.caption(f"**Total score:** {confidence}/100")

    bar.empty()
    picks.sort(key=lambda x: x["confidence"], reverse=True)
    return picks, rejected


# ==========================================
# 6. SLIP BUILDER
# ==========================================
def build_slip(picks):
    with_odds = [p for p in picks if p["odds"] is not None]

    if not with_odds:
        return ([picks[0]] if picks else []), None

    # Strategy A: Single in range
    if TARGET_ODDS_LOW <= with_odds[0]["odds"] <= TARGET_ODDS_HIGH:
        return [with_odds[0]], round(with_odds[0]["odds"], 2)

    # Strategy B: Double
    if len(with_odds) >= 2:
        c = with_odds[0]["odds"] * with_odds[1]["odds"]
        if TARGET_ODDS_LOW <= c <= TARGET_ODDS_HIGH:
            return [with_odds[0], with_odds[1]], round(c, 2)

    # Strategy C: Treble (max)
    if len(with_odds) >= 3:
        c = with_odds[0]["odds"] * with_odds[1]["odds"] * with_odds[2]["odds"]
        if c <= TARGET_ODDS_HIGH + 0.5:
            return with_odds[:3], round(c, 2)

    # Fallback: best single
    return [with_odds[0]], round(with_odds[0]["odds"], 2)


# ==========================================
# 7. USER AUTH
# ==========================================
def get_all_users():   return users_sheet.get_all_records()
def get_all_results(): return results_sheet.get_all_records() if results_sheet else []

def check_expiry(u):
    try:
        return datetime.now().date() <= datetime.strptime(u["expiry"], "%Y-%m-%d").date()
    except Exception:
        return False


# ==========================================
# 8. HOME PAGE
# ==========================================
def home_and_register():
    st.title("🤖 ValueBet Algorithm Pro")
    tab_login, tab_verify = st.tabs(["🔓 Login & Join", "📊 Verified Results"])

    with tab_login:
        st.success("🔥 Join 978+ Smart Bettors using mathematical edge.")
        col1, col2 = st.columns(2)

        with col1:
            st.header("Login")
            lu = st.text_input("Username", key="lu")
            lp = st.text_input("Password", type="password", key="lp")
            if st.button("Log In"):
                matched = False
                for u in get_all_users():
                    if (
                        str(u["username"]) == lu
                        and str(u["password"]) == lp
                        and u["status"] == "active"
                        and check_expiry(u)
                    ):
                        st.session_state.current_user = lu
                        matched = True
                        st.rerun()
                if not matched:
                    st.error("Invalid credentials or account expired.")

        with col2:
            st.header("Get Premium Access")
            st.info("💰 Weekly: 500 KES | Monthly: 1,500 KES\nSend M-Pesa to: **0758275510**")
            ru = st.text_input("Choose Username")
            mc = st.text_input("M-Pesa Code", max_chars=10)
            if st.button("Submit Payment", type="primary"):
                pending_sheet.append_row([
                    ru, "password", "Monthly", mc.upper(), str(datetime.now().date())
                ])
                st.success("✅ Submitted! You'll be activated within 10 minutes.")

    with tab_verify:
        st.header("📊 Verified Profit History")
        data = get_all_results()
        if data:
            st.dataframe(pd.DataFrame(data), use_container_width=True, hide_index=True)
        else:
            st.info("Results are being compiled. Check back soon.")


# ==========================================
# 9. PREMIUM DASHBOARD
# ==========================================
def premium_dashboard():
    st.title("📈 ValueBet God Mode")

    with st.sidebar:
        st.header("⚙️ Settings")
        debug = st.toggle("🔬 Debug Mode", value=False,
                          help="Shows confidence score breakdown per match")
        st.divider()
        st.markdown(f"👤 Logged in as **{st.session_state.current_user}**")
        st.caption("Powered by API-Football. No scraping. Data every day.")
        if st.button("Logout"):
            st.session_state.current_user = None
            st.rerun()

    st.info(
        "**Strategy:** 1–3 picks per day. High confidence only. "
        "Target 2.0–3.2 combined odds. Discipline beats gambling."
    )
    st.divider()

    if st.button("🔍 Generate Today's Slip", type="primary", use_container_width=True):

        picks, rejected = run_analysis(debug=debug)

        if not picks:
            st.error(
                "❌ No picks passed all filters today. "
                "**Do not bet.** The system is protecting your bankroll. "
                "More picks appear on active matchdays (Sat/Sun/midweek)."
            )
        else:
            slip, slip_odds = build_slip(picks)

            # ---- Today's Slip ----
            st.header("🎯 Today's Slip")

            if slip_odds and TARGET_ODDS_LOW <= slip_odds <= TARGET_ODDS_HIGH:
                st.success(f"✅ In target range: **{slip_odds:.2f} odds**")
            elif slip_odds:
                st.info(f"ℹ️ Best available: **{slip_odds:.2f} odds**")
            else:
                st.warning("No bookmaker odds from API today — use as singles guide only.")

            for idx, p in enumerate(slip, 1):
                with st.container(border=True):
                    ca, cb, cc = st.columns([3, 1, 1])
                    with ca:
                        st.subheader(f"Pick {idx}: {p['pick_label']}")
                        st.caption(f"⏰ {p['ko']}  |  🏆 {p['league']}")
                        st.caption(
                            f"🏠 {p['home']} (form: {p['home_form']})  "
                            f"vs  ✈️ {p['away']} (form: {p['away_form']})"
                        )
                    with cb:
                        st.metric("Confidence", f"{p['confidence']}/100")
                        st.metric("Draw Risk",   f"{p['draw_pct']}%")
                    with cc:
                        st.metric("Odds", p["odds_str"])

            if slip_odds:
                st.metric("🎟️ Combined Odds", f"{slip_odds:.2f}")

            # ---- All passing picks ----
            st.divider()
            st.subheader(f"📋 All {len(picks)} Picks That Passed (Singles Reference)")
            st.dataframe(
                pd.DataFrame([{
                    "Match":      p["match"],
                    "Pick":       p["pick_label"],
                    "Confidence": f"{p['confidence']}/100",
                    "Draw Risk":  f"{p['draw_pct']}%",
                    "Odds":       p["odds_str"],
                    "League":     p["league"],
                    "Kick-off":   p["ko"],
                    "Home Form":  p["home_form"],
                    "Away Form":  p["away_form"],
                } for p in picks]),
                use_container_width=True, hide_index=True
            )

        # ---- Rejected log ----
        if rejected:
            with st.expander(f"🗑️ {len(rejected)} matches filtered out — tap to see why"):
                st.dataframe(pd.DataFrame(rejected), use_container_width=True, hide_index=True)


# ==========================================
# 10. ROUTER
# ==========================================
if st.session_state.current_user is None:
    home_and_register()
else:
    premium_dashboard()
