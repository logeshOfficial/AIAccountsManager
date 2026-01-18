import sqlite3
import json 
import pandas as pd

DB_PATH = "invoices.db"
TOKEN_DB_PATH = "/mount/src/oauth_tokens.db"


def get_connection():
    return sqlite3.connect(DB_PATH, check_same_thread=False)

def get_connection_for_token_db():
    return sqlite3.connect(TOKEN_DB_PATH, check_same_thread=False)

def init_token_db():
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS google_tokens (
            user_id TEXT PRIMARY KEY,
            token_json TEXT NOT NULL
        )
    """)

    conn.commit()
    conn.close()

def save_token(user_id: str, token_json: str):
    init_token_db()
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("""
        INSERT OR REPLACE INTO google_tokens (user_id, token_json)
        VALUES (?, ?)
    """, (user_id, token_json))

    conn.commit()
    conn.close()

def load_token(user_id: str):
    init_token_db()
    
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("""
        SELECT token_json FROM google_tokens WHERE user_id = ?
    """, (user_id,))

    row = cur.fetchone()
    conn.close()

    return row[0] if row else None

def delete_token(user_id: str):
    init_token_db()
    
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("""
        DELETE FROM google_tokens WHERE user_id = ?
    """, (user_id,))

    conn.commit()
    conn.close()
    
def init_db():
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("""
    CREATE TABLE IF NOT EXISTS invoices (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        file_id TEXT,
        file_name TEXT,
        invoice_number TEXT,
        invoice_date TEXT,
        gst_number TEXT
        vendor_name TEXT,
        description TEXT,
        total_amount REAL,
        raw_text TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)

    conn.commit()
    conn.close()

def insert_invoice(invoice):
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("""
    INSERT INTO invoices (
        file_id,
        file_name,
        invoice_number,
        invoice_date,
        gst_number,
        vendor_name,
        description,
        total_amount,
        raw_text
    )
    VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (
        invoice["_file"]["id"],
        invoice["_file"]["name"],
        invoice.get("invoice_number"),
        invoice.get("invoice_date"),
        invoice.get("gst_number"),
        invoice.get("vendor_name"),
        invoice.get("description"),
        float(invoice.get("total_amount", 0)),
        json.dumps(invoice.get("raw_text", ""))
    ))

    conn.commit()
    conn.close()
