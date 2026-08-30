import sqlite3
import os
import json
from datetime import datetime
from typing import List, Optional

DB_PATH = os.path.join(os.path.dirname(__file__), "controlplane.db")

def init_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS audit_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            session_id TEXT,
            prompt TEXT NOT NULL,
            raw_output TEXT,
            cp_verdict TEXT,
            risk_score REAL,
            trigger_engine TEXT
        )
    ''')
    conn.commit()
    conn.close()

def log_incident(
    session_id: str,
    prompt: str,
    raw_output: str,
    cp_verdict: str,
    risk_score: float,
    trigger_engine: str
):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO audit_logs (timestamp, session_id, prompt, raw_output, cp_verdict, risk_score, trigger_engine)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    ''', (datetime.utcnow().isoformat(), session_id, prompt, raw_output, cp_verdict, risk_score, trigger_engine))
    conn.commit()
    conn.close()

# Initialize on import
init_db()
