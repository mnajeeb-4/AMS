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
        # Users Table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                full_name TEXT NOT NULL,
                role TEXT NOT NULL CHECK(role IN ('student', 'teacher'))
            )
        """)
        # Attendance Table (Added 'notes' and 'mood_score' for AI features)
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

# --- AI Utilities (Rule-Based & Predictive) ---
def ai_text_analyzer(notes: str) -> dict:
    """Fake NLP AI to analyze notes and suggest status."""
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
    """Calculate AI risk score and future prediction."""
    cursor = conn.cursor()
    cursor.execute("""
        SELECT status FROM attendance WHERE student_id = ? ORDER BY date DESC LIMIT 10
    """, (student_id,))
    recent = cursor.fetchall()
    
    absences = sum(1 for r in recent if r['status'] != 'Present')
    risk_score = int((absences / 10) * 100) if recent else 0
    
    future_warning = "Low Risk"
    if risk_score > 30:
        future_warning = "High Risk of falling below attendance requirements"
    elif risk_score > 10:
        future_warning = "Moderate Risk - Monitor this student"
        
    return {"risk": risk_score, "warning": future_warning, "absences": absences}

def ai_generate_report(conn) -> str:
    """Generates a human-readable health report for the class."""
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) as total FROM users WHERE role='student'")
    total_students = cursor.fetchone()['total']
    
    today = datetime.date.today()
    start_of_month = today.replace(day=1)
    cursor.execute("""
        SELECT status, COUNT(*) as c FROM attendance 
        WHERE date >= ? GROUP BY status
    """, (start_of_month.strftime(DATE_FORMAT),))
    stats = cursor.fetchall()
    
    present = sum(r['c'] for r in stats if r['status'] == 'Present')
    total = sum(r['c'] for r in stats)
    rate = round((present / total) * 100, 2) if total > 0 else 0.0
    
    alert = "Excellent" if rate > 85 else "Good" if rate > 70 else "Needs Immediate Attention"
    
    return f"""
    📊 **AI Monthly Class Health Summary**
    
    **Overall Attendance Rate:** {rate}%
    **Status:** {alert}
    
    **Insights:**
    - Total Students Active: {total_students}
    - Days tracked this month: {today.day}
    
    **Recommendations:**
    - {'Focus on boosting engagement through interactive sessions.' if rate < 80 else 'Attendance is well maintained. Continue positive reinforcement.'}
    - Use the "Risk Alerts" section to identify at-risk individuals.
    """

# --- Student Application ---
def student_tab_checkin(student_id: int, student_name: str):
    st.subheader(f"🔐 Secure Digital Check-In: {student_name}")
    st.markdown("---")
    
    today = datetime.date.today().strftime(DATE_FORMAT)
    
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT status FROM attendance WHERE student_id = ? AND date = ?", (student_id, today))
        if cursor.fetchone():
            st.warning("⚠️ You have already checked in for today!")
            st.info("Duplicate check-ins are prevented automatically.")
            return
    finally:
        conn.close()

    col1, col2 = st.columns([3, 2])
    with col1:
        st.markdown("#### 🧠 AI-Powered Mood Check-In")
        st.write("Type how you're feeling. Our AI will auto-detect the status (e.g., fever = Leave).")
        
        notes = st.text_area("How do you feel today?", placeholder="Example: I have a high fever today", height=100)
        
        ai_suggestion = ai_text_analyzer(notes) if notes else {"status": "Present", "alert": ""}
        suggested_status = ai_suggestion['status']
        
        if ai_suggestion['alert']:
            st.info(f"🤖 AI Suggestion: {ai_suggestion['alert']}")
        
        final_status = st.selectbox("Confirm Attendance Status", ["Present", "Absent", "Leave"], index=["Present", "Absent", "Leave"].index(suggested_status))
        mood_score = st.slider("Your Mood (1=Stressed, 5=Happy)", 1, 5, 3)
        
        if st.button("✅ Mark Attendance", type="primary", use_container_width=True):
            if "offline_mode" in st.session_state and st.session_state.offline_mode:
                offline_entry = {
                    "student_id": student_id, "date": today, "status": final_status,
                    "timestamp": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "notes": notes, "mood_score": mood_score
                }
                st.session_state.offline_cache.append(offline_entry)
                st.success("✅ Marked in Offline Mode. Data cached locally.")
            else:
                conn = get_db_connection()
                try:
                    cursor = conn.cursor()
                    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    cursor.execute("INSERT INTO attendance (student_id, date, status, timestamp, notes, mood_score) VALUES (?, ?, ?, ?, ?, ?)",
                                   (student_id, today, final_status, now, notes, mood_score))
                    conn.commit()
                    st.success("🎉 Checked in successfully!")
                    st.balloons()
                except sqlite3.Error as e:
                    st.error(f"Error: {e}")
                finally:
                    conn.close()

def student_tab_offline(student_id: int):
    st.subheader("📶 Offline Mode Management")
    st.markdown("---")
    
    if "offline_cache" not in st.session_state:
        st.session_state.offline_cache = []
    
    offline_enabled = st.toggle("Enable Offline Mode", value=st.session_state.get("offline_mode", False))
    st.session_state.offline_mode = offline_enabled
    
    if offline_enabled:
        st.info("🟢 Offline Mode Active. Data held locally.")
        pending = len(st.session_state.offline_cache)
        st.metric("Pending Offline Records", pending)
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
            finally:
                conn.close()
    else:
        if len(st.session_state.offline_cache) > 0:
            st.warning("⚠️ You have unsynced records! Enable offline mode and sync.")

def student_tab_ai_advisor(student_id: int):
    st.subheader("🤖 AI Performance Advisor")
    st.markdown("---")
    
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
            if r['status'] == 'Present':
                streak += 1
            else:
                break
        
        st.metric("Current Attendance %", f"{rate}%")
        st.metric("Current Active Streak", f"{streak} days")
        
        if rate >= 90:
            st.success(f"🌟 Outstanding, {st.session_state.user['full_name']}! You are a role model. Keep up the great work!")
        elif rate >= 75:
            st.info(f"📈 You are doing great. You are {rate}% on track. Just 3 more days and you'll hit 80%!")
        elif rate >= 50:
            st.warning(f"⚠️ You have missed quite a few days. Try to attend the next 5 classes to boost your score.")
        else:
            st.error(f"🚨 You are below 50% attendance. Please speak to your teacher immediately.")
            
        st.markdown("#### 📋 Your Recent Mood History")
        cursor.execute("SELECT date, mood_score FROM attendance WHERE student_id = ? ORDER BY date DESC LIMIT 7", (student_id,))
        moods = cursor.fetchall()
        
        if moods:
            df = pd.DataFrame([dict(r) for r in moods])
            fig = px.line(df, x='date', y='mood_score', title='Weekly Emotional Trend', markers=True, range_y=[1,5])
            fig.update_layout(xaxis_title="Date", yaxis_title="Happiness Level (1-5)")
            st.plotly_chart(fig, use_container_width=True)
    finally:
        conn.close()

def student_tab_stats(student_id: int):
    st.subheader("📊 Attendance Analytics")
    st.markdown("---")
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT status, COUNT(*) as count FROM attendance WHERE student_id = ? GROUP BY status", (student_id,))
        rows = cursor.fetchall()
        total_present = total_absent = total_leave = 0
        for r in rows:
            if r['status'] == 'Present': total_present = r['count']
            elif r['status'] == 'Absent': total_absent = r['count']
            elif r['status'] == 'Leave': total_leave = r['count']
            
        total = total_present + total_absent + total_leave
        perc = round((total_present / total * 100), 2) if total else 0
        col1, col2, col3 = st.columns(3)
        col1.metric("Present", total_present)
        col2.metric("Absent", total_absent)
        col3.metric("Attendance %", f"{perc}%")
        
        if total > 0:
            fig = go.Figure(data=[go.Pie(labels=['Present', 'Absent', 'Leave'], values=[total_present, total_absent, total_leave], hole=.3, marker=dict(colors=['#28a745', '#dc3545', '#ffc107']))])
            fig.update_layout(title_text="Distribution")
            st.plotly_chart(fig, use_container_width=True)
            
            cursor.execute("SELECT date, status FROM attendance WHERE student_id = ? ORDER BY date ASC", (student_id,))
            trends = cursor.fetchall()
            if trends:
                df = pd.DataFrame([dict(r) for r in trends])
                df['status_val'] = df['status'].map({'Present': 1, 'Leave': 0.5, 'Absent': 0})
                fig2 = px.line(df, x='date', y='status_val', title='Trend', markers=True)
                st.plotly_chart(fig2, use_container_width=True)
    except sqlite3.Error as e:
        st.error(f"Stats Error: {e}")
    finally:
        conn.close()

# --- Teacher Application ---
def teacher_tab_matrix():
    st.subheader("📅 Enterprise Attendance Matrix")
    st.markdown("---")
    today = datetime.date.today()
    start_date = today.replace(day=1)
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT id, full_name FROM users WHERE role = 'student' ORDER BY full_name")
        students = cursor.fetchall()
        if not students:
            st.info("No students found.")
            return

        cursor.execute("SELECT student_id, date, status FROM attendance WHERE date >= ? AND date <= ?", 
                       (start_date.strftime(DATE_FORMAT), today.strftime(DATE_FORMAT)))
        records = cursor.fetchall()
        
        data = []
        att_map = {}
        for r in records:
            att_map[(r['student_id'], r['date'])] = r['status']
            
        days_in_month = today.day
        for s in students:
            row = {"Student Name": s['full_name']}
            for day in range(1, days_in_month + 1):
                d_str = f"{today.strftime('%Y-%m')}-{day:02d}"
                row[d_str] = att_map.get((s['id'], d_str), "N/A")
            data.append(row)
        df = pd.DataFrame(data)
        
        def color_status(val):
            bg, color = 'white', 'black'
            if val == 'Present': bg, color = '#d4edda', 'black'
            elif val == 'Absent': bg, color = '#f8d7da', 'black'
            elif val == 'Leave': bg, color = '#fff3cd', 'black'
            elif val == 'N/A': bg, color = '#f8f9fa', '#6c757d'
            return f'background-color: {bg}; color: {color}; text-align: center; font-weight: bold;'
        
        styled_df = df.style.map(color_status, subset=pd.IndexSlice[:, df.columns[1:]])
        st.dataframe(styled_df, use_container_width=True, height=600)
    except sqlite3.Error as e:
        st.error(f"Matrix Error: {e}")
    finally:
        conn.close()

def teacher_tab_crud():
    st.subheader("👨‍🏫 Student Management (CRUD)")
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT id, full_name, username FROM users WHERE role = 'student'")
        students = cursor.fetchall()
        
        with st.expander("➕ Add New Student"):
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
        
        with st.expander("❌ Remove / ✏️ Update Student"):
            if students:
                opts = {f"{s['id']} - {s['full_name']}": s for s in students}
                sel = st.selectbox("Select Student", list(opts.keys()))
                s_obj = opts[sel]
                c1, c2 = st.columns(2)
                with c1:
                    if st.button("🚨 Permanently Delete", type="primary"):
                        cursor.execute("DELETE FROM users WHERE id = ?", (s_obj['id'],))
                        conn.commit()
                        st.success("Deleted!")
                        st.rerun()
                with c2:
                    with st.form("update_form"):
                        new_name = st.text_input("Update Name", value=s_obj['full_name'])
                        new_uname = st.text_input("Update Username", value=s_obj['username'])
                        new_pwd = st.text_input("New Password", type="password")
                        if st.form_submit_button("Update"):
                            if new_pwd:
                                cursor.execute("UPDATE users SET full_name=?, username=?, password_hash=? WHERE id=?", (new_name, new_uname, hash_password(new_pwd), s_obj['id']))
                            else:
                                cursor.execute("UPDATE users SET full_name=?, username=? WHERE id=?", (new_name, new_uname, s_obj['id']))
                            conn.commit()
                            st.success("Updated!")
                            st.rerun()
            else: st.info("No students available.")
    except sqlite3.Error as e: st.error(f"CRUD Error: {e}")
    finally: conn.close()

def teacher_tab_ai_insights():
    st.subheader("🤖 AI Educator Insights & Risk Monitor")
    st.markdown("---")
    conn = get_db_connection()
    try:
        # AI Report Summary
        st.markdown(ai_generate_report(conn))
        
        st.divider()
        st.markdown("### 📉 AI Predictive Risk Alerts")
        cursor = conn.cursor()
        cursor.execute("SELECT id, full_name FROM users WHERE role='student'")
        students = cursor.fetchall()
        
        risk_data = []
        for s in students:
            r = ai_predict_risk(conn, s['id'], s['full_name'])
            risk_data.append({"Student": s['full_name'], "Risk %": r['risk'], "Absences (Last 10 days)": r['absences'], "Status": r['warning']})
            
        df = pd.DataFrame(risk_data)
        df = df.sort_values(by="Risk %", ascending=False)
        
        # Color code risk rows
        def color_risk(val):
            color = 'black'
            bg = 'white'
            if val > 30: bg, color = '#f8d7da', 'darkred'
            elif val > 10: bg, color = '#fff3cd', 'black'
            return f'background-color: {bg}; color: {color}; font-weight: bold;'
            
        styled_df = df.style.map(color_risk, subset=['Risk %'])
        st.dataframe(styled_df, use_container_width=True)
        
        st.info("💡 *AI Note: Students with >30% risk score should be prioritized for intervention this week.*")
    except sqlite3.Error as e: st.error(f"Insight Error: {e}")
    finally: conn.close()

def teacher_tab_analytics():
    st.subheader("📊 Macro-Level Analytics")
    st.markdown("---")
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT date, SUM(CASE WHEN status='Present' THEN 1 ELSE 0 END) as p, COUNT(*) as t FROM attendance GROUP BY date ORDER BY date ASC")
        data = cursor.fetchall()
        if not data: return st.info("No data.")
        
        df = pd.DataFrame([dict(r) for r in data])
        df['rate'] = (df['p'] / df['t']) * 100
        fig = px.bar(df, x='date', y='rate', title='Daily Class Attendance Rate (%)', color='rate', color_continuous_scale='RdYlGn')
        fig.update_layout(xaxis_tickangle=-45)
        st.plotly_chart(fig, use_container_width=True)
    except sqlite3.Error as e: st.error(f"Analytics Error: {e}")
    finally: conn.close()

# --- Main App ---
def main():
    st.set_page_config(layout="wide", page_title="AI AMS")
    init_database()
    seed_mock_data()
    
    if "offline_cache" not in st.session_state: st.session_state.offline_cache = []
    if "user" not in st.session_state: st.session_state.user = None

    if st.session_state.user is None:
        st.title("🤖 University AI Attendance Management")
        with st.container():
            with st.form("login"):
                u = st.text_input("Username")
                p = st.text_input("Password", type="password")
                if st.form_submit_button("Login", type="primary", use_container_width=True):
                    user = authenticate_user(u, p)
                    if user: 
                        st.session_state.user = user
                        st.rerun()
                    else: st.error("Invalid credentials.")
        st.caption("Teacher: `admin` / `admin123` | Student: `student1` / `123456`")
        return

    user = st.session_state.user
    st.sidebar.title(f"Welcome, {user['full_name']}")
    st.sidebar.markdown(f"Role: {'👨‍🏫 Teacher' if user['role'] == 'teacher' else '🧑‍🎓 Student'}")
    if st.sidebar.button("🚪 Logout"): st.session_state.user = None; st.rerun()

    if user['role'] == 'student':
        tab1, tab2, tab3, tab4 = st.tabs(["✅ Check-In", "📶 Offline", "🤖 AI Advisor", "📊 My Stats"])
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
