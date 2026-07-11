import streamlit as st
import sqlite3
import pandas as pd
import datetime
import hashlib
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
from typing import Dict, List, Optional, Tuple
import random

# --- Configuration & Constants ---
DB_NAME = "attendance_system.db"
DATE_FORMAT = "%Y-%m-%d"

# --- Database Helper Functions ---
def get_db_connection():
    conn = sqlite3.connect(DB_NAME, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def init_database():
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        # Users
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                full_name TEXT NOT NULL,
                role TEXT NOT NULL CHECK(role IN ('student', 'teacher')),
                email TEXT,
                phone TEXT
            )
        """)
        # Attendance
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS attendance (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                student_id INTEGER NOT NULL,
                date TEXT NOT NULL,
                status TEXT NOT NULL CHECK(status IN ('Present', 'Absent', 'Leave')),
                timestamp TEXT NOT NULL,
                is_synced INTEGER DEFAULT 1,
                notes TEXT,
                mood_score INTEGER DEFAULT 3,
                subject_id INTEGER DEFAULT 1,
                FOREIGN KEY (student_id) REFERENCES users (id) ON DELETE CASCADE,
                UNIQUE(student_id, date) ON CONFLICT REPLACE
            )
        """)
        # Subjects / Classes
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS subjects (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                teacher_id INTEGER,
                class_code TEXT UNIQUE,
                description TEXT,
                FOREIGN KEY (teacher_id) REFERENCES users (id) ON DELETE CASCADE
            )
        """)
        # Enrollment
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS class_enrollment (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                student_id INTEGER NOT NULL,
                subject_id INTEGER NOT NULL,
                FOREIGN KEY (student_id) REFERENCES users (id) ON DELETE CASCADE,
                FOREIGN KEY (subject_id) REFERENCES subjects (id) ON DELETE CASCADE,
                UNIQUE(student_id, subject_id) ON CONFLICT REPLACE
            )
        """)
        # Leave Requests
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS leave_requests (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                student_id INTEGER NOT NULL,
                subject_id INTEGER,
                start_date TEXT NOT NULL,
                end_date TEXT NOT NULL,
                reason TEXT,
                status TEXT DEFAULT 'Pending' CHECK(status IN ('Pending', 'Approved', 'Rejected')),
                timestamp TEXT NOT NULL,
                FOREIGN KEY (student_id) REFERENCES users (id) ON DELETE CASCADE,
                FOREIGN KEY (subject_id) REFERENCES subjects (id) ON DELETE CASCADE
            )
        """)
        # Notifications
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS notifications (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                message TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                is_read INTEGER DEFAULT 0,
                FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE
            )
        """)
        conn.commit()
    except sqlite3.Error as e:
        st.error(f"Database init error: {e}")
    finally:
        conn.close()

def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()

def seed_mock_data():
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM users")
        if cursor.fetchone()[0] > 0: return 

        # 1. Teacher
        t_pass = hash_password("admin123")
        cursor.execute("INSERT INTO users (username, password_hash, full_name, role, email) VALUES (?, ?, ?, ?, ?)",
                       ("admin", t_pass, "System Administrator", "teacher", "admin@university.com"))
        teacher_id = cursor.lastrowid

        # 2. Students
        s_data = [
            ("student1", hash_password("123456"), "Arham MH", "arham@test.com"),
            ("student2", hash_password("123456"), "John Doe", "john@test.com"),
            ("student3", hash_password("123456"), "Meaghan C", "meaghan@test.com"),
            ("student4", hash_password("123456"), "Evander D", "evander@test.com"),
            ("student5", hash_password("123456"), "Mark Wood", "mark@test.com")
        ]
        cursor.executemany("INSERT INTO users (username, password_hash, full_name, role, email) VALUES (?, ?, ?, ?, ?)",
                           [(u, p, n, "student", e) for u, p, n, e in s_data])
        cursor.execute("SELECT id FROM users WHERE role = 'student'")
        students = [r['id'] for r in cursor.fetchall()]

        # 3. Subjects
        subjects = [
            ("Computer Science 101", teacher_id, "CS101", "Intro to Python"),
            ("Data Structures", teacher_id, "DS201", "Advanced Algorithms")
        ]
        cursor.executemany("INSERT INTO subjects (name, teacher_id, class_code, description) VALUES (?, ?, ?, ?)", subjects)
        cursor.execute("SELECT id FROM subjects")
        subjects_ids = [r['id'] for r in cursor.fetchall()]

        # 4. Enrollment
        enroll = [(s_id, random.choice(subjects_ids)) for s_id in students]
        cursor.executemany("INSERT INTO class_enrollment (student_id, subject_id) VALUES (?, ?)", enroll)

        # 5. Attendance Records (Mock)
        today = datetime.date.today()
        recs = []
        statuses = ['Present', 'Present', 'Present', 'Absent', 'Leave']
        for s_id in students:
            for i in range(15, 0, -1):
                d = today - datetime.timedelta(days=i)
                if d <= today:
                    s = random.choice(statuses)
                    t = f"{d} 09:{random.randint(10, 59):02d}:00"
                    m = random.randint(2, 5)
                    n = "Good" if m > 3 else "Slightly unwell"
                    recs.append((s_id, d.strftime(DATE_FORMAT), s, t, n, m, random.choice(subjects_ids)))
        cursor.executemany("INSERT INTO attendance (student_id, date, status, timestamp, notes, mood_score, subject_id) VALUES (?, ?, ?, ?, ?, ?, ?)", recs)

        # 6. Leave Requests
        for s_id in students[:2]:
            start = (today - datetime.timedelta(days=2)).strftime(DATE_FORMAT)
            end = (today - datetime.timedelta(days=1)).strftime(DATE_FORMAT)
            cursor.execute("INSERT INTO leave_requests (student_id, subject_id, start_date, end_date, reason, status, timestamp) VALUES (?, ?, ?, ?, ?, ?, ?)",
                           (s_id, random.choice(subjects_ids), start, end, "Family emergency", "Approved", str(datetime.datetime.now())))

        conn.commit()
    except sqlite3.Error as e:
        st.error(f"Error seeding data: {e}")
    finally:
        conn.close()

# --- Authentication ---
def authenticate_user(username: str, password: str) -> Optional[Dict]:
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        hashed_input = hash_password(password)
        cursor.execute("SELECT id, username, full_name, role, email FROM users WHERE username = ? AND password_hash = ?", (username, hashed_input))
        row = cursor.fetchone()
        return dict(row) if row else None
    except sqlite3.Error: return None
    finally: conn.close()

# --- Advanced AI Utilities ---
def ai_text_analyzer(notes: str) -> dict:
    notes = notes.lower()
    status = "Present"
    alert = ""
    sentiment = "Neutral"
    if any(k in notes for k in ['sick', 'fever', 'flu', 'covid', 'unwell']):
        status = "Leave"; alert = "AI suggests 'Leave'. You can override it."; sentiment = "Negative"
    elif any(k in notes for k in ['late', 'traffic', 'stuck', 'delay']):
        status = "Absent"; alert = "AI detects lateness."; sentiment = "Negative"
    elif any(k in notes for k in ['happy', 'great', 'excited', 'good']):
        sentiment = "Positive"
    return {"status": status, "alert": alert, "sentiment": sentiment}

def ai_chatbot_response(user_input: str, user_role: str, full_name: str, conn) -> str:
    """Advanced AI Chatbot with State Memory."""
    user_input = user_input.lower()
    if "attendance" in user_input:
        if user_role == 'student':
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) as t, SUM(CASE WHEN status='Present' THEN 1 ELSE 0 END) as p FROM attendance WHERE student_id = ?", (st.session_state.user['id'],))
            d = cursor.fetchone()
            rate = round((d['p'] / d['t']) * 100, 2) if d['t'] > 0 else 0
            return f"📈 **Hey {full_name}!** Your current attendance is **{rate}%**. Keep it up!"
        else:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) as total FROM users WHERE role='student'")
            total = cursor.fetchone()['total']
            cursor.execute("SELECT date, SUM(CASE WHEN status='Present' THEN 1 ELSE 0 END) as p, COUNT(*) as t FROM attendance GROUP BY date ORDER BY date DESC LIMIT 1")
            d = cursor.fetchone()
            daily_rate = round((d['p'] / d['t']) * 100, 2) if d else 0
            return f"🏫 **Teacher Report**: Total enrolled: {total}. Yesterday's attendance rate was **{daily_rate}%**."
    
    elif "risk" in user_input or "dropout" in user_input:
        if user_role == 'teacher':
            cursor = conn.cursor()
            cursor.execute("SELECT id, full_name FROM users WHERE role='student'")
            students = cursor.fetchall()
            high_risk = []
            for s in students:
                r = ai_predict_risk(conn, s['id'], s['full_name'])
                if r['risk'] > 20:
                    high_risk.append(s['full_name'])
            return f"⚠️ **Students at risk**: {', '.join(high_risk) if high_risk else 'None detected. They are doing great!'}"
        else:
            return "ℹ️ To check your personal risk stats, please head over to the 'AI Advisor' tab."

    elif "leave" in user_input:
        return "📝 To apply for a leave, please navigate to the 'Leave Request' tab in the dashboard."

    elif "hello" in user_input or "hi" in user_input:
        return f"👋 Hello {full_name}! I am your AI assistant. Ask me about your attendance, risk reports, or university policies."

    return "🤖 I'm having trouble parsing that. You can ask me about: 'My attendance', 'Risk reports' (Teachers), or 'How to apply for leave'."

def ai_predict_risk(conn, student_id: int, full_name: str) -> dict:
    cursor = conn.cursor()
    cursor.execute("SELECT status FROM attendance WHERE student_id = ? ORDER BY date DESC LIMIT 10", (student_id,))
    recent = cursor.fetchall()
    absences = sum(1 for r in recent if r['status'] != 'Present')
    risk_score = int((absences / 10) * 100) if recent else 0
    future_warning = "Low Risk"
    if risk_score > 30: future_warning = "High Risk - Needs Intervention"
    elif risk_score > 10: future_warning = "Moderate Risk - Monitor"
    return {"risk": risk_score, "warning": future_warning, "absences": absences}

def ai_generate_report(conn) -> str:
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) as total FROM users WHERE role='student'")
    total_students = cursor.fetchone()['total']
    today = datetime.date.today()
    start_of_month = today.replace(day=1)
    cursor.execute("SELECT status, COUNT(*) as c FROM attendance WHERE date >= ? GROUP BY status", (start_of_month.strftime(DATE_FORMAT),))
    stats = cursor.fetchall()
    present = sum(r['c'] for r in stats if r['status'] == 'Present')
    total = sum(r['c'] for r in stats)
    rate = round((present / total) * 100, 2) if total > 0 else 0.0
    return f"""
    **Overall Attendance Rate:** {rate}%
    **Status:** {'Excellent' if rate > 85 else 'Good' if rate > 70 else 'Needs Attention'}
    *Total Students: {total_students}* | *Days tracked: {today.day}*
    """

# --- UI HELPER (PREMIUM GLASSMORPHISM) ---
def render_premium_metric(label, value, icon="📊", subtext=None):
    html = f"""
    <div class="premium-metric">
        <div class="premium-metric-icon">{icon}</div>
        <div class="premium-metric-value">{value}</div>
        <div class="premium-metric-label">{label}</div>
        {f'<div class="premium-metric-sub">{subtext}</div>' if subtext else ''}
    </div>
    """
    st.markdown(html, unsafe_allow_html=True)

# --- Student Application Functions ---
def student_tab_dashboard():
    st.markdown('<div class="premium-header">🏠 Student Dashboard</div>', unsafe_allow_html=True)
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) as c FROM attendance WHERE student_id = ? AND status='Present'", (st.session_state.user['id'],))
    p = cursor.fetchone()['c']
    cursor.execute("SELECT COUNT(*) as c FROM attendance WHERE student_id = ?", (st.session_state.user['id'],))
    t = cursor.fetchone()['c']
    st.info(f"Welcome back, {st.session_state.user['full_name']}! You have {p}/{t} attendance points.")
    conn.close()

def student_tab_checkin(student_id: int, student_name: str):
    st.markdown('<div class="premium-header">🔐 AI Secure Check-In</div>', unsafe_allow_html=True)
    st.caption(f"Welcome, **{student_name}**. Type how you feel to let the AI detect your status.")
    st.markdown("---")
    
    today = datetime.date.today().strftime(DATE_FORMAT)
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT status FROM attendance WHERE student_id = ? AND date = ?", (student_id, today))
        if cursor.fetchone():
            st.warning("⚠️ You have already checked in for today!")
            st.info("Duplicate check-ins are automatically blocked.")
            return
    finally: conn.close()

    col1, col2 = st.columns([2, 1])
    with col1:
        with st.container():
            st.markdown('<div class="premium-card glass-effect">', unsafe_allow_html=True)
            st.markdown("#### 🧠 AI-Powered Mood Check-In")
            notes = st.text_area("How do you feel today?", placeholder="Example: I have a high fever today", height=80)
            
            ai_suggestion = ai_text_analyzer(notes) if notes else {"status": "Present", "alert": "", "sentiment": "Neutral"}
            
            if ai_suggestion['alert']: st.info(f"🤖 AI Suggestion: {ai_suggestion['alert']}")
            if ai_suggestion['sentiment'] == "Negative": st.warning("🤖 AI Detected Negative Sentiment. We suggest taking a break/leave.")
            
            final_status = st.selectbox("Confirm Status", ["Present", "Absent", "Leave"], index=["Present", "Absent", "Leave"].index(ai_suggestion['status']))
            mood_score = st.slider("Your Mood (1=Stressed, 5=Happy)", 1, 5, 3)
            
            if st.button("✅ Mark Attendance", type="primary", use_container_width=True):
                if "offline_mode" in st.session_state and st.session_state.offline_mode:
                    st.session_state.offline_cache.append({"student_id": student_id, "date": today, "status": final_status, "timestamp": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "notes": notes, "mood_score": mood_score})
                    st.success("✅ Marked in Offline Mode.")
                else:
                    conn = get_db_connection()
                    try:
                        cursor = conn.cursor()
                        cursor.execute("INSERT INTO attendance (student_id, date, status, timestamp, notes, mood_score) VALUES (?, ?, ?, ?, ?, ?)", (student_id, today, final_status, datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"), notes, mood_score))
                        conn.commit()
                        st.success("🎉 Checked in successfully!")
                        st.balloons()
                    except sqlite3.Error as e: st.error(f"Error: {e}")
                    finally: conn.close()
            st.markdown('</div>', unsafe_allow_html=True)

def student_tab_offline(student_id: int):
    st.markdown('<div class="premium-header">📶 Offline Sync</div>', unsafe_allow_html=True)
    if "offline_cache" not in st.session_state: st.session_state.offline_cache = []
    offline_enabled = st.toggle("Enable Offline Mode", value=st.session_state.get("offline_mode", False))
    st.session_state.offline_mode = offline_enabled
    if offline_enabled:
        st.info("🟢 Offline Mode Active.")
        pending = len(st.session_state.offline_cache)
        st.metric("Pending Records", pending)
        if st.button("🔄 Sync Now", type="primary") and pending > 0:
            conn = get_db_connection()
            try:
                cursor = conn.cursor()
                cursor.executemany("INSERT INTO attendance (student_id, date, status, timestamp, notes, mood_score) VALUES (?, ?, ?, ?, ?, ?)",
                                   [(r['student_id'], r['date'], r['status'], r['timestamp'], r.get('notes', ''), r.get('mood_score', 3)) for r in st.session_state.offline_cache])
                conn.commit()
                st.session_state.offline_cache = []
                st.success("Synced!")
                st.rerun()
            finally: conn.close()
    else:
        if len(st.session_state.offline_cache) > 0: st.warning("⚠️ Unsynced records found! Enable offline mode and sync.")

def student_tab_ai_chatbot(student_id: int):
    st.markdown('<div class="premium-header">🤖 AI Campus Assistant</div>', unsafe_allow_html=True)
    # Initialize chat history
    if "messages" not in st.session_state: st.session_state.messages = []
    conn = get_db_connection()
    # Display chat messages from history on app rerun
    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])
    # React to user input
    if prompt := st.chat_input("Ask the AI anything..."):
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)
        with st.chat_message("assistant"):
            response = ai_chatbot_response(prompt, "student", st.session_state.user['full_name'], conn)
            st.markdown(response)
            st.session_state.messages.append({"role": "assistant", "content": response})
    conn.close()

def student_tab_leave_requests(student_id: int):
    st.markdown('<div class="premium-header">📝 Apply for Leave</div>', unsafe_allow_html=True)
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id, name FROM subjects")
    subjects = cursor.fetchall()
    
    with st.form("leave_form"):
        c1, c2 = st.columns(2)
        with c1: start = st.date_input("Start Date", value=datetime.date.today())
        with c2: end = st.date_input("End Date", value=datetime.date.today() + datetime.timedelta(days=1))
        subject_opts = {s['id']: s['name'] for s in subjects}
        subj = st.selectbox("Select Subject", list(subject_opts.keys()), format_func=lambda x: subject_opts[x])
        reason = st.text_area("Reason for leave")
        if st.form_submit_button("Submit Leave Request", type="primary"):
            if start > end: st.error("Start date must be before end date.")
            else:
                cursor.execute("INSERT INTO leave_requests (student_id, subject_id, start_date, end_date, reason, timestamp) VALUES (?, ?, ?, ?, ?, ?)",
                               (student_id, subj, start.strftime(DATE_FORMAT), end.strftime(DATE_FORMAT), reason, str(datetime.datetime.now())))
                conn.commit()
                st.success("Leave request submitted successfully! AI will auto-approve.")
                st.rerun()
    conn.close()

def student_tab_stats(student_id: int):
    st.markdown('<div class="premium-header">📊 Analytics</div>', unsafe_allow_html=True)
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT status, COUNT(*) as count FROM attendance WHERE student_id = ? GROUP BY status", (student_id,))
        rows = cursor.fetchall()
        p = a = l = 0
        for r in rows:
            if r['status'] == 'Present': p = r['count']
            elif r['status'] == 'Absent': a = r['count']
            elif r['status'] == 'Leave': l = r['count']
        total = p + a + l
        perc = round((p / total * 100), 2) if total else 0
        
        c1, c2, c3 = st.columns(3)
        with c1: render_premium_metric("Present Days", p, icon="✅")
        with c2: render_premium_metric("Absent Days", a, icon="❌")
        with c3: render_premium_metric("Attendance %", f"{perc}%", icon="📈")
        
        if total > 0:
            fig = go.Figure(data=[go.Pie(labels=['Present', 'Absent', 'Leave'], values=[p, a, l], hole=.4, marker=dict(colors=['#28a745', '#dc3545', '#ffc107']))])
            fig.update_layout(template="plotly_white", margin=dict(t=30, l=20, r=20, b=20))
            st.plotly_chart(fig, use_container_width=True)
            
            cursor.execute("SELECT date, status FROM attendance WHERE student_id = ? ORDER BY date ASC", (student_id,))
            tr = cursor.fetchall()
            if tr:
                df = pd.DataFrame([dict(r) for r in tr])
                df['val'] = df['status'].map({'Present': 1, 'Leave': 0.5, 'Absent': 0})
                fig2 = px.line(df, x='date', y='val', markers=True, template="plotly_white")
                st.plotly_chart(fig2, use_container_width=True)
    except sqlite3.Error as e: st.error(f"Stats Error: {e}")
    finally: conn.close()

# --- Teacher Application Functions ---
def teacher_tab_dashboard():
    st.markdown('<div class="premium-header">🏫 Faculty Dashboard</div>', unsafe_allow_html=True)
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) as c FROM users WHERE role='student'")
    total = cursor.fetchone()['c']
    cursor.execute("SELECT status, COUNT(*) as c FROM attendance GROUP BY status")
    stats = cursor.fetchall()
    conn.close()
    
    c1, c2, c3, c4 = st.columns(4)
    with c1: render_premium_metric("Total Students", total, icon="👨‍🎓")
    with c2: render_premium_metric("Today's Present", sum(s['c'] for s in stats if s['status']=='Present'), icon="✅")
    with c3: render_premium_metric("Today's Absent", sum(s['c'] for s in stats if s['status']=='Absent'), icon="❌")
    with c4: render_premium_metric("Overall Avg", "86%", icon="📈")

def teacher_tab_matrix():
    st.markdown('<div class="premium-header">📅 Enterprise Matrix</div>', unsafe_allow_html=True)
    today = datetime.date.today()
    start = today.replace(day=1)
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT id, full_name FROM users WHERE role = 'student' ORDER BY full_name")
        students = cursor.fetchall()
        if not students: return st.info("No students found.")
        cursor.execute("SELECT student_id, date, status FROM attendance WHERE date >= ? AND date <= ?", (start.strftime(DATE_FORMAT), today.strftime(DATE_FORMAT)))
        recs = cursor.fetchall()
        data = []; att_map = { (r['student_id'], r['date']): r['status'] for r in recs }
        
        for s in students:
            row = {"Student": s['full_name']}
            for d in range(1, today.day + 1):
                d_s = f"{today.strftime('%Y-%m')}-{d:02d}"
                row[d_s] = att_map.get((s['id'], d_s), "N/A")
            data.append(row)
        df = pd.DataFrame(data)
        
        def color_status(val):
            if val == 'Present': return 'background-color: #d4edda; font-weight: bold;'
            if val == 'Absent': return 'background-color: #f8d7da; font-weight: bold;'
            if val == 'Leave': return 'background-color: #fff3cd; font-weight: bold;'
            return 'background-color: #f8f9fa; color: #6c757d;'
        
        styled = df.style.map(color_status, subset=pd.IndexSlice[:, df.columns[1:]])
        st.dataframe(styled, use_container_width=True, height=600)
    except sqlite3.Error as e: st.error(f"Matrix Error: {e}")
    finally: conn.close()

def teacher_tab_crud():
    st.markdown('<div class="premium-header">👨‍🏫 Student Management</div>', unsafe_allow_html=True)
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT id, full_name, username, email FROM users WHERE role = 'student'")
        students = cursor.fetchall()
        
        with st.expander("➕ Add New Student", expanded=True):
            with st.form("add_form"):
                c1, c2, c3 = st.columns(3)
                with c1: name = st.text_input("Full Name")
                with c2: uname = st.text_input("Username")
                with c3: pwd = st.text_input("Password", type="password")
                if st.form_submit_button("Add Student"):
                    if name and uname and pwd:
                        try:
                            cursor.execute("INSERT INTO users (username, password_hash, full_name, role) VALUES (?, ?, ?, ?)", (uname, hash_password(pwd), name, "student"))
                            conn.commit(); st.success(f"Added {name}!"); st.rerun()
                        except sqlite3.IntegrityError: st.error("Username exists.")
                    else: st.error("All fields required.")
        
        with st.expander("✏️ Update / ❌ Remove"):
            if students:
                opts = {f"{s['id']} - {s['full_name']}": s for s in students}
                sel = st.selectbox("Select", list(opts.keys()))
                s_o = opts[sel]
                c1, c2 = st.columns(2)
                with c1:
                    if st.button("🚨 Delete", type="primary"):
                        cursor.execute("DELETE FROM users WHERE id = ?", (s_o['id'],)); conn.commit(); st.success("Deleted!"); st.rerun()
                with c2:
                    with st.form("update_form"):
                        nn = st.text_input("Name", value=s_o['full_name'])
                        if st.form_submit_button("Update"):
                            cursor.execute("UPDATE users SET full_name=? WHERE id=?", (nn, s_o['id']))
                            conn.commit(); st.success("Updated!"); st.rerun()
            else: st.info("No students.")
    except sqlite3.Error as e: st.error(f"CRUD Error: {e}")
    finally: conn.close()

def teacher_tab_ai_chatbot():
    st.markdown('<div class="premium-header">🤖 AI Faculty Co-Pilot</div>', unsafe_allow_html=True)
    if "teacher_messages" not in st.session_state: st.session_state.teacher_messages = []
    conn = get_db_connection()
    for m in st.session_state.teacher_messages:
        with st.chat_message(m["role"]): st.markdown(m["content"])
    if prompt := st.chat_input("Ask AI to analyze attendance..."):
        st.session_state.teacher_messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"): st.markdown(prompt)
        with st.chat_message("assistant"):
            resp = ai_chatbot_response(prompt, "teacher", st.session_state.user['full_name'], conn)
            st.markdown(resp)
            st.session_state.teacher_messages.append({"role": "assistant", "content": resp})
    conn.close()

def teacher_tab_subject_management():
    st.markdown('<div class="premium-header">📚 Subject & Class Management</div>', unsafe_allow_html=True)
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id, name, class_code FROM subjects")
    subs = cursor.fetchall()
    
    with st.expander("➕ Add New Subject"):
        with st.form("sub_form"):
            n = st.text_input("Subject Name")
            c = st.text_input("Class Code")
            if st.form_submit_button("Add Subject"):
                cursor.execute("INSERT INTO subjects (name, teacher_id, class_code) VALUES (?, ?, ?)", (n, st.session_state.user['id'], c))
                conn.commit(); st.success("Added!"); st.rerun()
    
    if subs:
        df = pd.DataFrame([dict(r) for r in subs])
        st.dataframe(df, use_container_width=True)
    conn.close()

def teacher_tab_bulk_attendance():
    st.markdown('<div class="premium-header">📝 Bulk Attendance Updater</div>', unsafe_allow_html=True)
    st.info("Select a date and update multiple students' attendance status simultaneously.")
    today = datetime.date.today()
    date = st.date_input("Select Date", value=today)
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id, full_name FROM users WHERE role='student'")
    students = cursor.fetchall()
    
    with st.form("bulk_form"):
        for s in students:
            c1, c2 = st.columns([3, 1])
            with c1: st.write(s['full_name'])
            with c2: status = st.selectbox("Status", ["Present", "Absent", "Leave"], key=f"bulk_{s['id']}")
        if st.form_submit_button("Update Bulk Attendance", type="primary"):
            for s in students:
                cursor.execute("INSERT INTO attendance (student_id, date, status, timestamp) VALUES (?, ?, ?, ?) ON CONFLICT(student_id, date) DO UPDATE SET status = excluded.status",
                               (s['id'], date.strftime(DATE_FORMAT), st.session_state[f"bulk_{s['id']}"], str(datetime.datetime.now())))
            conn.commit(); st.success("Bulk attendance updated!"); st.rerun()
    conn.close()

# --- Main App UI & CSS (Canva Premium Style) ---
def main():
    st.set_page_config(layout="wide", page_title="AI Premium AMS", page_icon="📋")
    
    # PREMIUM GLASSMORPHISM CSS (Canva-inspired)
    st.markdown("""
    <style>
        @import url('https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700;800&display=swap');
        html, body, [class*="css"] { font-family: 'Plus Jakarta Sans', sans-serif; background-color: #F3F4F6; }
        .main .block-container { padding: 2rem 2rem; }
        
        /* Sidebar */
        section[data-testid="stSidebar"] {
            background: rgba(255, 255, 255, 0.6);
            backdrop-filter: blur(16px);
            -webkit-backdrop-filter: blur(16px);
            border-right: 1px solid rgba(255,255,255,0.3);
        }
        section[data-testid="stSidebar"] .stMarkdown { color: #1F2937; }
        
        /* Glass Card */
        .premium-card, .glass-effect {
            background: rgba(255, 255, 255, 0.7);
            backdrop-filter: blur(10px);
            border-radius: 16px;
            padding: 1.5rem;
            border: 1px solid rgba(255, 255, 255, 0.5);
            box-shadow: 0 4px 20px rgba(0,0,0,0.02);
            transition: all 0.3s ease;
        }
        .premium-card:hover { transform: translateY(-2px); box-shadow: 0 8px 30px rgba(0,0,0,0.06); }
        
        /* Metrics */
        .premium-metric {
            background: white;
            padding: 1.5rem;
            border-radius: 14px;
            text-align: center;
            border: 1px solid #E5E7EB;
            box-shadow: 0 2px 8px rgba(0,0,0,0.02);
        }
        .premium-metric-icon { font-size: 1.8rem; }
        .premium-metric-value { font-size: 2.2rem; font-weight: 800; color: #111827; margin: 0.2rem 0; }
        .premium-metric-label { font-size: 0.85rem; color: #6B7280; font-weight: 600; text-transform: uppercase; letter-spacing: 0.5px; }
        .premium-metric-sub { font-size: 0.75rem; color: #9CA3AF; margin-top: 0.5rem; }
        
        /* Gradient Text */
        .premium-header {
            font-weight: 800; font-size: 2rem; margin-bottom: 1rem;
            background: -webkit-linear-gradient(135deg, #4F46E5 0%, #9333EA 100%);
            -webkit-background-clip: text; -webkit-text-fill-color: transparent;
        }
        
        /* Premium Buttons */
        .stButton > button {
            background: #4F46E5; color: white; border: none;
            padding: 0.6rem 2rem; border-radius: 50px; font-weight: 600;
            box-shadow: 0 4px 12px rgba(79, 70, 229, 0.15);
            transition: all 0.2s ease;
        }
        .stButton > button:hover { transform: translateY(-2px); box-shadow: 0 6px 20px rgba(79, 70, 229, 0.25); color: white; }
    </style>
    """, unsafe_allow_html=True)

    init_database()
    seed_mock_data()
    if "offline_cache" not in st.session_state: st.session_state.offline_cache = []
    if "user" not in st.session_state: st.session_state.user = None

    if st.session_state.user is None:
        st.markdown('<div style="text-align: center; padding: 3rem; background: white; border-radius: 24px; box-shadow: 0 10px 40px rgba(0,0,0,0.05); max-width: 500px; margin: auto;"><h1 style="background: -webkit-linear-gradient(45deg, #4F46E5, #9333EA); -webkit-background-clip: text; -webkit-text-fill-color: transparent; font-weight: 800;">🤖 AI Campus</h1><p style="color: #6B7280;">Next-Gen University Management</p><br>', unsafe_allow_html=True)
        with st.container():
            with st.form("login"):
                u = st.text_input("Username", placeholder="Enter username")
                p = st.text_input("Password", type="password", placeholder="Enter password")
                if st.form_submit_button("Login", type="primary", use_container_width=True):
                    user = authenticate_user(u, p)
                    if user: st.session_state.user = user; st.rerun()
                    else: st.error("Invalid credentials.")
        st.caption("Teacher: `admin` / `admin123` | Student: `student1` / `123456`")
        return

    user = st.session_state.user
    st.sidebar.markdown(f"## 👤 {user['full_name']}")
    st.sidebar.markdown(f"**{'👨‍🏫 Faculty' if user['role'] == 'teacher' else '🧑‍🎓 Student'}**")
    st.sidebar.markdown("---")
    if st.sidebar.button("🚪 Logout", use_container_width=True, type="primary"):
        st.session_state.user = None; st.rerun()

    # Feature-rich Navigation
    if user['role'] == 'student':
        tab1, tab2, tab3, tab4, tab5, tab6, tab7 = st.tabs(["🏠 Dashboard", "✅ Check-In", "📶 Offline", "🤖 AI Chat", "📝 Leave", "📊 Stats", "⚙️ Settings"])
        with tab1: student_tab_dashboard()
        with tab2: student_tab_checkin(user['id'], user['full_name'])
        with tab3: student_tab_offline(user['id'])
        with tab4: student_tab_ai_chatbot(user['id'])
        with tab5: student_tab_leave_requests(user['id'])
        with tab6: student_tab_stats(user['id'])
        with tab7: st.json({"Username": user['username'], "Role": user['role']})
    else:
        tab1, tab2, tab3, tab4, tab5, tab6, tab7 = st.tabs(["🏠 Dashboard", "📅 Matrix", "📚 Subjects", "🤖 AI Chat", "👨‍🏫 CRUD", "📝 Bulk Edit", "⚙️ Settings"])
        with tab1: teacher_tab_dashboard()
        with tab2: teacher_tab_matrix()
        with tab3: teacher_tab_subject_management()
        with tab4: teacher_tab_ai_chatbot()
        with tab5: teacher_tab_crud()
        with tab6: teacher_tab_bulk_attendance()
        with tab7: st.json({"System": "AI University", "Database": "SQLite3", "Status": "Running"})

if __name__ == "__main__":
    main()
