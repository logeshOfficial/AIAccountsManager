import sqlite3
import json 
import pandas as pd
import os
from typing import Tuple

DB_PATH = "/mount/src/invoices.db"
ADMIN_EMAIL = "iamlogeshwaran.info@gmail.com"


def get_connection():
    try:
        return sqlite3.connect(DB_PATH, check_same_thread=False)
    except Exception as e:
        raise Exception("Error while get_connection: ", e)
    
def init_db():
    try:
        conn = get_connection()
        cur = conn.cursor()

        cur.execute("""
        CREATE TABLE IF NOT EXISTS invoices (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT,
            file_id TEXT,
            file_name TEXT,
            invoice_number TEXT,
            invoice_date TEXT,
            gst_number TEXT,
            vendor_name TEXT,
            description TEXT,
            total_amount REAL,
            raw_text TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """)

        # Lightweight migration: if DB already existed without user_id, add it.
        cols = [r[1] for r in cur.execute("PRAGMA table_info(invoices)").fetchall()]
        if "user_id" not in cols:
            cur.execute("ALTER TABLE invoices ADD COLUMN user_id TEXT")

        # Index for per-user queries
        cur.execute("CREATE INDEX IF NOT EXISTS idx_invoices_user_id ON invoices(user_id)")

        conn.commit()
    
    except Exception as e:
        raise Exception("Error while init_db: ", e)

    finally:
        conn.close()
        
def insert_invoice(invoice, user_id: str):
    init_db()
    
    try:
        conn = get_connection()
        cur = conn.cursor()

        cur.execute("""
        INSERT INTO invoices (
            user_id,
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
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            user_id,
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
        
    except Exception as e:
        raise Exception("Error while insert_invoice: ",e)
    
    finally:
        conn.close()
    
def read_db(user_id: str | None = None, is_admin: bool = False):
    init_db()
    
    try:
        conn = get_connection()

        if is_admin:
            df = pd.read_sql("SELECT * FROM invoices ORDER BY created_at DESC", conn)
        else:
            if not user_id:
                df = pd.DataFrame([])
            else:
                df = pd.read_sql(
                    "SELECT * FROM invoices WHERE user_id = ? ORDER BY created_at DESC",
                    conn,
                    params=(user_id,),
                )
        
        conn.close()

    except Exception as e:
        raise Exception("Error while read_db: ",e)
    
    finally:
        return df 

def drop_invoices_db(recreate: bool = True) -> Tuple[bool, str]:
    """
    Deletes the invoices sqlite database file at DB_PATH.

    Args:
        recreate: If True, re-create the DB file and invoices table after deletion.

    Returns:
        (success, message)
    """
    # Best-effort close of any open connections happens at call sites; here we just try to delete.
    try:
        if os.path.exists(DB_PATH):
            os.remove(DB_PATH)
        else:
            # Treat "doesn't exist" as success for idempotency
            if recreate:
                init_db()
            return True, f"DB not found at {DB_PATH}. Recreated schema." if recreate else f"DB not found at {DB_PATH}."

        if recreate:
            init_db()
            return True, f"Deleted and recreated DB at {DB_PATH}."

        return True, f"Deleted DB at {DB_PATH}."
    except PermissionError as e:
        return False, f"Permission error deleting DB at {DB_PATH}. Is it open elsewhere? ({e})"
    except Exception as e:
        return False, f"Failed to delete DB at {DB_PATH}: {e}"