import sqlite3
import json 
import pandas as pd


DB_PATH = "invoices.db"

def get_connection():
    return sqlite3.connect(DB_PATH, check_same_thread=False)

def get_data():
    conn = sqlite3.connect("invoices.db")
    df = pd.read_sql("SELECT * FROM invoices ORDER BY created_at DESC", conn)
    return df

def insert_token(token):
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("""
                INSERT INTO TOKEN (flow)
                VALUES (?)
                """, (token))
    
    conn.commit()
    conn.close()

def init_token_db():
    conn = get_connection()
    cur = conn.cursor()

    cur.execute(""" 
        CREATE TABLE IF NOT EXISTS TOKEN (
            flow TEXT
        ,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)
        """)
    
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
