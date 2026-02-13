import os
from pathlib import Path
import streamlit as st

st.set_page_config(
    page_title="NMK Certification Portal",
    layout="wide"
)
import requests
import time
import pandas as pd
import boto3
from dotenv import load_dotenv
import streamlit.components.v1 as components
st.markdown("""
<style>

/* ===== GLOBAL LAYOUT ===== */
.block-container {
    padding-top: 3rem !important;
    padding-left: 3rem !important;
    padding-right: 3rem !important;
    max-width: 100% !important;
}

/* ===== HEADER ===== */
h1, h2, h3 {
    font-weight: 700 !important;
    color: #1f2937 !important;
}

/* ===== CARD STYLE ===== */
div[data-testid="stForm"],
div[data-testid="stExpander"] {
    background: white;
    padding: 25px;
    border-radius: 14px;
    box-shadow: 0 8px 24px rgba(0,0,0,0.05);
    border: 1px solid #f1f5f9;
}

/* ===== INPUT FIELDS ===== */
input, textarea {
    border-radius: 8px !important;
}

/* ===== PRIMARY BUTTON ===== */
.stButton > button[kind="primary"] {
    background-color: #2563eb !important;
    border-radius: 8px !important;
    font-weight: 600 !important;
    height: 45px !important;
}

.stButton > button[kind="primary"]:hover {
    background-color: #1e40af !important;
}

/* ===== NORMAL BUTTON ===== */
.stButton > button {
    border-radius: 8px !important;
    height: 42px !important;
}

/* ===== RADIO BUTTON CARDS ===== */
div[role="radiogroup"] > label {
    background-color: #f9fafb;
    padding: 14px 16px;
    border-radius: 10px;
    margin-bottom: 10px;
    border: 1px solid #e5e7eb;
    transition: all 0.2s ease;
}

div[role="radiogroup"] > label:hover {
    background-color: #eef2ff;
    border-color: #2563eb;
}



/* ===== METRICS ===== */
div[data-testid="metric-container"] {
    background: white;
    padding: 20px;
    border-radius: 12px;
    box-shadow: 0 6px 18px rgba(0,0,0,0.04);
}

/* ===== PROGRESS BAR ===== */
.stProgress > div > div {
    background-color: #2563eb;
}

/* ===== TIMER ===== */
.timer-box {
    font-size: 28px;
    font-weight: 700;
    padding: 20px;
    border-radius: 12px;
    background: linear-gradient(135deg, #eef2ff, #dbeafe);
    text-align: center;
}

</style>
""", unsafe_allow_html=True)




load_dotenv()

AWS_REGION = os.getenv("AWS_REGION")
COGNITO_CLIENT_ID = os.getenv("COGNITO_CLIENT_ID")

cognito = boto3.client(
    "cognito-idp",
    region_name=AWS_REGION
)


API = "http://127.0.0.1:8000"



def init_session():
    defaults = {
        "access_token": None,
        "user_email": None,
        "is_admin": False,
        "exam_id": None,
        "candidate_exam_id": None,
        "questions": None,
        "answers": {},
        "dirty_answers": set(),   # Track changed answers only
        "time_remaining": 0,
        "time_original": 0,
        "exam_started_at": None,
        "status": None,
        "submitted": False,
        "last_saved": {},
        "last_timer_tick": 0,
        "page": "home",
        "auto_resume_checked": False,  # ✅ NEW: Track if we checked for resume
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v



if "initialized" not in st.session_state:
    init_session()
    st.session_state["initialized"] = True

def show_brand_header():
    # Center the header block
    _, center, _ = st.columns([2, 6, 2])

    with center:
        # Tight logo + text row
        logo_col, text_col = st.columns([1, 5], gap="large")

        with logo_col:
            st.markdown("<div style='margin-top:22px'></div>", unsafe_allow_html=True)
            st.image("frontend/nmk_logo.png", width=140)

        with text_col:
            st.markdown(
                """
                <div style="
                    display: flex;
                    align-items: left;
                    height: 100%;
                    margin-left: -10px;
                ">
                    <h1 style="
                        margin: 0;
                        font-size: 42px;
                        font-weight: 800;
                        color: #1f2937;
                        line-height: 1.1;
                    ">
                        NMK Certification Portal
                    </h1>
                </div>
                """,
                unsafe_allow_html=True
            )

    
def auth_headers():
    token = st.session_state["access_token"]
    if not token:
        return {}
    return {"Authorization": f"Bearer {token}"}


def api_post(path, json=None, headers=None):
    try:
        return requests.post(API + path, json=json, headers=headers, timeout=180)
    except Exception as e:
        st.error(f"Connection error: {e}")
        return None


def api_get(path, headers=None):
    try:
        return requests.get(API + path, headers=headers, timeout=180)
    except Exception as e:
        st.error(f"Connection error: {e}")
        return None


def get_resumable_exam():
    """Check if user has an unfinished exam"""
    try:
        resp = api_get("/exam/resume", headers=auth_headers())
        if resp and resp.status_code == 200:
            return resp.json()
        return None
    except Exception as e:
        return None


def api_patch(path, json=None, headers=None):
    try:
        return requests.patch(API + path, json=json, headers=headers, timeout=10)
    except Exception as e:
        st.error(f"Connection error: {e}")
        return None


# ✅ NEW: Auto-resume function
def auto_resume_exam_if_needed():
    """
    Automatically restore exam state after browser refresh.
    This runs once when the user is logged in but session state is empty.
    """
    # Only run once per session
    if st.session_state.get("auto_resume_checked"):
        return
    
    st.session_state["auto_resume_checked"] = True
    
    # Only auto-resume if we don't have an active exam in session
    if st.session_state.get("candidate_exam_id"):
        return
    
    # Check if there's a resumable exam in the database
    resumable = get_resumable_exam()
    
    if resumable:
        print("🔄 AUTO-RESUMING EXAM AFTER PAGE REFRESH")
        
        elapsed = resumable["time_elapsed"]
        
        # Restore full session state
        st.session_state.update({
            "candidate_exam_id": resumable["candidate_exam_id"],
            "questions": resumable["questions"],
            "answers": resumable["answers"],
            "last_saved": resumable["answers"].copy(),
            "time_original": resumable["time_allowed_secs"],
            "time_remaining": max(0, resumable["time_allowed_secs"] - elapsed),
            "exam_started_at": time.time() - elapsed,
            "status": "in_progress",
            "page": "exam",
        })
        
        # Show a notification that we auto-resumed
        st.toast("✅ Exam resumed automatically", icon="🔄")


def login_ui():
    _, center, _ = st.columns([2, 6, 2])

    with center:
        logo_col, text_col = st.columns([2, 6], gap="small")

        with logo_col:
            st.markdown("<div style='margin-top:22px'></div>", unsafe_allow_html=True)
            st.image("frontend/nmk_logo.png", width=160)

        with text_col:
            st.markdown(
                """
                <div style="
                    display: flex;
                    align-items: left;
                    height: 100%;
                    margin-left: -10px;
                ">
                    <h1 style="
                        margin: 0;
                        font-size: 42px;
                        font-weight: 800;
                        color: #1f2937;
                        line-height: 1.1;
                    ">
                        NMK Certification Portal
                    </h1>
                </div>
                """,
                unsafe_allow_html=True
            )

    st.subheader("Login to Your Account")

    with st.form("login_form"):
        email = st.text_input("Email Address")
        pwd = st.text_input("Password", type="password")
        submitted = st.form_submit_button("Login", use_container_width=True)

        if submitted:
            if not email or not pwd:
                st.error("Please enter both email and password")
                return

            try:
                # 🔐 Cognito authentication
                response = cognito.initiate_auth(
                    ClientId=COGNITO_CLIENT_ID,
                    AuthFlow="USER_PASSWORD_AUTH",
                    AuthParameters={
                        "USERNAME": email,
                        "PASSWORD": pwd
                    }
                )

                token = response["AuthenticationResult"]["IdToken"]

                st.session_state["access_token"] = token
                st.session_state["user_email"] = email

                # 🔄 Sync user with backend
                sync_resp = api_post("/auth/sync", headers=auth_headers())
                if not sync_resp or sync_resp.status_code != 200:
                    st.error("Failed to sync user with server")
                    return

                # 🔍 Get admin status from backend
                me_resp = api_get("/auth/me", headers=auth_headers())
                if me_resp and me_resp.status_code == 200:
                    st.session_state["is_admin"] = me_resp.json().get("is_admin", False)
                else:
                    st.session_state["is_admin"] = False

                st.success("Login successful!")
                st.rerun()

            except Exception as e:
                st.error("Invalid email or password")
    
    if st.button("Forgot Password?", use_container_width=True):
        st.session_state["page"] = "forgot_password"
        st.rerun()    

    st.markdown("---")

    # Centered Create Account button
    col_left, col_center, col_right = st.columns([2, 4, 2])

    with col_center:
        if st.button("🆕 Create New Account", width="stretch"):
            st.session_state["page"] = "register"
            st.rerun()

        st.caption("New users must register through Cognito.")


            


def register_ui():
    # ---- Header Section (Same as Login) ----
    _, center, _ = st.columns([2, 6, 2])

    with center:
        # Tight logo + text row
        logo_col, text_col = st.columns([2, 6], gap="small")

        with logo_col:
            st.markdown("<div style='margin-top:22px'></div>", unsafe_allow_html=True)
            st.image("frontend/nmk_logo.png", width=160)

        with text_col:
            st.markdown(
                """
                <div style="
                    display: flex;
                    align-items: left;
                    height: 100%;
                    margin-left: -10px;
                ">
                    <h1 style="
                        margin: 0;
                        font-size: 42px;
                        font-weight: 800;
                        color: #1f2937;
                        line-height: 1.1;
                    ">
                        NMK Certification Portal
                    </h1>
                </div>
                """,
                unsafe_allow_html=True
            )


    # ---- Centered Form Section ----
    _, center, _ = st.columns([2, 4, 2])

    with center:
        st.subheader("📝 Create a New Account")

        with st.form("register_form"):
            name = st.text_input("Full Name")
            email = st.text_input("Email Address")
            password = st.text_input("Password", type="password")
            confirm_password = st.text_input("Confirm Password", type="password")

            submitted = st.form_submit_button("Register", width="stretch")

            if submitted:
                if not email or not password:
                    st.error("Email and password are required")
                    return

                if password != confirm_password:
                    st.error("Passwords do not match")
                    return

                try:
                    cognito.sign_up(
                        ClientId=COGNITO_CLIENT_ID,
                        Username=email,
                        Password=password,
                        UserAttributes=[
                            {"Name": "email", "Value": email},
                            {"Name": "name", "Value": name}
                        ]
                    )

                    st.success("✅ Registration successful! Check your email for verification code.")

                    st.session_state["verify_email"] = email
                    st.session_state["page"] = "verify"
                    st.rerun()

                except Exception:
                    st.error("Registration failed. Email may already exist.")

        st.markdown("---")

        if st.button("⬅️ Back to Login", width="stretch"):
            st.session_state["page"] = "login"
            st.rerun()




def verify_ui():
    st.subheader("Verify Your Email")

    email = st.session_state.get("verify_email")

    st.write(f"A verification code was sent to {email}")

    code = st.text_input("Enter Verification Code")

    if st.button("Verify Account", use_container_width=True):
        try:
            cognito.confirm_sign_up(
                ClientId=COGNITO_CLIENT_ID,
                Username=email,
                ConfirmationCode=code
            )

            st.success("✅ Account verified successfully! You can now login.")
            st.session_state["page"] = "login"
            st.rerun()

        except Exception as e:
            st.error(f"Verification failed: {str(e)}")

    if st.button("⬅️ Back to Login", use_container_width=True):
        st.session_state["page"] = "login"
        st.rerun()



def admin_dashboard():
    st.title("🔧 Admin Dashboard")
    
    tab1, tab2, tab3, tab4 = st.tabs(["Create Exam", "Manage Exams", "Assign Exams", "Candidate Results"])
    
    # TAB 1: CREATE EXAM
    with tab1:
        st.subheader("Create New Exam with LLM Questions")
        
        with st.form("create_exam_form"):
            title = st.text_input("Exam Title", placeholder="e.g., Java Certification Level 1")
            language = st.text_input("Programming Language", placeholder="e.g., Java, Python, JavaScript")
            
            col1, col2 = st.columns(2)
            with col1:
                question_count = st.number_input("Number of Questions", min_value=5, max_value=100, value=10)
            with col2:
                time_minutes = st.number_input("Time Limit (minutes)", min_value=5, max_value=180, value=30)
            
            submit = st.form_submit_button("🚀 Create Exam", use_container_width=True)
            
            if submit:
                if not title or not language:
                    st.error("Please fill in all fields")
                    return
                
                with st.spinner("Fetching questions from LLM... This may take a moment."):
                    resp = api_post(
                        "/admin/exams",
                        json={
                            "title": title,
                            "language": language,
                            "question_count": question_count,
                            "time_allowed_secs": time_minutes * 60
                        },
                        headers=auth_headers()
                    )
                    
                    if resp and resp.status_code == 200:
                        st.success(f"✅ Exam '{title}' created successfully!")
                        st.balloons()
                        st.rerun()
                    else:
                        error_detail = resp.json().get("detail", "Unknown error") if resp else "Connection failed"
                        st.error(f"Failed to create exam: {error_detail}")
    
    # TAB 2: MANAGE EXAMS
    with tab2:
        st.subheader("Existing Exams")
        
        resp = api_get("/admin/exams", headers=auth_headers())
        
        if resp and resp.status_code == 200:
            exams = resp.json()
            
            if not exams:
                st.info("No exams created yet. Create your first exam!")
            else:
                for exam in exams:
                    with st.expander(f"{'✅' if exam['is_active'] else '❌'} {exam['title']} - {exam['language']}"):
                        col1, col2, col3 = st.columns(3)
                        with col1:
                            st.metric("Questions", exam['question_count'])
                        with col2:
                            st.metric("Time", f"{exam['time_allowed_secs'] // 60} min")
                        with col3:
                            status = "Active" if exam['is_active'] else "Inactive"
                            st.metric("Status", status)
                        
                        st.caption(f"Created: {exam['created_at'][:10]}")
                        st.caption(f"Exam ID: {exam['id']}")
                        
                        if st.button(
                            f"{'Deactivate' if exam['is_active'] else 'Activate'} Exam",
                            key=f"toggle_{exam['id']}"
                        ):
                            toggle_resp = api_patch(
                                f"/admin/exams/{exam['id']}/toggle",
                                headers=auth_headers()
                            )
                            if toggle_resp and toggle_resp.status_code == 200:
                                st.success("Status updated!")
                                st.rerun()
        else:
            st.error("Unable to load exams")
    
    # TAB 3: ASSIGN EXAMS
    with tab3:
        st.subheader("Assign Exams to Candidates")
        
        # Get all exams
        resp = api_get("/admin/exams", headers=auth_headers())
        
        if resp and resp.status_code == 200:
            exams = resp.json()
            
            if not exams:
                st.info("Create an exam first before assigning!")
            else:
                exam_options = {f"{e['title']} ({e['language']})": e['id'] for e in exams if e['is_active']}
                
                if not exam_options:
                    st.warning("No active exams available. Activate an exam first!")
                else:
                    with st.form("assign_exam_form"):
                        selected_exam_name = st.selectbox("Select Exam", list(exam_options.keys()))
                        
                        st.write("**Enter candidate emails (one per line):**")
                        emails_text = st.text_area(
                            "Candidate Emails",
                            height=150,
                            placeholder="candidate1@example.com\ncandidate2@example.com\ncandidate3@example.com"
                        )
                        
                        assign_submit = st.form_submit_button("📧 Assign Exam", use_container_width=True)
                        
                        if assign_submit:
                            selected_exam_id = exam_options[selected_exam_name]
                            
                            # Parse emails
                            emails = [e.strip() for e in emails_text.split('\n') if e.strip()]
                            
                            if not emails:
                                st.error("Please enter at least one email address")
                            else:
                                resp = api_post(
                                    f"/admin/exams/{selected_exam_id}/assign",
                                    json={"candidate_emails": emails},
                                    headers=auth_headers()
                                )

                                if resp is None:
                                    st.error("Server not reachable.")
                                elif resp.status_code == 200:
                                    result = resp.json()
                                    st.success("✅ Exam assigned successfully!")
                                else:
                                    try:
                                        error_detail = resp.json().get("detail", "Unknown error")
                                    except:
                                        error_detail = resp.text
                                    st.error(f"Failed to assign exam: {error_detail}")
                
                # Show current assignments
                st.markdown("---")
                st.subheader("Current Assignments")
                
                for exam in exams:
                    if exam['is_active']:
                        with st.expander(f"📋 {exam['title']} - Assignments"):
                            assign_resp = api_get(
                                f"/admin/exams/{exam['id']}/assignments",
                                headers=auth_headers()
                            )
                            
                            if assign_resp and assign_resp.status_code == 200:
                                assignments = assign_resp.json()
                                
                                if not assignments:
                                    st.info("No candidates assigned yet")
                                else:
                                    df = pd.DataFrame(assignments)
                                    df['assigned_at'] = pd.to_datetime(df['assigned_at']).dt.strftime('%Y-%m-%d %H:%M')
                                    st.dataframe(df, use_container_width=True)
        else:
            st.error("Unable to load exams")
    
    # TAB 4: CANDIDATE RESULTS
    with tab4:
        st.subheader("All Candidate Results")
        
        resp = api_get("/admin/candidates/results", headers=auth_headers())
        
        if resp and resp.status_code == 200:
            results = resp.json()
            
            if not results:
                st.info("No exam attempts yet")
            else:
                # Create DataFrame
                df = pd.DataFrame(results)
                
                # Format datetime columns
                df['started_at'] = pd.to_datetime(df['started_at']).dt.strftime('%Y-%m-%d %H:%M')
                df['ended_at'] = pd.to_datetime(df['ended_at'], errors='coerce').dt.strftime('%Y-%m-%d %H:%M')
                
                # Sort by started_at descending
                df = df.sort_values('started_at', ascending=False)
                
                # Add filters
                col1, col2 = st.columns(2)
                with col1:
                    status_filter = st.multiselect(
                        "Filter by Status",
                        options=df['status'].unique(),
                        default=df['status'].unique()
                    )
                with col2:
                    exam_filter = st.multiselect(
                        "Filter by Exam",
                        options=df['exam_title'].unique(),
                        default=df['exam_title'].unique()
                    )
                
                # Apply filters
                filtered_df = df[
                    (df['status'].isin(status_filter)) &
                    (df['exam_title'].isin(exam_filter))
                ]
                
                # Display metrics
                col1, col2, col3, col4 = st.columns(4)
                with col1:
                    st.metric("Total Attempts", len(filtered_df))
                with col2:
                    completed = len(filtered_df[filtered_df['status'] == 'completed'])
                    st.metric("Completed", completed)
                with col3:
                    in_progress = len(filtered_df[filtered_df['status'] == 'in_progress'])
                    st.metric("In Progress", in_progress)
                with col4:
                    if completed > 0:
                        avg_score = filtered_df[filtered_df['status'] == 'completed']['score'].mean()
                        st.metric("Avg Score", f"{avg_score:.1f}%")
                
                st.markdown("---")
                
                # Display table
                display_columns = [
                    'candidate_name', 'candidate_email', 'exam_title', 
                    'exam_language', 'status', 'score', 'started_at', 'ended_at'
                ]
                
                st.dataframe(
                    filtered_df[display_columns],
                    use_container_width=True,
                    hide_index=True
                )
        else:
            st.error("Unable to load candidate results")


def exam_selection_ui():
    st.title("🎓 Available Exams")

    # 🔍 Check unfinished exam
    resumable = get_resumable_exam()

    if resumable:
        st.warning("⚠️ You have an unfinished exam")
        
        # Calculate time remaining
        time_remaining = resumable.get('time_allowed_secs', 0) - resumable.get('time_elapsed', 0)
        minutes_remaining = time_remaining // 60
        
        st.info(f"""
        **Exam Details:**
        - Questions: {len(resumable.get('questions', []))}
        - Time Remaining: {minutes_remaining} minutes
        - Answers Saved: {len(resumable.get('answers', {}))}
        """)

        col1, col2 = st.columns(2)
        
        with col1:
            if st.button("▶️ Resume Exam", type="primary", use_container_width=True):
                elapsed = resumable["time_elapsed"]

                st.session_state.update({
                    "candidate_exam_id": resumable["candidate_exam_id"],
                    "questions": resumable["questions"],
                    "answers": resumable["answers"],
                    "last_saved": resumable["answers"].copy(),
                    "time_original": resumable["time_allowed_secs"],
                    "time_remaining": max(0, resumable["time_allowed_secs"] - elapsed),
                    "exam_started_at": time.time() - elapsed,
                    "status": "in_progress",
                    "page": "exam",
                })

                st.rerun()
        
        with col2:
            if st.button("❌ Abandon Exam", use_container_width=True):
                candidate_exam_id = resumable["candidate_exam_id"]
                headers = auth_headers()
                
                resp = api_post(
                    f"/exam/{candidate_exam_id}/submit",
                    json={"final_time_elapsed": resumable["time_elapsed"]},
                    headers=headers,
                )
                
                if resp and resp.status_code == 200:
                    st.success("Exam submitted")
                    st.rerun()

        st.divider()
        st.caption("⚠️ Please resume or abandon your current exam before starting a new one")
        return

    # -------- NORMAL EXAM LIST --------
    resp = api_get("/exams", headers=auth_headers())

    if not resp or resp.status_code != 200:
        st.error("Unable to load exams")
        return

    exams = resp.json()

    if not exams:
        st.info("No exams assigned to you")
        return

    for exam in exams:
        st.markdown(f"### 📝 {exam['title']}")

        col1, col2, col3 = st.columns(3)
        with col1:
            st.write(f"**Language:** {exam['language']}")
        with col2:
            st.write(f"**Questions:** {exam['question_count']}")
        with col3:
            st.write(f"**Time:** {exam['time_allowed_secs'] // 60} min")

        if st.button("Start Exam", key=f"start_{exam['id']}", use_container_width=True):
            start_exam(exam["id"])

        st.divider()


def start_exam(exam_id):
    headers = auth_headers()

    resp = api_post(f"/exam/{exam_id}/start", headers=headers)
    if not resp or resp.status_code != 200:
        st.error("Unable to start exam")
        return

    candidate_exam_id = resp.json().get("id")

    details = api_get(f"/exam/{candidate_exam_id}", headers=headers)
    if not details or details.status_code != 200:
        st.error("Unable to load exam")
        return

    data = details.json()
    questions = data["questions"]

    st.session_state.update({
        "exam_id": exam_id,
        "candidate_exam_id": candidate_exam_id,
        "questions": questions,
        "answers": {},
        "last_saved": {},
        "time_original": data["time_allowed_secs"],
        "time_remaining": data["time_allowed_secs"],
        "exam_started_at": time.time(),
        "status": "in_progress",
        "submitted": False,
        "page": "exam",
        "current_page": 0,
    })

    st.rerun()


def save_answer(candidate_exam_id, qid, index):
    qid_str = str(qid)
    
    if st.session_state["last_saved"].get(qid_str) == index:
        return True
    
    headers = auth_headers()
    elapsed = st.session_state["time_original"] - st.session_state["time_remaining"]

    payload = {
        "question_id": qid_str,
        "selected_index": index,
        "time_elapsed": elapsed,
    }

    resp = api_post(f"/exam/{candidate_exam_id}/save-answer", json=payload, headers=headers)
    
    if resp and resp.status_code == 200:
        st.session_state["last_saved"][qid_str] = index
        return True
    
    return False

def save_dirty_answers():
    if not st.session_state["dirty_answers"]:
        return True

    candidate_exam_id = st.session_state["candidate_exam_id"]
    headers = auth_headers()

    elapsed = (
        st.session_state["time_original"]
        - st.session_state["time_remaining"]
    )

    payload = [
        {
            "question_id": qid,
            "selected_index": st.session_state["answers"][qid],
            "time_elapsed": elapsed
        }
        for qid in st.session_state["dirty_answers"]
    ]

    resp = api_post(
        f"/exam/{candidate_exam_id}/bulk-save",
        json={"answers": payload},
        headers=headers
    )

    if resp and resp.status_code == 200:
        st.session_state["dirty_answers"].clear()
        return True

    st.error("Auto-save failed. Please try again.")
    return False



    
def submit_exam():
    if st.session_state.get("status") == "completed":
        return

    if st.session_state.get("submitted"):
        return

    # Save remaining dirty answers first
    save_dirty_answers()

    candidate_exam_id = st.session_state["candidate_exam_id"]
    headers = auth_headers()

    elapsed = (
        st.session_state["time_original"]
        - st.session_state["time_remaining"]
    )

    resp = api_post(
        f"/exam/{candidate_exam_id}/submit",
        json={"final_time_elapsed": elapsed},
        headers=headers,
    )

    if not resp or resp.status_code != 200:
        st.error("Unable to submit exam. Please try again.")
        return

    st.session_state["submitted"] = True
    st.session_state["status"] = "completed"
    st.session_state["page"] = "results"

def exam_ui():
    # Safety guard for session keys
    if "dirty_answers" not in st.session_state:
        st.session_state["dirty_answers"] = set()

    if "answers" not in st.session_state:
        st.session_state["answers"] = {}

    candidate_exam_id = st.session_state["candidate_exam_id"]
    questions = st.session_state["questions"]

    if not st.session_state.get("exam_started_at"):
        return

    # ---------------- TIMER CALCULATION ----------------
    elapsed = int(time.time() - st.session_state["exam_started_at"])
    remaining = max(0, st.session_state["time_original"] - elapsed)

    st.session_state["time_remaining"] = remaining

    # ---------------- PAGINATION SETTINGS ----------------
    QUESTIONS_PER_PAGE = 10

    if "current_page" not in st.session_state:
        st.session_state["current_page"] = 0

    total_pages = (len(questions) - 1) // QUESTIONS_PER_PAGE + 1
    current_page = st.session_state["current_page"]
    if current_page >= total_pages:
        current_page = total_pages - 1
        st.session_state["current_page"] = current_page

    if current_page < 0:
        current_page = 0
        st.session_state["current_page"] = 0

    start_index = current_page * QUESTIONS_PER_PAGE
    end_index = min(start_index + QUESTIONS_PER_PAGE, len(questions))

    left, right = st.columns([1, 4])


    # ---------------- LEFT PANEL ----------------
    with left:
        total_seconds = remaining

        components.html(
            f"""
            <div id="timer" style="
                font-size:28px;
                font-weight:700;
                padding:15px;
                border-radius:8px;
                background-color:#eef2ff;
                text-align:center;
            ">
            </div>

            <script>
            var timeLeft = {total_seconds};

            function updateTimer() {{
                var minutes = Math.floor(timeLeft / 60);
                var seconds = timeLeft % 60;

                var formatted =
                    String(minutes).padStart(2,'0') + ":" +
                    String(seconds).padStart(2,'0');

                var timerDiv = document.getElementById("timer");
                timerDiv.innerHTML = "⏰ " + formatted;

                if (timeLeft <= 60) {{
                    timerDiv.style.backgroundColor = "#fee2e2";
                    timerDiv.style.color = "#b91c1c";
                }}

                if (timeLeft <= 0) {{
                    clearInterval(interval);
                    window.parent.postMessage({{type: "time_up"}}, "*");
                }}

                timeLeft--;
            }}

            updateTimer();
            var interval = setInterval(updateTimer, 1000);
            </script>
            """,
            height=110,
        )

        answered_count = len(st.session_state["answers"])

        st.progress(answered_count / len(questions))
        st.caption(f"{answered_count} of {len(questions)} answered")
        st.caption(f"Page {current_page + 1} of {total_pages}")

    # ---------------- RIGHT PANEL ----------------
    with right:
        st.header("Exam Questions")

        for i in range(start_index, end_index):
            q = questions[i]
            qid = str(q["id"])
            current_idx = st.session_state["answers"].get(qid)

            st.markdown(f"### Question {i + 1}")
            st.write(q["text"])

            selected_idx = None  # Always initialize

            selected = st.radio(
                "Select your answer:",
                q["choices"],
                index=current_idx if current_idx is not None else None,
                key=f"radio_{qid}",
                label_visibility="collapsed"
            )

            if selected is not None:
                selected_idx = q["choices"].index(selected)

                previous = st.session_state["answers"].get(qid)

                if previous != selected_idx:
                    st.session_state["answers"][qid] = selected_idx
                    st.session_state["dirty_answers"].add(qid)

            st.divider()

        col1, col2, col3 = st.columns([2, 2, 1])

        with col1:
            if st.button("⬅ Previous Page", disabled=current_page == 0):
                if save_dirty_answers():
                    st.session_state["current_page"] -= 1
                    st.rerun()

        with col2:
            if st.button("Next Page ➡", disabled=current_page == total_pages - 1):
                if save_dirty_answers():
                    st.session_state["current_page"] += 1
                    st.rerun()

        with col3:
            if st.button("Submit Exam", type="primary"):
                submit_exam()

    # ---------------- AUTO SUBMIT ----------------
    if (
        remaining <= 0
        and st.session_state.get("status") == "in_progress"
    ):
        submit_exam()
        st.rerun()

    # ---------------- LISTEN FOR JS EVENT ----------------
    components.html(
        """
        <script>
        window.addEventListener("message", (event) => {
            if (event.data.type === "time_up") {
                window.parent.postMessage({type: "streamlit_rerun"}, "*");
            }
        });
        </script>
        """,
        height=0,
    )




def results_ui():
    show_brand_header()
    st.title("📊 Your Exam Results")
    
    candidate_exam_id = st.session_state["candidate_exam_id"]
    headers = auth_headers()
    
    res = api_get(f"/exam/{candidate_exam_id}/result", headers=headers)
    if res and res.status_code == 200:
        result_data = res.json()
        
        col1, col2, col3 = st.columns([1, 2, 1])
        with col2:
            if 'score' in result_data:
                score = result_data['score']
                if score >= 70:
                    st.success(f"## 🎉 Congratulations!")
                    st.metric("Your Score", f"{score}%", "Pass")
                    st.balloons()
                elif score >= 50:
                    st.warning(f"## 📈 Good Effort!")
                    st.metric("Your Score", f"{score}%")
                else:
                    st.error(f"## 📚 Keep Learning!")
                    st.metric("Your Score", f"{score}%")
        
        st.markdown("---")
        
        st.subheader("Question Review")
        
        for idx, detail in enumerate(result_data.get('details', []), start=1):
            is_correct = detail.get('is_correct')
            
            with st.expander(
                f"{'✅' if is_correct else '❌'} Question {idx}: {detail.get('question')[:50]}...",
                expanded=not is_correct
            ):
                st.write(f"**Question:** {detail.get('question')}")
                
                choices = detail.get('choices', [])
                selected_val = detail.get('selected')
                correct_val = detail.get('correct_index')
                
                col1, col2 = st.columns(2)
                
                with col1:
                    st.write("**Your Answer:**")
                    if selected_val is not None and 0 <= selected_val < len(choices):
                        if is_correct:
                            st.success(choices[selected_val])
                        else:
                            st.error(choices[selected_val])
                    else:
                        st.warning("No answer provided")
                
                with col2:
                    st.write("**Correct Answer:**")
                    if correct_val is not None and 0 <= correct_val < len(choices):
                        st.success(choices[correct_val])
        
        st.markdown("---")
        col1, col2, col3 = st.columns([1, 2, 1])
        with col2:
            if st.button("🔄 Take Another Exam", type="primary", use_container_width=True):
                st.session_state["exam_id"] = None
                st.session_state["candidate_exam_id"] = None
                st.session_state["questions"] = None
                st.session_state["answers"] = {}
                st.session_state["last_saved"] = {}
                st.session_state["status"] = None
                st.session_state["time_remaining"] = 0
                st.session_state["submitted"] = False
                st.session_state["page"] = "home"
                st.session_state["auto_resume_checked"] = False  # Reset for next exam
                st.rerun()
    else:
        st.error("Unable to load results. Please try again.")

def change_password_ui():
    show_brand_header()
    st.subheader("🔑 Change Your Password")

    with st.form("change_password_form"):
        old_password = st.text_input("Current Password", type="password")
        new_password = st.text_input("New Password", type="password")
        confirm_password = st.text_input("Confirm New Password", type="password")

        submitted = st.form_submit_button("Update Password", use_container_width=True)

        if submitted:
            if not old_password or not new_password:
                st.error("All fields are required")
                return

            if new_password != confirm_password:
                st.error("New passwords do not match")
                return

            email = st.session_state.get("user_email")

            try:
                # 🔐 Step 1: Verify current password by attempting login
                cognito.admin_initiate_auth(
                    UserPoolId=os.getenv("COGNITO_USER_POOL_ID"),
                    ClientId=COGNITO_CLIENT_ID,
                    AuthFlow="ADMIN_USER_PASSWORD_AUTH",
                    AuthParameters={
                        "USERNAME": email,
                        "PASSWORD": old_password
                    }
                )

                # 🔄 Step 2: If login successful, set new password
                cognito.admin_set_user_password(
                    UserPoolId=os.getenv("COGNITO_USER_POOL_ID"),
                    Username=email,
                    Password=new_password,
                    Permanent=True
                )

                st.success("✅ Password changed successfully!")
                st.info("Please login again with your new password.")

                # Logout user
                st.session_state.clear()
                init_session()
                st.rerun()

            except cognito.exceptions.NotAuthorizedException:
                st.error("Current password is incorrect")

            except cognito.exceptions.InvalidPasswordException:
                st.error("Password does not meet Cognito requirements")

            except Exception as e:
                st.error(f"Error: {str(e)}")


def forgot_password_ui():
    show_brand_header()
    st.subheader("🔐 Reset Your Password")

    with st.form("forgot_password_form"):
        email = st.text_input("Enter your registered email")

        submitted = st.form_submit_button("Send Verification Code", use_container_width=True)

        if submitted:
            if not email:
                st.error("Email is required")
                return

            try:
                cognito.forgot_password(
                    ClientId=COGNITO_CLIENT_ID,
                    Username=email
                )

                st.success("📩 Verification code sent to your email")
                st.session_state["reset_email"] = email
                st.session_state["page"] = "confirm_reset"
                st.rerun()

            except Exception as e:
                st.error("Error sending verification code. Check email.")
    
    if st.button("⬅ Back to Login", use_container_width=True):
        st.session_state["page"] = "login"
        st.rerun()
def confirm_reset_ui():
    show_brand_header()
    st.subheader("🔢 Enter Verification Code")

    email = st.session_state.get("reset_email")

    st.write(f"Code sent to: **{email}**")

    with st.form("confirm_reset_form"):
        code = st.text_input("Verification Code")
        new_password = st.text_input("New Password", type="password")
        confirm_password = st.text_input("Confirm New Password", type="password")

        submitted = st.form_submit_button("Reset Password", use_container_width=True)

        if submitted:
            if not code or not new_password:
                st.error("All fields are required")
                return

            if new_password != confirm_password:
                st.error("Passwords do not match")
                return

            try:
                cognito.confirm_forgot_password(
                    ClientId=COGNITO_CLIENT_ID,
                    Username=email,
                    ConfirmationCode=code,
                    Password=new_password
                )

                st.success("✅ Password reset successfully!")
                st.session_state["page"] = "login"
                st.rerun()

            except Exception as e:
                st.error("Invalid code or password does not meet requirements")

    if st.button("⬅ Back to Login", use_container_width=True):
        st.session_state["page"] = "login"
        st.rerun()






def main():
    if not st.session_state["access_token"]:
        page = st.session_state.get("page")

        if page == "register":
            register_ui()
        elif page == "verify":
            verify_ui()
        elif page == "forgot_password":
            forgot_password_ui()
        elif page == "confirm_reset":
            confirm_reset_ui()
        else:
            login_ui()
        return




    # ✅ AUTO-RESUME: Check and restore exam state after refresh
    auto_resume_exam_if_needed()

    # -------- SIDEBAR --------
    st.sidebar.image("frontend/nmk_logo.png", width=160)
    st.sidebar.title("NMK Portal")
    st.sidebar.write(f"**User:** {st.session_state['user_email']}")
    st.sidebar.divider()

    if st.session_state["is_admin"]:
        page = st.sidebar.radio(
            "Navigation",
            ["Admin Dashboard", "Change Password"]
        )
    else:
        page = st.sidebar.radio(
            "Navigation",
            [ "Change Password"]
        )

    
    if page == "Admin Dashboard":
        st.session_state["page"] = "admin_dashboard"
    elif page == "Change Password":
        st.session_state["page"] = "change_password"

   
    if st.sidebar.button("🚪 Logout", use_container_width=True):
        st.session_state.clear()
        init_session()
        st.rerun()

    # -------- SINGLE PAGE RENDER --------
    if st.session_state.get("status") == "in_progress":
        exam_ui()
        return

    if st.session_state.get("status") == "completed":
        results_ui()
        return

    if st.session_state.get("page") == "admin_dashboard" and st.session_state["is_admin"]:
        admin_dashboard()
        return
    if st.session_state.get("page") == "change_password":
        change_password_ui()
        return


    exam_selection_ui()


if __name__ == "__main__":
    main()
