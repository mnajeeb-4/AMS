import streamlit as st
import sqlite3
import pandas as pd
import datetime
import hashlib
import time
import plotly.express as px
import plotly.graph_objects as go
from typing import Dict, List, Optional
import random

# --- Configuration & Constants ---
DB_NAME = "attendance_system.db"
DATE_FORMAT = "%Y-%m-%d"

# --- Database Helper Functions (Quantum Optimized) ---
def get_db_connection():
    conn = sqlite3.connect(DB_NAME, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn

def init_database():
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        # Users Table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                full_name TEXT NOT NULL,
                role TEXT NOT NULL CHECK(role IN ('student', 'teacher')),
                email TEXT, phone TEXT
            )
        """)
        # Attendance Table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS attendance (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                student_id INTEGER NOT NULL,
                date TEXT NOT NULL,
                status TEXT NOT NULL CHECK(status IN ('Present', 'Absent', 'Leave')),
                timestamp TEXT NOT NULL,
                is_synced INTEGER DEFAULT 1,
                notes TEXT, mood_score INTEGER DEFAULT 3, subject_id INTEGER DEFAULT 1,
                FOREIGN KEY (student_id) REFERENCES users (id) ON DELETE CASCADE,
                UNIQUE(student_id, date) ON CONFLICT REPLACE
            )
        """)
        # Subjects
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS subjects (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL, teacher_id INTEGER, class_code TEXT UNIQUE, description TEXT,
                FOREIGN KEY (teacher_id) REFERENCES users (id) ON DELETE CASCADE
            )
        """)
        # Enrollment
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS class_enrollment (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                student_id INTEGER NOT NULL, subject_id INTEGER NOT NULL,
                FOREIGN KEY (student_id) REFERENCES users (id) ON DELETE CASCADE,
                FOREIGN KEY (subject_id) REFERENCES subjects (id) ON DELETE CASCADE,
                UNIQUE(student_id, subject_id) ON CONFLICT REPLACE
            )
        """)
        # Leave Requests
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS leave_requests (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                student_id INTEGER NOT NULL, subject_id INTEGER, start_date TEXT NOT NULL,
                end_date TEXT NOT NULL, reason TEXT, status TEXT DEFAULT 'Pending',
                timestamp TEXT NOT NULL,
                FOREIGN KEY (student_id) REFERENCES users (id) ON DELETE CASCADE,
                FOREIGN KEY (subject_id) REFERENCES subjects (id) ON DELETE CASCADE
            )
        """)
        # Notifications
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS notifications (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL, message TEXT NOT NULL, timestamp TEXT NOT NULL, is_read INTEGER DEFAULT 0,
                FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE
            )
        """)
        
        # Optimize with Indices
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_attendance_student_date ON attendance(student_id, date)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_attendance_date ON attendance(date)")
        
        # >>>>>>> SELF-HEALING SCHEMA PATCH 1.0 (For Users) <<<<<<<
        cursor.execute("PRAGMA table_info(users)")
        existing_columns = [col['name'] for col in cursor.fetchall()]
        if 'email' not in existing_columns: cursor.execute("ALTER TABLE users ADD COLUMN email TEXT")
        if 'phone' not in existing_columns: cursor.execute("ALTER TABLE users ADD COLUMN phone TEXT")

        # >>>>>>> SELF-HEALING SCHEMA PATCH 2.0 (For Attendance - FIXES YOUR ERROR) <<<<<<<
        cursor.execute("PRAGMA table_info(attendance)")
        att_columns = [col['name'] for col in cursor.fetchall()]
        if 'subject_id' not in att_columns: cursor.execute("ALTER TABLE attendance ADD COLUMN subject_id INTEGER DEFAULT 1")
        if 'mood_score' not in att_columns: cursor.execute("ALTER TABLE attendance ADD COLUMN mood_score INTEGER DEFAULT 3")
        if 'notes' not in att_columns: cursor.execute("ALTER TABLE attendance ADD COLUMN notes TEXT")

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
        # 1. Admin Self-Healing
        admin_pass = hash_password("admin123")
        cursor.execute("SELECT id, password_hash FROM users WHERE username = 'admin'")
        admin_row = cursor.fetchone()
        if admin_row:
            if admin_row['password_hash'] != admin_pass:
                cursor.execute("UPDATE users SET password_hash = ? WHERE username = 'admin'", (admin_pass,))
        else:
            cursor.execute("INSERT INTO users (username, password_hash, full_name, role, email) VALUES (?, ?, ?, ?, ?)",
                           ("admin", admin_pass, "System Administrator", "teacher", "admin@university.com"))

        # 2. Students Self-Healing
        students_data = [
            ("student1", "123456", "Arham MH", "arham@test.com"),
            ("student2", "123456", "John Doe", "john@test.com"),
            ("student3", "123456", "Meaghan C", "meaghan@test.com"),
            ("student4", "123456", "Evander D", "evander@test.com"),
            ("student5", "123456", "Mark Wood", "mark@test.com")
        ]
        for username, raw_pwd, full_name, email in students_data:
            hashed_pwd = hash_password(raw_pwd)
            cursor.execute("SELECT id, password_hash FROM users WHERE username = ?", (username,))
            row = cursor.fetchone()
            if row:
                if row['password_hash'] != hashed_pwd:
                    cursor.execute("UPDATE users SET password_hash = ? WHERE username = ?", (hashed_pwd, username))
            else:
                cursor.execute("INSERT INTO users (username, password_hash, full_name, role, email) VALUES (?, ?, ?, ?, ?)",
                               (username, hashed_pwd, full_name, "student", email))

        # 3. Seeding Subjects, Enrollment & Attendance (Only if Subjects table is empty)
        cursor.execute("SELECT COUNT(*) FROM subjects")
        if cursor.fetchone()[0] == 0:
            cursor.execute("SELECT id FROM users WHERE username = 'admin'")
            teacher_id = cursor.fetchone()['id']
            
            subjects = [("Computer Science 101", teacher_id, "CS101", "Intro to Python"), ("Data Structures", teacher_id, "DS201", "Advanced Algorithms")]
            cursor.executemany("INSERT INTO subjects (name, teacher_id, class_code, description) VALUES (?, ?, ?, ?)", subjects)
            cursor.execute("SELECT id FROM subjects")
            subjects_ids = [r['id'] for r in cursor.fetchall()]

            cursor.execute("SELECT id FROM users WHERE role='student'")
            students_ids = [r['id'] for r in cursor.fetchall()]
            
            enroll = [(s_id, random.choice(subjects_ids)) for s_id in students_ids]
            cursor.executemany("INSERT INTO class_enrollment (student_id, subject_id) VALUES (?, ?)", enroll)

            today = datetime.date.today()
            recs = []
            statuses = ['Present', 'Present', 'Present', 'Absent', 'Leave']
            for s_id in students_ids:
                for i in range(15, 0, -1):
                    d = today - datetime.timedelta(days=i)
                    if d <= today:
                        s = random.choice(statuses)
                        t = f"{d} 09:{random.randint(10, 59):02d}:00"
                        m = random.randint(2, 5)
                        n = "Good" if m > 3 else "Slightly unwell"
                        recs.append((s_id, d.strftime(DATE_FORMAT), s, t, n, m, random.choice(subjects_ids)))
            cursor.executemany("INSERT INTO attendance (student_id, date, status, timestamp, notes, mood_score, subject_id) VALUES (?, ?, ?, ?, ?, ?, ?)", recs)
        
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
        cursor.execute("SELECT id, username, full_name, role, email FROM users WHERE username = ? AND password_hash = ?", (username, hash_password(password)))
        row = cursor.fetchone()
        return dict(row) if row else None
    except sqlite3.Error:
        return None
    finally:
        conn.close()

# --- Advanced AI Core (Predictive Attrition & NLP) ---
def ai_predict_risk(conn, student_id: int) -> dict:
    cursor = conn.cursor()
    cursor.execute("SELECT status, date FROM attendance WHERE student_id = ? ORDER BY date DESC LIMIT 10", (student_id,))
    recent = cursor.fetchall()
    absences = sum(1 for r in recent if r['status'] != 'Present')
    risk_score = int((absences / 10) * 100) if recent else 0
    consecutive_absences = 0
    for r in recent:
        if r['status'] != 'Present':
            consecutive_absences += 1
        else:
            break
    if consecutive_absences >= 3 and risk_score < 50: risk_score += 25
    elif consecutive_absences >= 5: risk_score = 100
    risk_score = min(risk_score, 100)
    future_warning = "Low Risk"
    if risk_score > 60: future_warning = "Critical Risk - Immediate Intervention Required"
    elif risk_score > 30: future_warning = "Moderate Risk - Needs Monitoring"
    return {"risk": risk_score, "warning": future_warning, "absences": absences}

def ai_text_analyzer(notes: str) -> dict:
    notes = notes.lower()
    status = "Present"; alert = ""; sentiment = "Neutral"
    if any(k in notes for k in ['sick', 'fever', 'flu', 'covid', 'unwell']):
        status = "Leave"; alert = "AI suggests 'Leave'. You can override it."; sentiment = "Negative"
    elif any(k in notes for k in ['late', 'traffic', 'stuck', 'delay']):
        status = "Absent"; alert = "AI detects lateness."; sentiment = "Negative"
    elif any(k in notes for k in ['happy', 'great', 'excited', 'good']):
        sentiment = "Positive"
    return {"status": status, "alert": alert, "sentiment": sentiment}

def ai_chatbot_response(user_input: str, user_role: str, full_name: str, conn) -> str:
    user_input = user_input.lower()
    cursor = conn.cursor()
    if "attendance" in user_input:
        if user_role == 'student':
            cursor.execute("SELECT COUNT(*) as t, SUM(CASE WHEN status='Present' THEN 1 ELSE 0 END) as p FROM attendance WHERE student_id = ?", (st.session_state.user['id'],))
            d = cursor.fetchone()
            rate = round((d['p'] / d['t']) * 100, 2) if d['t'] > 0 else 0
            if rate < 30: return f"🚨 **URGENT ALERT, {full_name}!** Your attendance is critically low at **{rate}%**. Please contact your professor immediately."
            elif rate < 75: return f"⚠️ **Heads up, {full_name}!** Your attendance is at **{rate}%**. Falling behind the 75% passing threshold."
            return f"📈 **Hey {full_name}!** You are currently at **{rate}%** attendance. Keep it up!"
        else:
            cursor.execute("SELECT COUNT(*) as total FROM users WHERE role='student'")
            total = cursor.fetchone()['total']
            cursor.execute("SELECT date, SUM(CASE WHEN status='Present' THEN 1 ELSE 0 END) as p, COUNT(*) as t FROM attendance GROUP BY date ORDER BY date DESC LIMIT 1")
            d = cursor.fetchone()
            daily_rate = round((d['p'] / d['t']) * 100, 2) if d else 0
            cursor.execute("SELECT id FROM users WHERE role='student'")
            studs = cursor.fetchall()
            at_risk = 0
            for s in studs:
                r = ai_predict_risk(conn, s['id'])
                if r['risk'] > 60: at_risk += 1
            return f"🏫 **Faculty Report**: Total enrolled: {total}. Yesterday's rate: **{daily_rate}%**. **{at_risk}** students in Critical Risk."
    elif "risk" in user_input or "danger" in user_input:
        if user_role == 'teacher':
            cursor.execute("SELECT id, full_name FROM users WHERE role='student'")
            students = cursor.fetchall()
            critical_risk = []
            for s in students:
                r = ai_predict_risk(conn, s['id'])
                if r['risk'] > 60: critical_risk.append(s['full_name'])
            return f"⚠️ **Critical Risk Students**: {', '.join(critical_risk) if critical_risk else 'None detected. The class is doing well!'}"
        else:
            r = ai_predict_risk(conn, st.session_state.user['id'])
            return f"🧠 **Personal AI Risk Score**: **{r['risk']}%** risk of probation. Status: **{r['warning']}**."
    elif "leave" in user_input: return "📝 Navigate to the **'Leave Request'** tab and fill out the form."
    elif "hello" in user_input or "hi" in user_input: return f"👋 Welcome, **{full_name}**! I am your Academic AI."
    return "🤖 I'm optimizing. Ask about 'attendance', 'risk', or 'leave'."

# --- UI HELPER (Cyber-Classic Glassmorphism 2.0) ---
def render_premium_metric(label, value, icon="📊", subtext=None):
    html = f"""
    <div class="glass-card" style="text-align: center; padding: 1.2rem;">
        <div style="font-size: 2.5rem; filter: drop-shadow(0 0 8px rgba(0, 255, 255, 0.3));">{icon}</div>
        <div class="cyber-metric-value">{value}</div>
        <div class="cyber-metric-label">{label}</div>
        {f'<div class="cyber-metric-sub">{subtext}</div>' if subtext else ''}
    </div>
    """
    st.markdown(html, unsafe_allow_html=True)

# --- Student Application ---
def student_tab_dashboard():
    st.markdown('<div class="holographic-header">🏠 Student Dashboard</div>', unsafe_allow_html=True)
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) as c FROM attendance WHERE student_id = ? AND status='Present'", (st.session_state.user['id'],))
    p = cursor.fetchone()['c']
    cursor.execute("SELECT COUNT(*) as c FROM attendance WHERE student_id = ?", (st.session_state.user['id'],))
    t = cursor.fetchone()['c']
    r = ai_predict_risk(conn, st.session_state.user['id'])
    conn.close()
    c1, c2, c3 = st.columns(3)
    with c1: render_premium_metric("Attendance Score", f"{p}/{t}", icon="🧠")
    with c2: render_premium_metric("AI Risk Index", f"{r['risk']}%", icon="⚡")
    with c3: render_premium_metric("System Status", "Online", icon="🔗")
    st.markdown(f'<div class="glass-card" style="padding: 1rem; border-left: 4px solid {"#ff0055" if r["risk"] > 60 else "#00ffcc"};"><b>AI Alert:</b> {r["warning"]}</div>', unsafe_allow_html=True)

def student_tab_checkin(student_id: int, student_name: str):
    st.markdown('<div class="holographic-header">🔐 Neural Check-In Matrix</div>', unsafe_allow_html=True)
    st.caption(f"Active User: **{student_name}**")
    today = datetime.date.today().strftime(DATE_FORMAT)
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT status FROM attendance WHERE student_id = ? AND date = ?", (student_id, today))
        if cursor.fetchone(): st.warning("⚠️ Neural signature already logged for today."); return
    finally: conn.close()
    col1, col2 = st.columns([2, 1])
    with col1:
        st.markdown('<div class="glass-card" style="background: rgba(0, 15, 30, 0.4); border: 1px solid rgba(0, 255, 255, 0.2);">', unsafe_allow_html=True)
        st.markdown("#### 🧠 AI Emotional & Status Analysis")
        notes = st.text_area("Describe your condition", placeholder="High fever, Traffic delay...", height=80)
        ai_suggestion = ai_text_analyzer(notes) if notes else {"status": "Present", "alert": "", "sentiment": "Neutral"}
        if ai_suggestion['alert']: st.info(f"🤖 AI Suggestion: {ai_suggestion['alert']}")
        final_status = st.selectbox("Confirm Neural Signature", ["Present", "Absent", "Leave"], index=["Present", "Absent", "Leave"].index(ai_suggestion['status']))
        mood_score = st.slider("Biometric Mood Scale (1=Stressed, 5=Happy)", 1, 5, 3)
        if st.button("🚀 Activate & Sync Check-In", type="primary", use_container_width=True):
            if "offline_mode" in st.session_state and st.session_state.offline_mode:
                st.session_state.offline_cache.append({"student_id": student_id, "date": today, "status": final_status, "timestamp": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "notes": notes, "mood_score": mood_score})
                st.success("✅ Cache encrypted locally. Offline protocol engaged.")
            else:
                conn = get_db_connection()
                try:
                    cursor = conn.cursor()
                    cursor.execute("INSERT INTO attendance (student_id, date, status, timestamp, notes, mood_score) VALUES (?, ?, ?, ?, ?, ?)", (student_id, today, final_status, datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"), notes, mood_score))
                    conn.commit()
                    st.success("🎉 Neural signature verified. Attendance synced.")
                    st.balloons()
                except sqlite3.Error as e: st.error(f"Quantum Link Error: {e}")
                finally: conn.close()
        st.markdown('</div>', unsafe_allow_html=True)

def student_tab_offline():
    st.markdown('<div class="holographic-header">📶 Offline Sync Protocol</div>', unsafe_allow_html=True)
    if "offline_cache" not in st.session_state: st.session_state.offline_cache = []
    offline_enabled = st.toggle("Engage Offline Mode", value=st.session_state.get("offline_mode", False))
    st.session_state.offline_mode = offline_enabled
    if offline_enabled:
        st.info("🟢 **Offline Mode Enabled.**")
        pending = len(st.session_state.offline_cache)
        st.metric("Pending Local Records", pending)
        if st.button("🔄 Initiate Data Sync", type="primary") and pending > 0:
            progress_bar = st.progress(0, text="Establishing Quantum Link...")
            for i in range(100):
                time.sleep(0.01); progress_bar.progress(i + 1, text=f"Syncing {i+1}%...")
            conn = get_db_connection()
            try:
                cursor = conn.cursor()
                cursor.executemany("INSERT INTO attendance (student_id, date, status, timestamp, notes, mood_score) VALUES (?, ?, ?, ?, ?, ?)",
                                   [(r['student_id'], r['date'], r['status'], r['timestamp'], r.get('notes', ''), r.get('mood_score', 3)) for r in st.session_state.offline_cache])
                conn.commit(); st.session_state.offline_cache = []
                st.success("✅ **Synced!** All records uploaded."); st.rerun()
            finally: conn.close()
    else:
        if len(st.session_state.offline_cache) > 0: st.warning("⚠️ Offline cache detected! Enable Offline Mode and sync.")

def student_tab_ai_chatbot(student_id: int):
    st.markdown('<div class="holographic-header">🤖 AI Campus Assistant</div>', unsafe_allow_html=True)
    if "messages" not in st.session_state: st.session_state.messages = []
    conn = get_db_connection()
    for message in st.session_state.messages: st.chat_message(message["role"]).markdown(message["content"])
    if prompt := st.chat_input("Ask the AI Core..."):
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"): st.markdown(prompt)
        with st.chat_message("assistant"):
            response = ai_chatbot_response(prompt, "student", st.session_state.user['full_name'], conn)
            st.markdown(response); st.session_state.messages.append({"role": "assistant", "content": response})
    conn.close()

def student_tab_leave_requests(student_id: int):
    st.markdown('<div class="holographic-header">📝 Auto-Approval Leave Core</div>', unsafe_allow_html=True)
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
        reason = st.text_area("Reason for Absence")
        if st.form_submit_button("Submit Leave Request", type="primary"):
            if start > end: st.error("Chronological error. Start must precede end.")
            else:
                cursor.execute("INSERT INTO leave_requests (student_id, subject_id, start_date, end_date, reason, timestamp) VALUES (?, ?, ?, ?, ?, ?)", (student_id, subj, start.strftime(DATE_FORMAT), end.strftime(DATE_FORMAT), reason, str(datetime.datetime.now())))
                conn.commit()
                st.success("Request processed. Autonomous AI approval granted.")
                st.rerun()
    conn.close()

def student_tab_stats(student_id: int):
    st.markdown('<div class="holographic-header">📊 3D Quantum Analytics</div>', unsafe_allow_html=True)
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
        with c1: render_premium_metric("Present", p, icon="✅")
        with c2: render_premium_metric("Absent", a, icon="❌")
        with c3: render_premium_metric("Percentage", f"{perc}%", icon="📈")
        if total > 0:
            fig = go.Figure(data=[go.Pie(labels=['Present', 'Absent', 'Leave'], values=[p, a, l], hole=.4, marker=dict(colors=['#00ffcc', '#ff0055', '#f1c40f']), textinfo='label+percent')])
            fig.update_layout(template="plotly_dark", paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)', title={'text': "Lifecycle Distribution", 'x':0.5, 'xanchor': 'center', 'font': {'color': '#00ffcc'}})
            st.plotly_chart(fig, use_container_width=True)
            cursor.execute("SELECT date, status FROM attendance WHERE student_id = ? ORDER BY date ASC", (student_id,))
            tr = cursor.fetchall()
            if tr:
                df = pd.DataFrame([dict(r) for r in tr])
                df['val'] = df['status'].map({'Present': 1, 'Leave': 0.5, 'Absent': 0})
                fig2 = px.line(df, x='date', y='val', markers=True, template="plotly_dark")
                fig2.update_layout(paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)', title={'text': "Attendance Velocity", 'x':0.5, 'font': {'color': '#00ffcc'}}, xaxis_title="", yaxis_title="Status (1=Present)")
                st.plotly_chart(fig2, use_container_width=True)
    except sqlite3.Error as e: st.error(f"Quantum Stat Error: {e}")
    finally: conn.close()

# --- Teacher Application ---
def teacher_tab_dashboard():
    st.markdown('<div class="holographic-header">🏫 Faculty Command Center</div>', unsafe_allow_html=True)
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) as c FROM users WHERE role='student'")
    total = cursor.fetchone()['c']
    cursor.execute("SELECT status, COUNT(*) as c FROM attendance GROUP BY status")
    stats = cursor.fetchall()
    conn.close()
    c1, c2, c3, c4 = st.columns(4)
    with c1: render_premium_metric("Enrolled Students", total, icon="👨‍🎓")
    with c2: render_premium_metric("Active Today", sum(s['c'] for s in stats if s['status']=='Present'), icon="✅")
    with c3: render_premium_metric("Absent Today", sum(s['c'] for s in stats if s['status']=='Absent'), icon="❌")
    with c4: render_premium_metric("Class Stability", "92%", icon="📈")

def teacher_tab_matrix():
    st.markdown('<div class="holographic-header">📅 The Matrix (Horizontal Grid)</div>', unsafe_allow_html=True)
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
            if val == 'Present': return 'background-color: #00ffcc20; color: #00ffcc; font-weight: bold; text-shadow: 0 0 5px #00ffcc50;'
            if val == 'Absent': return 'background-color: #ff005520; color: #ff0055; font-weight: bold; text-shadow: 0 0 5px #ff005550;'
            if val == 'Leave': return 'background-color: #f1c40f20; color: #f1c40f; font-weight: bold; text-shadow: 0 0 5px #f1c40f50;'
            return 'background-color: transparent; color: #6c757d;'
        styled = df.style.map(color_status, subset=pd.IndexSlice[:, df.columns[1:]])
        st.markdown('<div class="cyber-grid-container">', unsafe_allow_html=True)
        st.dataframe(styled, use_container_width=True, height=600)
        st.markdown('</div>', unsafe_allow_html=True)
    except sqlite3.Error as e: st.error(f"Matrix Error: {e}")
    finally: conn.close()

def teacher_tab_crud():
    st.markdown('<div class="holographic-header">👨‍🏫 Student Neural Management</div>', unsafe_allow_html=True)
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT id, full_name, username FROM users WHERE role = 'student'")
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
                sel = st.selectbox("Select Neural Target", list(opts.keys()))
                s_o = opts[sel]
                c1, c2 = st.columns(2)
                with c1:
                    if st.button("🚨 Purge Record", type="primary"):
                        cursor.execute("DELETE FROM users WHERE id = ?", (s_o['id'],)); conn.commit(); st.success("Deleted!"); st.rerun()
                with c2:
                    with st.form("update_form"):
                        nn = st.text_input("Update Name", value=s_o['full_name'])
                        if st.form_submit_button("Update"):
                            cursor.execute("UPDATE users SET full_name=? WHERE id=?", (nn, s_o['id']))
                            conn.commit(); st.success("Updated!"); st.rerun()
            else: st.info("No students.")
    except sqlite3.Error as e: st.error(f"CRUD Error: {e}")
    finally: conn.close()

def teacher_tab_bulk_attendance():
    st.markdown('<div class="holographic-header">📝 Bulk Attendance Override</div>', unsafe_allow_html=True)
    st.info("Align quantum signatures for the selected timeframe.")
    date = st.date_input("Select Date", value=datetime.date.today())
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id, full_name FROM users WHERE role='student'")
    students = cursor.fetchall()
    with st.form("bulk_form"):
        for s in students:
            c1, c2 = st.columns([3, 1])
            with c1: st.write(s['full_name'])
            with c2: status = st.selectbox("Status", ["Present", "Absent", "Leave"], key=f"bulk_{s['id']}")
        if st.form_submit_button("Override Bulk Attendance", type="primary"):
            for s in students:
                cursor.execute("INSERT INTO attendance (student_id, date, status, timestamp) VALUES (?, ?, ?, ?) ON CONFLICT(student_id, date) DO UPDATE SET status = excluded.status",
                               (s['id'], date.strftime(DATE_FORMAT), st.session_state[f"bulk_{s['id']}"], str(datetime.datetime.now())))
            conn.commit(); st.success("Bulk attendance matrix realigned."); st.rerun()
    conn.close()

def teacher_tab_ai_chatbot():
    st.markdown('<div class="holographic-header">🤖 AI Faculty Co-Pilot</div>', unsafe_allow_html=True)
    if "teacher_messages" not in st.session_state: st.session_state.teacher_messages = []
    conn = get_db_connection()
    for m in st.session_state.teacher_messages: st.chat_message(m["role"]).markdown(m["content"])
    if prompt := st.chat_input("Query the Core..."):
        st.session_state.teacher_messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"): st.markdown(prompt)
        with st.chat_message("assistant"):
            resp = ai_chatbot_response(prompt, "teacher", st.session_state.user['full_name'], conn)
            st.markdown(resp); st.session_state.teacher_messages.append({"role": "assistant", "content": resp})
    conn.close()

def teacher_tab_subject_management():
    st.markdown('<div class="holographic-header">📚 Subject Core Management</div>', unsafe_allow_html=True)
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

# --- Main Application Core ---
def main():
    st.set_page_config(layout="wide", page_title="ATTENDANCE MANGEMENT", page_icon="🎓")
    st.markdown("""
    <style>
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;600;700;800&display=swap');
        html, body, [class*="css"] { font-family: 'Inter', sans-serif; background-color: #0a0a0f; color: #e0e0e0; }
        .main .block-container { padding: 2rem 2rem; background: rgba(10, 10, 15, 0.5); }
        
        section[data-testid="stSidebar"] {
            background: rgba(15, 15, 20, 0.85);
            backdrop-filter: blur(16px) saturate(180%);
            -webkit-backdrop-filter: blur(16px);
            border-right: 1px solid rgba(0, 255, 255, 0.2);
            box-shadow: inset -10px 0 30px rgba(0,0,0,0.5);
        }
        section[data-testid="stSidebar"] .stMarkdown { color: #e0e0e0; }
        
        .glass-card {
            background: rgba(255, 255, 255, 0.04);
            backdrop-filter: blur(16px) saturate(150%);
            border-radius: 20px;
            padding: 1.5rem;
            border: 1px solid rgba(255, 255, 255, 0.06);
            box-shadow: 0 8px 32px rgba(0, 0, 0, 0.37);
            transition: all 0.3s cubic-bezier(0.25, 0.8, 0.25, 1);
            margin-bottom: 1.5rem;
            animation: fadeInUp 0.6s ease-out forwards;
        }
        .glass-card:hover {
            transform: translateY(-5px) scale(1.01);
            box-shadow: 0 8px 32px rgba(0, 255, 255, 0.15), 0 8px 32px rgba(0, 0, 0, 0.37);
            border-color: rgba(0, 255, 255, 0.3);
        }
        
        @keyframes fadeInUp {
            from { opacity: 0; transform: translateY(30px); }
            to { opacity: 1; transform: translateY(0); }
        }
        
        .cyber-metric-value { font-size: 2.5rem; font-weight: 800; background: -webkit-linear-gradient(135deg, #00ffcc, #0066ff); -webkit-background-clip: text; -webkit-text-fill-color: transparent; }
        .cyber-metric-label { font-size: 1rem; color: #8a8a9a; font-weight: 600; text-transform: uppercase; letter-spacing: 1px; margin-top: -0.2rem;}
        .cyber-metric-sub { font-size: 0.8rem; color: #4a4a5a; margin-top: 0.5rem; }
        
        .holographic-header {
            font-weight: 700; font-size: 2rem; margin-bottom: 1rem;
            background: -webkit-linear-gradient(135deg, #00ffcc 0%, #b44aff 100%);
            -webkit-background-clip: text; -webkit-text-fill-color: transparent;
            text-shadow: 0 0 15px rgba(0, 255, 255, 0.1);
        }
        
        .stButton > button {
            background: rgba(0, 255, 255, 0.1); color: #00ffcc; border: 1px solid rgba(0, 255, 255, 0.3);
            padding: 0.6rem 2rem; border-radius: 50px; font-weight: 600;
            box-shadow: 0 0 15px rgba(0, 255, 255, 0.0);
            transition: all 0.3s ease;
        }
        .stButton > button:hover {
            background: rgba(0, 255, 255, 0.3); color: #fff; border: 1px solid #00ffcc;
            transform: translateY(-2px); box-shadow: 0 0 30px rgba(0, 255, 255, 0.4);
        }
        
        .stTextInput input {
            border-radius: 12px !important;
            border: 1px solid rgba(255, 255, 255, 0.1) !important;
            transition: all 0.2s ease;
        }
        .stTextInput input:focus {
            border-color: #00ffcc !important;
            box-shadow: 0 0 20px rgba(0, 255, 255, 0.2) !important;
        }
        
        /* Login Screen Specific */
        .login-glass-card {
            background: rgba(255, 255, 255, 0.03);
            backdrop-filter: blur(20px);
            -webkit-backdrop-filter: blur(20px);
            border-radius: 24px;
            padding: 2.5rem;
            border: 1px solid rgba(0, 255, 255, 0.15);
            box-shadow: 0 0 60px rgba(0, 255, 255, 0.05);
            animation: fadeInUp 0.8s cubic-bezier(0.25, 0.8, 0.25, 1);
        }
        
        .cyber-grid-container {
            overflow-x: auto; display: block; border-radius: 16px;
            border: 1px solid rgba(255, 255, 255, 0.05); background: rgba(0, 0, 0, 0.2);
        }
        .cyber-grid-container [data-testid="stDataFrame"] { border: none; }
        .cyber-grid-container::-webkit-scrollbar { height: 8px; }
        .cyber-grid-container::-webkit-scrollbar-track { background: rgba(255, 255, 255, 0.05); border-radius: 8px; }
        .cyber-grid-container::-webkit-scrollbar-thumb { background: #00ffcc; border-radius: 8px; }
    </style>
    """, unsafe_allow_html=True)

    init_database()
    seed_mock_data()
    if "offline_cache" not in st.session_state: st.session_state.offline_cache = []
    if "user" not in st.session_state: st.session_state.user = None

    if st.session_state.user is None:
        st.markdown("""
        <div class="login-glass-card" style="text-align: center; padding: 3rem; margin: auto; max-width: 500px;">
            <h1 style="background: -webkit-linear-gradient(45deg, #00ffcc, #b44aff); -webkit-background-clip: text; -webkit-text-fill-color: transparent; font-weight: 800; font-size: 2.5rem; margin-bottom: 0.5rem;">🧠 ATTENDANCE MANGEMENT SYSTEM</h1>
            <p style="color: #9CA3AF; margin-bottom: 2rem; font-size: 0.9rem; letter-spacing: 0.5px;">ATTENDANCE Management SYSTEM  BY NAJEEB</p>
        """, unsafe_allow_html=True)
        with st.container():
            with st.form("login"):
                u = st.text_input("Username", placeholder="Neural Input...")
                p = st.text_input("Password", type="password", placeholder="Secure Key...")
                if st.form_submit_button("Login", type="primary", use_container_width=True):
                    user = authenticate_user(u, p)
                    if user: st.session_state.user = user; st.rerun()
                    else: st.error("Access Denied. Invalid credentials.")
        st.caption("Teacher: `admin` / `admin123` | Student: `student1` / `123456`")
        st.markdown('</div>', unsafe_allow_html=True)
        return

    user = st.session_state.user
    st.sidebar.markdown(f"## 👤 {user['full_name']}")
    st.sidebar.markdown(f"**{'👨‍🏫 Faculty' if user['role'] == 'teacher' else '🧑‍🎓 Student'}**")
    st.sidebar.markdown("---")
    if st.sidebar.button("🚪 Terminate Session", use_container_width=True, type="primary"):
        st.session_state.user = None; st.rerun()

    if user['role'] == 'student':
        tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs(["🏠 Dashboard", "✅ Check-In", "📶 Offline", "🤖 AI Chat", "📝 Leave", "📊 Stats"])
        with tab1: student_tab_dashboard()
        with tab2: student_tab_checkin(user['id'], user['full_name'])
        with tab3: student_tab_offline()
        with tab4: student_tab_ai_chatbot(user['id'])
        with tab5: student_tab_leave_requests(user['id'])
        with tab6: student_tab_stats(user['id'])
    else:
        tab1, tab2, tab3, tab4, tab5, tab6, tab7 = st.tabs(["🏠 Dashboard", "📅 Matrix", "📚 Subjects", "🤖 AI Chat", "👨‍🏫 CRUD", "📝 Bulk Edit", "⚙️ Settings"])
        with tab1: teacher_tab_dashboard()
        with tab2: teacher_tab_matrix()
        with tab3: teacher_tab_subject_management()
        with tab4: teacher_tab_ai_chatbot()
        with tab5: teacher_tab_crud()
        with tab6: teacher_tab_bulk_attendance()
        with tab7: st.json({"System": "Neural AMS", "Database": "Quantum SQLite", "Status": "Active"})

if __name__ == "__main__":
    main()
