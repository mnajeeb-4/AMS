# 🤖 AI-Powered Attendance Management System (AMS)

A futuristic, production-ready Attendance Management System built with Streamlit. Features distinct Student and Teacher portals, a simulated **AI Risk Predictor**, **NLP Mood Check-In**, and **Enterprise-grade Attendance Matrices**. Designed for the modern university with strict data privacy and zero external API dependencies.

## 🚀 Core AI & Futuristic Features
*   **AI Mood Check-In (NLP Simulator):** Students can type how they feel (e.g., "I have a fever"). The AI auto-suggests `Leave` or `Absent` statuses using rule-based keyword analysis.
*   **Predictive Risk Assessment (Teacher):** Uses historical data to calculate risk percentages for students dropping below attendance thresholds, helping early intervention.
*   **AI Performance Advisor (Student):** Analyzes real-time streaks and stats to provide empathetic, actionable motivational messages.
*   **AI Class Health Report:** Auto-generates a natural language summary of class performance, highlighting areas needing immediate attention.
*   **Offline Mode:** Resilient offline caching ensuring zero data loss during network outages.

## 📁 Project Structure
```text
AMS-AI/
├── app.py              # Main application (Single-file architecture)
├── requirements.txt    # Python dependencies
├── README.md           
└── attendance_system.db # Auto-generated on first run
