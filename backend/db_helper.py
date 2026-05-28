import sqlite3
import os
import json
from datetime import datetime

DB_PATH = os.path.join(os.path.dirname(__file__), 'monitor.db')

def get_db_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db_connection()
    cursor = conn.cursor()
    # Create services table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS services (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            url TEXT NOT NULL,
            expected_codes TEXT NOT NULL DEFAULT '200',
            tag TEXT DEFAULT 'custom',
            description TEXT,
            notify_email TEXT,
            active INTEGER DEFAULT 1,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );
    ''')
    # Run migrations if columns do not exist
    try:
        cursor.execute("ALTER TABLE services ADD COLUMN description TEXT;")
    except sqlite3.OperationalError:
        pass
    try:
        cursor.execute("ALTER TABLE services ADD COLUMN notify_email TEXT;")
    except sqlite3.OperationalError:
        pass
    # Create checks table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS checks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            service_id INTEGER NOT NULL,
            status TEXT NOT NULL,
            http_code INTEGER,
            latency_ms INTEGER,
            note TEXT,
            checked_at TEXT DEFAULT CURRENT_TIMESTAMP
        );
    ''')
    # Create alerts table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS alerts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            service_id INTEGER NOT NULL,
            previous_status TEXT,
            new_status TEXT,
            message TEXT,
            sent_at TEXT DEFAULT CURRENT_TIMESTAMP
        );
    ''')
    conn.commit()
    conn.close()

# Helper query executions
def query_db(query, args=(), one=False):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(query, args)
    rv = cursor.fetchall()
    conn.commit()
    conn.close()
    return (rv[0] if rv else None) if one else rv

def execute_db(query, args=()):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(query, args)
    conn.commit()
    last_row_id = cursor.lastrowid
    conn.close()
    return last_row_id
