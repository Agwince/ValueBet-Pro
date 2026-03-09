import streamlit as st
from datetime import datetime, timedelta
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
import json

st.set_page_config(page_title="ValueBet Algorithm Pro", layout="wide", page_icon="🤖")

# ==========================================
# 1. CONNECT TO GOOGLE SHEETS
# ==========================================
@st.cache_resource
def init_connection():
    scopes = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
    # Load the secret JSON we pasted into Streamlit Secrets
    creds_dict = json.loads(st.secrets["google_sheets_creds"])
    creds = Credentials.from_service_account_info(creds_dict, scopes=scopes)
    client = gspread.authorize(creds)
    return client.open("ValueBet Database")

# Connect and load the specific sheets
sheet = init_connection()
users_sheet = sheet.worksheet("Users")
pending_sheet = sheet.worksheet("Pending")

if 'current_user' not in st.session_state:
    st.session_state.current_user = None

# ==========================================
# 2. HELPER FUNCTIONS
# ==========================================
def get_all_users():
    return users_sheet.get_all_records()

def get_all_pending():
    return pending_sheet.get_all_records()

def check_expiry(user_record):
    """Checks if the user's time is up based on the Google Sheet date."""
    expiry_date = datetime.strptime(user_record['expiry'], "%Y-%m-%d").date()
    today = datetime.now().date()
    return today <= expiry_date

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
                # Instantly saves to your Google Sheet!
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
                    
                    # Add to Active Users Google Sheet
                    users_sheet.append_row([payment['username'], payment['password'], "user", str(expiry_date), "active"])
                    
                    # Delete from Pending Google Sheet (Row 2 is the first data row)
                    pending_sheet.delete_rows(idx + 2) 
                    
                    st.success(f"User activated until {expiry_date}!")
                    st.rerun()

def premium_bot_dashboard():
    st.title("📈 Pro Dashboard: Live Value Bets")
    st.success(f"Welcome back, {st.session_state.current_user}!")
    
    if st.button("Logout"):
        st.session_state.current_user = None
        st.rerun()
        
    st.divider()
    st.markdown("### 🚨 Live Algorithm Output")
    st.info("Scanning global markets... (Bot logic will be integrated here)")

# ==========================================
# 4. ROUTER LOGIC
# ==========================================
if st.session_state.current_user is None:
    home_and_register()
else:
    # Check if they are the admin
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
