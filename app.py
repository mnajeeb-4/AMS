import streamlit as st
import sqlite3
import pandas as pd
import datetime
import hashlib
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
from typing import Dict, List, Optional, Tuple

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
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                full_name TEXT NOT NULL,
                role TEXT NOT NULL CHECK(role IN ('student', 'teacher'))
            )
        """)
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
                FOREIGN KEY (student_id) REFERENCES users (id) ON DELETE CASCADE,
                UNIQUE(student_id, date) ON CONFLICT REPLACE
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
        if cursor.fetchone()[0] > 0:
            return 

        teacher_pass = hash_password("admin123")
        cursor.execute("INSERT INTO users (username, password_hash, full_name, role) VALUES (?, ?, ?, ?)",
                       ("admin", teacher_pass, "System Administrator", "teacher"))
        
        student_data = [
            ("student1", hash_password("123456"), "Arham MH"),
            ("student2", hash_password("123456"), "John Doe"),
            ("student3", hash_password("123456"), "Meaghan Campigotto"),
            ("student4", hash_password("123456"), "Evander Deoscariz"),
            ("student5", hash_password("123456"), "Mark Wood")
        ]
        cursor.executemany("INSERT INTO users (username, password_hash, full_name, role) VALUES (?, ?, ?, ?)",
                           [(u, p, n, "student") for u, p, n in student_data])
        
        cursor.execute("SELECT id, full_name FROM users WHERE role = 'student'")
        students = cursor.fetchall()
        
        today = datetime.date.today()
        attendance_records = []
        import random
        statuses = ['Present', 'Present', 'Present', 'Absent', 'Leave']
        
        for student in students:
            s_id = student['id']
            for i in range(15, 0, -1):
                day_date = today - datetime.timedelta(days=i)
                if day_date <= today:
                    status = random.choice(statuses)
                    timestamp = f"{day_date} 09:{random.randint(10, 59):02d}:00"
                    mood = random.randint(2, 5)
                    notes = "Good" if mood > 3 else "Slightly unwell"
                    attendance_records.append((s_id, day_date.strftime(DATE_FORMAT), status, timestamp, notes, mood))

        cursor.executemany("INSERT INTO attendance (student_id, date, status, timestamp, notes, mood_score) VALUES (?, ?, ?, ?, ?, ?)", 
                           attendance_records)
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
        cursor.execute("SELECT id, username, full_name, role FROM users WHERE username = ? AND password_hash = ?", 
                       (username, hashed_input))
        row = cursor.fetchone()
        return dict(row) if row else None
    except sqlite3.Error:
        return None
    finally:
        conn.close()

# --- AI Utilities ---
def ai_text_analyzer(notes: str) -> dict:
    notes = notes.lower()
    status = "Present"
    alert = ""
    if any(k in notes for k in ['sick', 'fever', 'flu', 'covid', 'unwell']):
        status = "Leave"
        alert = "Based on your input, the AI recommends 'Leave'. You can override it."
    elif any(k in notes for k in ['late', 'traffic', 'stuck', 'delay']):
        status = "Absent"
        alert = "Based on your input, the AI marks this as 'Absent' (Late)."
    return {"status": status, "alert": alert}

def ai_predict_risk(conn, student_id: int, full_name: str) -> dict:
    cursor = conn.cursor()
    cursor.execute("SELECT status FROM attendance WHERE student_id = ? ORDER BY date DESC LIMIT 10", (student_id,))
    recent = cursor.fetchall()
    absences = sum(1 for r in recent if r['status'] != 'Present')
    risk_score = int((absences / 10) * 100) if recent else 0
    future_warning = "Low Risk"
    if risk_score > 30: future_warning = "High Risk - Needs Intervention"
    elif risk_score > 10: future_warning = "Moderate Risk"
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
    alert = "Excellent" if rate > 85 else "Good" if rate > 70 else "Needs Attention"
    return f"""
    **Overall Attendance Rate:** {rate}%
    **Status:** {alert}
    *Total Students: {total_students}* | *Days tracked this month: {today.day}*
    *Recommendation:* {'Focus on engagement.' if rate < 80 else 'Attendance is well maintained.'}
    """

# --- UI HELPER (PREMIUM CARDS) ---
def render_premium_metric(label, value, icon="📊", subtext=None):
    """Renders a beautiful premium CSS metric card."""
    html = f"""
    <div class="premium-metric">
        <div class="premium-metric-icon">{icon}</div>
        <div class="premium-metric-value">{value}</div>
        <div class="premium-metric-label">{label}</div>
        {f'<div style="font-size:0.75rem; color:#888;">{subtext}</div>' if subtext else ''}
    </div>
    """
    st.markdown(html, unsafe_allow_html=True)

# --- Student Application ---
def student_tab_checkin(student_id: int, student_name: str):
    st.markdown('<div class="premium-header">🔐 Secure Digital Check-In</div>', unsafe_allow_html=True)
    st.caption(f"Welcome, **{student_name}**. Scan or type to check in.")
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
    finally:
        conn.close()

    col1, col2 = st.columns([2, 1])
    with col1:
        with st.container():
            st.markdown('<div class="premium-card">', unsafe_allow_html=True)
            st.markdown("#### 🧠 AI-Powered Mood Check-In")
            notes = st.text_area("How do you feel today? (Example: I have a fever)", placeholder="Let our AI detect your status...", height=80)
            
            ai_suggestion = ai_text_analyzer(notes) if notes else {"status": "Present", "alert": ""}
            suggested_status = ai_suggestion['status']
            
            if ai_suggestion['alert']:
                st.info(f"🤖 AI Suggestion: {ai_suggestion['alert']}")
            
            final_status = st.selectbox("Confirm Status", ["Present", "Absent", "Leave"], index=["Present", "Absent", "Leave"].index(suggested_status))
            mood_score = st.slider("Your Mood (1=Stressed, 5=Happy)", 1, 5, 3)
            
            if st.button("✅ Mark Attendance", type="primary", use_container_width=True):
                if "offline_mode" in st.session_state and st.session_state.offline_mode:
                    offline_entry = {"student_id": student_id, "date": today, "status": final_status, "timestamp": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "notes": notes, "mood_score": mood_score}
                    st.session_state.offline_cache.append(offline_entry)
                    st.success("✅ Marked in Offline Mode. Data cached.")
                else:
                    conn = get_db_connection()
                    try:
                        cursor = conn.cursor()
                        now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                        cursor.execute("INSERT INTO attendance (student_id, date, status, timestamp, notes, mood_score) VALUES (?, ?, ?, ?, ?, ?)", (student_id, today, final_status, now, notes, mood_score))
                        conn.commit()
                        st.success("🎉 Checked in successfully!")
                        st.balloons()
                    except sqlite3.Error as e: st.error(f"Error: {e}")
                    finally: conn.close()
            st.markdown('</div>', unsafe_allow_html=True)

def student_tab_offline(student_id: int):
    st.markdown('<div class="premium-header">📶 Offline Sync Mode</div>', unsafe_allow_html=True)
    if "offline_cache" not in st.session_state: st.session_state.offline_cache = []
    offline_enabled = st.toggle("Enable Offline Mode", value=st.session_state.get("offline_mode", False))
    st.session_state.offline_mode = offline_enabled
    
    if offline_enabled:
        st.info("🟢 Offline Mode Active. Data held locally.")
        pending = len(st.session_state.offline_cache)
        st.metric("Pending Offline Records", pending, delta_color="normal")
        if st.button("🔄 Sync Now", type="primary") and pending > 0:
            conn = get_db_connection()
            try:
                cursor = conn.cursor()
                cursor.executemany("INSERT INTO attendance (student_id, date, status, timestamp, notes, mood_score) VALUES (?, ?, ?, ?, ?, ?)",
                                   [(r['student_id'], r['date'], r['status'], r['timestamp'], r.get('notes', ''), r.get('mood_score', 3)) for r in st.session_state.offline_cache])
                conn.commit()
                st.session_state.offline_cache = []
                st.success("Synced successfully!")
                st.rerun()
            finally: conn.close()
    else:
        if len(st.session_state.offline_cache) > 0: st.warning("⚠️ Unsynced records found! Enable offline mode and sync.")

def student_tab_ai_advisor(student_id: int):
    st.markdown('<div class="premium-header">🤖 AI Performance Advisor</div>', unsafe_allow_html=True)
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT status FROM attendance WHERE student_id = ?", (student_id,))
        records = cursor.fetchall()
        total = len(records)
        present = sum(1 for r in records if r['status'] == 'Present')
        rate = round((present / total * 100), 2) if total > 0 else 0
        streak = 0
        for r in reversed(records):
            if r['status'] == 'Present': streak += 1
            else: break
        
        # Premium 3-Column Layout
        col1, col2, col3 = st.columns(3)
        with col1: render_premium_metric("Attendance Rate", f"{rate}%", icon="📈")
        with col2: render_premium_metric("Active Streak", f"{streak} days", icon="🔥")
        with col3: render_premium_metric("Total Records", total, icon="📋")
        
        st.markdown("---")
        if rate >= 90: st.success(f"🌟 Outstanding, {st.session_state.user['full_name']}! You are a role model.")
        elif rate >= 75: st.info(f"📈 You are doing great. {rate}% on track. Keep going!")
        elif rate >= 50: st.warning(f"⚠️ You missed some days. Attend the next 5 classes to boost your score.")
        else: st.error(f"🚨 Below 50% attendance. Please speak to your teacher immediately.")

        cursor.execute("SELECT date, mood_score FROM attendance WHERE student_id = ? ORDER BY date DESC LIMIT 7", (student_id,))
        moods = cursor.fetchall()
        if moods:
            st.markdown("#### 🧠 Emotional Well-being Trend")
            df = pd.DataFrame([dict(r) for r in moods])
            fig = px.line(df, x='date', y='mood_score', markers=True, range_y=[1,5], template="plotly_white")
            fig.update_layout(xaxis_title="Date", yaxis_title="Happiness (1-5)", height=250, margin=dict(l=20, r=20, t=30, b=20))
            st.plotly_chart(fig, use_container_width=True)
    finally: conn.close()

def student_tab_stats(student_id: int):
    st.markdown('<div class="premium-header">📊 Attendance Analytics</div>', unsafe_allow_html=True)
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
            fig.update_layout(title_text="Attendance Distribution", template="plotly_white", margin=dict(t=30, l=20, r=20, b=20))
            st.plotly_chart(fig, use_container_width=True)
            
            cursor.execute("SELECT date, status FROM attendance WHERE student_id = ? ORDER BY date ASC", (student_id,))
            tr = cursor.fetchall()
            if tr:
                df = pd.DataFrame([dict(r) for r in tr])
                df['val'] = df['status'].map({'Present': 1, 'Leave': 0.5, 'Absent': 0})
                fig2 = px.line(df, x='date', y='val', title='Historical Trend', markers=True, template="plotly_white")
                fig2.update_layout(xaxis_title="Date", yaxis_title="Score (1=Present)", height=300, margin=dict(t=30, l=20, r=20, b=20))
                st.plotly_chart(fig2, use_container_width=True)
    except sqlite3.Error as e: st.error(f"Stats Error: {e}")
    finally: conn.close()

# --- Teacher Application ---
def teacher_tab_matrix():
    st.markdown('<div class="premium-header">📅 Enterprise Attendance Matrix</div>', unsafe_allow_html=True)
    today = datetime.date.today()
    start_date = today.replace(day=1)
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT id, full_name FROM users WHERE role = 'student' ORDER BY full_name")
        students = cursor.fetchall()
        if not students: return st.info("No students found.")
        cursor.execute("SELECT student_id, date, status FROM attendance WHERE date >= ? AND date <= ?", (start_date.strftime(DATE_FORMAT), today.strftime(DATE_FORMAT)))
        records = cursor.fetchall()
        
        data, att_map = [], {}
        for r in records: att_map[(r['student_id'], r['date'])] = r['status']
        days = today.day
        
        for s in students:
            row = {"Student Name": s['full_name']}
            for d in range(1, days + 1):
                d_str = f"{today.strftime('%Y-%m')}-{d:02d}"
                row[d_str] = att_map.get((s['id'], d_str), "N/A")
            data.append(row)
        df = pd.DataFrame(data)
        
        def color_status(val):
            if val == 'Present': return 'background-color: #d4edda; color: black; font-weight: bold;'
            if val == 'Absent': return 'background-color: #f8d7da; color: black; font-weight: bold;'
            if val == 'Leave': return 'background-color: #fff3cd; color: black; font-weight: bold;'
            return 'background-color: #f8f9fa; color: #6c757d;'
        
        styled_df = df.style.map(color_status, subset=pd.IndexSlice[:, df.columns[1:]])
        st.dataframe(styled_df, use_container_width=True, height=600)
    except sqlite3.Error as e: st.error(f"Matrix Error: {e}")
    finally: conn.close()

def teacher_tab_crud():
    st.markdown('<div class="premium-header">👨‍🏫 Student Management (CRUD)</div>', unsafe_allow_html=True)
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
                            conn.commit()
                            st.success(f"Added {name}!")
                            st.rerun()
                        except sqlite3.IntegrityError: st.error("Username exists.")
                    else: st.error("All fields required.")
        
        with st.expander("✏️ Update / ❌ Remove Student"):
            if students:
                opts = {f"{s['id']} - {s['full_name']}": s for s in students}
                sel = st.selectbox("Select Student", list(opts.keys()))
                s_obj = opts[sel]
                c1, c2 = st.columns(2)
                with c1:
                    if st.button("🚨 Permanently Delete", type="primary"):
                        cursor.execute("DELETE FROM users WHERE id = ?", (s_obj['id'],)); conn.commit()
                        st.success("Deleted!"); st.rerun()
                with c2:
                    with st.form("update_form"):
                        nn = st.text_input("Update Name", value=s_obj['full_name'])
                        nu = st.text_input("Update Username", value=s_obj['username'])
                        np = st.text_input("New Password (optional)", type="password")
                        if st.form_submit_button("Update"):
                            if np: cursor.execute("UPDATE users SET full_name=?, username=?, password_hash=? WHERE id=?", (nn, nu, hash_password(np), s_obj['id']))
                            else: cursor.execute("UPDATE users SET full_name=?, username=? WHERE id=?", (nn, nu, s_obj['id']))
                            conn.commit()
                            st.success("Updated!")
                            st.rerun()
            else: st.info("No students available.")
    except sqlite3.Error as e: st.error(f"CRUD Error: {e}")
    finally: conn.close()

def teacher_tab_ai_insights():
    st.markdown('<div class="premium-header">🤖 AI Educator Insights</div>', unsafe_allow_html=True)
    conn = get_db_connection()
    try:
        with st.container():
            st.markdown('<div class="premium-card">', unsafe_allow_html=True)
            st.markdown(ai_generate_report(conn))
            st.markdown('</div>', unsafe_allow_html=True)
        st.divider()
        st.markdown("### 🚨 Predictive Risk Alerts")
        cursor = conn.cursor()
        cursor.execute("SELECT id, full_name FROM users WHERE role='student'")
        students = cursor.fetchall()
        risk_data = []
        for s in students:
            r = ai_predict_risk(conn, s['id'], s['full_name'])
            risk_data.append({"Student": s['full_name'], "Risk %": r['risk'], "Absences": r['absences'], "Status": r['warning']})
        df = pd.DataFrame(risk_data).sort_values(by="Risk %", ascending=False)
        
        def color_risk(val):
            if val > 30: return 'background-color: #f8d7da; color: darkred; font-weight: bold;'
            if val > 10: return 'background-color: #fff3cd; color: black;'
            return ''
        styled_df = df.style.map(color_risk, subset=['Risk %'])
        st.dataframe(styled_df, use_container_width=True, height=400)
        st.info("💡 *AI Note: Students > 30% risk need immediate intervention.*")
    except sqlite3.Error as e: st.error(f"Insight Error: {e}")
    finally: conn.close()

def teacher_tab_analytics():
    st.markdown('<div class="premium-header">📊 Macro-Level Analytics</div>', unsafe_allow_html=True)
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT date, SUM(CASE WHEN status='Present' THEN 1 ELSE 0 END) as p, COUNT(*) as t FROM attendance GROUP BY date ORDER BY date ASC")
        data = cursor.fetchall()
        if not data: return st.info("No data.")
        df = pd.DataFrame([dict(r) for r in data])
        df['rate'] = (df['p'] / df['t']) * 100
        fig = px.bar(df, x='date', y='rate', title='Daily Attendance Rate (%)', color='rate', color_continuous_scale='Bluyl', template="plotly_white")
        fig.update_layout(xaxis_tickangle=-45, height=400)
        st.plotly_chart(fig, use_container_width=True)
    except sqlite3.Error as e: st.error(f"Analytics Error: {e}")
    finally: conn.close()

# --- Main App UI & CSS ---
def main():
    st.set_page_config(layout="wide", page_title="AI Premium AMS", page_icon="📋")
    
    # PREMIUM CANVA-LIKE CSS INJECTION
    st.markdown("""
    <style>
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;600;700;800&display=swap');
        html, body, [class*="css"] { font-family: 'Inter', sans-serif; background-color: #F8F9FA; }
        .main .block-container { padding: 2rem 2rem; }
        
        /* Sidebar Premium Styling */
        section[data-testid="stSidebar"] {
            background: linear-gradient(180deg, #2C3E50 0%, #1A252F 100%);
            border-right: none;
        }
        section[data-testid="stSidebar"] .stMarkdown { color: white; }
        section[data-testid="stSidebar"] h1, section[data-testid="stSidebar"] h2 { color: #ffffff !important; }
        
        /* Premium Card Design */
        .premium-card {
            background: #ffffff;
            border-radius: 16px;
            padding: 1.5rem;
            margin-bottom: 1.5rem;
            box-shadow: 0 4px 20px rgba(0, 0, 0, 0.03);
            border: 1px solid #f1f1f1;
            transition: transform 0.2s, box-shadow 0.2s;
        }
        .premium-card:hover { transform: translateY(-2px); box-shadow: 0 8px 30px rgba(0,0,0,0.08); }
        
        /* Premium Metric Box */
        .premium-metric {
            background: white;
            padding: 1.5rem;
            border-radius: 12px;
            text-align: center;
            border: 1px solid #E9ECEF;
            box-shadow: 0 2px 8px rgba(0,0,0,0.02);
            margin-bottom: 1rem;
        }
        .premium-metric-icon { font-size: 1.8rem; margin-bottom: 0.2rem; }
        .premium-metric-value { font-size: 2.2rem; font-weight: 700; color: #2C3E50; margin: 0.2rem 0; }
        .premium-metric-label { font-size: 0.9rem; color: #6c757d; font-weight: 600; text-transform: uppercase; letter-spacing: 0.5px; }
        
        .premium-header {
            font-weight: 800;
            font-size: 1.8rem;
            color: #2C3E50;
            margin-bottom: 0.5rem;
            background: linear-gradient(135deg, #6C63FF 0%, #3F3D9E 100%);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            background-clip: text;
        }
        
        /* Button Styling */
        .stButton > button {
            background: linear-gradient(135deg, #6C63FF 0%, #3F3D9E 100%);
            color: white;
            border: none;
            padding: 0.6rem 1.5rem;
            border-radius: 50px;
            font-weight: 600;
            box-shadow: 0 4px 15px rgba(108, 99, 255, 0.2);
            transition: all 0.3s ease;
        }
        .stButton > button:hover {
            transform: translateY(-3px);
            box-shadow: 0 8px 25px rgba(108, 99, 255, 0.4);
            color: white;
        }
        
        /* Inputs */
        .stTextArea textarea, .stTextInput input, .stSelectbox div[data-baseweb="select"] {
            border-radius: 12px !important;
            border: 1px solid #E9ECEF !important;
            box-shadow: 0 2px 4px rgba(0,0,0,0.02);
        }
    </style>
    """, unsafe_allow_html=True)

    init_database()
    seed_mock_data()
    
    if "offline_cache" not in st.session_state: st.session_state.offline_cache = []
    if "user" not in st.session_state: st.session_state.user = None

    if st.session_state.user is None:
        st.markdown('<div style="text-align: center; padding: 2rem;"><h1 style="background: -webkit-linear-gradient(45deg, #6C63FF, #3F3D9E); -webkit-background-clip: text; -webkit-text-fill-color: transparent; font-weight: 800;">🤖 AI Attendance System</h1><p style="color: #6c757d;">Premium University Management Portal</p></div>', unsafe_allow_html=True)
        with st.container():
            col1, col2, col3 = st.columns([1, 1, 1])
            with col2:
                with st.form("login"):
                    st.subheader("Secure Login")
                    u = st.text_input("Username", placeholder="Enter username")
                    p = st.text_input("Password", type="password", placeholder="Enter password")
                    if st.form_submit_button("Login", type="primary", use_container_width=True):
                        user = authenticate_user(u, p)
                        if user: 
                            st.session_state.user = user
                            st.rerun()
                        else: st.error("Invalid credentials.")
        st.caption("Default Credentials: Teacher: `admin` / `admin123` | Student: `student1` / `123456`")
        return

    user = st.session_state.user
    st.sidebar.markdown(f"## 👤 {user['full_name']}")
    st.sidebar.markdown(f"**{'👨‍🏫 Teacher' if user['role'] == 'teacher' else '🧑‍🎓 Student'}**")
    st.sidebar.markdown("---")
    if st.sidebar.button("🚪 Logout", use_container_width=True, type="primary"):
        st.session_state.user = None
        st.rerun()

    if user['role'] == 'student':
        tab1, tab2, tab3, tab4 = st.tabs(["✅ Check-In", "📶 Offline", "🤖 AI Advisor", "📊 Stats"])
        with tab1: student_tab_checkin(user['id'], user['full_name'])
        with tab2: student_tab_offline(user['id'])
        with tab3: student_tab_ai_advisor(user['id'])
        with tab4: student_tab_stats(user['id'])
    else:
        tab1, tab2, tab3, tab4 = st.tabs(["📅 Matrix", "👨‍🏫 CRUD", "🤖 AI Insights", "📊 Analytics"])
        with tab1: teacher_tab_matrix()
        with tab2: teacher_tab_crud()
        with tab3: teacher_tab_ai_insights()
        with tab4: teacher_tab_analytics()

if __name__ == "__main__":
    main()
