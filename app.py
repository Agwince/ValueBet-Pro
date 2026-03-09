import streamlit as st
from datetime import datetime, timedelta
import pandas as pd

st.set_page_config(page_title="ValueBet Algorithm Pro", layout="wide", page_icon="🤖")

# ==========================================
# 1. DATABASE SETUP (Using session_state for testing)
# In a real app, you would save this to a JSON file or database
# ==========================================
if 'users' not in st.session_state:
    st.session_state.users = {
        "admin": {"password": "adminpassword", "role": "admin", "expiry": "2099-01-01", "status": "active"}
    }
if 'pending_payments' not in st.session_state:
    st.session_state.pending_payments = []
if 'current_user' not in st.session_state:
    st.session_state.current_user = None

# ==========================================
# 2. HELPER FUNCTIONS
# ==========================================
def check_expiry(username):
    """Automatically locks out users if their time is up."""
    user_data = st.session_state.users.get(username)
    if not user_data:
        return False
    
    expiry_date = datetime.strptime(user_data['expiry'], "%Y-%m-%d").date()
    today = datetime.now().date()
    
    if today > expiry_date:
        st.session_state.users[username]['status'] = "expired"
        return False
    return True

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
            if login_user in st.session_state.users and st.session_state.users[login_user]['password'] == login_pass:
                if st.session_state.users[login_user]['status'] == 'active':
                    if check_expiry(login_user):
                        st.session_state.current_user = login_user
                        st.rerun()
                    else:
                        st.error("❌ Your subscription has expired. Please renew below.")
                else:
                    st.warning("⏳ Your account is pending admin approval.")
            else:
                st.error("Invalid Username or Password.")

    with col2:
        st.header("💎 Get Premium Access")
        st.markdown("**Step 1:** Send payment via M-Pesa Pochi La Biashara to **07XX-XXX-XXX**.")
        st.info("💰 **Weekly Plan:** 500 KES\n\n💰 **Monthly Plan:** 1,500 KES")
        st.markdown("**Step 2:** Fill out the form below with your M-Pesa Code to activate your account.")
        
        reg_user = st.text_input("Choose a Username")
        reg_pass = st.text_input("Choose a Password", type="password")
        plan = st.selectbox("Select Your Plan", ["Weekly (500 KES)", "Monthly (1,500 KES)"])
        mpesa_code = st.text_input("M-Pesa Transaction Code (e.g., QAW5...)", max_chars=10)
        
        if st.button("Submit Payment for Verification", type="primary"):
            if reg_user in st.session_state.users:
                st.error("Username already exists. Choose another.")
            elif len(mpesa_code) < 8:
                st.error("Please enter a valid M-Pesa code.")
            else:
                st.session_state.pending_payments.append({
                    "username": reg_user,
                    "password": reg_pass,
                    "plan": plan,
                    "mpesa_code": mpesa_code.upper(),
                    "date_submitted": str(datetime.now().date())
                })
                st.success("✅ Details submitted! Please wait up to 10 minutes for activation.")

def admin_dashboard():
    st.title("🛡️ Admin Panel")
    st.write(f"Logged in as: **{st.session_state.current_user}**")
    
    if st.button("Logout"):
        st.session_state.current_user = None
        st.rerun()
        
    st.subheader("Pending M-Pesa Payments")
    if not st.session_state.pending_payments:
        st.info("No pending payments right now.")
    else:
        for idx, payment in enumerate(st.session_state.pending_payments):
            st.write(f"**User:** {payment['username']} | **Code:** {payment['mpesa_code']} | **Plan:** {payment['plan']}")
            
            col1, col2 = st.columns([1, 4])
            with col1:
                if st.button(f"Approve {payment['username']}", key=f"app_{idx}"):
                    # Calculate Expiry Date automatically
                    days_to_add = 7 if "Weekly" in payment['plan'] else 30
                    expiry_date = (datetime.now() + timedelta(days=days_to_add)).date()
                    
                    # Create the active user
                    st.session_state.users[payment['username']] = {
                        "password": payment['password'],
                        "role": "user",
                        "expiry": str(expiry_date),
                        "status": "active"
                    }
                    # Remove from pending list
                    st.session_state.pending_payments.pop(idx)
                    st.success(f"User {payment['username']} activated until {expiry_date}!")
                    st.rerun()
                    
            with col2:
                if st.button(f"Reject (Fake Code)", key=f"rej_{idx}"):
                    st.session_state.pending_payments.pop(idx)
                    st.error("Payment rejected.")
                    st.rerun()
                    
    st.divider()
    st.subheader("Active Users Database")
    users_df = pd.DataFrame.from_dict(st.session_state.users, orient='index')
    st.dataframe(users_df)

def premium_bot_dashboard():
    st.title("📈 Pro Dashboard: Live Value Bets")
    
    user_data = st.session_state.users[st.session_state.current_user]
    st.success(f"Welcome back, {st.session_state.current_user}! Your subscription is active until {user_data['expiry']}.")
    
    if st.button("Logout"):
        st.session_state.current_user = None
        st.rerun()
        
    st.divider()
    st.markdown("### 🚨 Live Algorithm Output")
    st.write("This is where we will put the upgraded Python bot that scans all leagues, calculates Expected Value (EV), and shows the Kelly Criterion staking advice.")
    
    # Placeholder for bot output
    st.info("Scanning global markets... (Bot logic will be integrated here)")

# ==========================================
# 4. ROUTER LOGIC
# ==========================================
if st.session_state.current_user is None:
    home_and_register()
elif st.session_state.users[st.session_state.current_user]['role'] == 'admin':
    admin_dashboard()
else:
    premium_bot_dashboard()
