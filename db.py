import sqlite3
import json 
import pandas as pd
import os
from typing import Tuple
from app_logger import get_logger

logger = get_logger(__name__)

DB_PATH = "/mount/src/invoices.db"


def get_connection():
    try:
        return sqlite3.connect(DB_PATH, check_same_thread=False)
    except Exception as e:
        logger.error(f"Error while get_connection: {e}")
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
            
        if "extraction_method" not in cols:
            cur.execute("ALTER TABLE invoices ADD COLUMN extraction_method TEXT")

        # Index for per-user queries
        cur.execute("CREATE INDEX IF NOT EXISTS idx_invoices_user_id ON invoices(user_id)")

        conn.commit()
    
    except Exception as e:
        raise Exception("Error while init_db: ", e)

    finally:
        conn.close()

def check_invoice_exists(file_id: str) -> bool:
    """Checks if an invoice with the given file_id already exists."""
    init_db()
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("SELECT 1 FROM invoices WHERE file_id = ?", (file_id,))
        exists = cur.fetchone() is not None
        return exists
    except Exception as e:
        logger.error(f"Error checking invoice existence: {e}")
        return False
    finally:
        if 'conn' in locals():
            conn.close()
        
def insert_invoice(invoice, user_id: str):
    init_db()
    
    # 1. Check for duplicates
    if check_invoice_exists(invoice["_file"]["id"]):
        logger.info(f"Skipping duplicate invoice: {invoice['_file']['name']} (ID: {invoice['_file']['id']})")
        return

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
            raw_text,
            extraction_method
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            user_id,
            invoice["_file"]["id"],
            invoice["_file"]["name"],
            invoice.get("invoice_number"),
            invoice.get("invoice_date"),
            invoice.get("gst_number"),
            invoice.get("vendor_name"),
            invoice.get("description"),
            invoice.get("total_amount", 0),
            json.dumps(invoice.get("raw_text", "")),
            invoice.get("extraction_method", "Unknown")
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

def delete_user_data(user_id: str) -> Tuple[bool, str]:
    """
    Deletes all invoices associated with a specific user_id.
    """
    init_db()
    try:
        conn = get_connection()
        cur = conn.cursor()
        
        # Check count before deleting
        cur.execute("SELECT COUNT(*) FROM invoices WHERE user_id = ?", (user_id,))
        count = cur.fetchone()[0]
        
        if count == 0:
            logger.info(f"User {user_id} attempted delete, but no records found.")
            return True, "No records found to delete."
            
        cur.execute("DELETE FROM invoices WHERE user_id = ?", (user_id,))
        conn.commit()
        conn.close()
        
        logger.info(f"User {user_id} deleted their data ({count} records).")
        return True, f"Successfully deleted {count} records."
        
    except Exception as e:
        logger.error(f"Failed to delete data for user {user_id}: {e}")
        return False, f"Error deleting data: {e}" 

def drop_invoices_db(recreate: bool = True) -> Tuple[bool, str]:
    """
    Deletes the invoices sqlite database file at DB_PATH.

    Args:
        recreate: If True, re-create the DB file and invoices table after deletion.

    Returns:
        (success, message)
    """
    # Best-effort close of any open connections happens at call sites; here we just try to delete.
    # Best-effort close of any open connections happens at call sites; here we just try to delete.
    try:
        user_param = "Admin" # distinct from regular user delete
        if os.path.exists(DB_PATH):
            os.remove(DB_PATH)
            logger.warning(f"Database dropped by {user_param}")
        else:
            # Treat "doesn't exist" as success for idempotency
            if recreate:
                init_db()
            logger.info(f"Drop DB requested, but DB not found. Schema recreated: {recreate}")
            return True, f"DB not found at {DB_PATH}. Recreated schema." if recreate else f"DB not found at {DB_PATH}."

        if recreate:
            init_db()
            return True, f"Deleted and recreated DB at {DB_PATH}."

        return True, f"Deleted DB at {DB_PATH}."
    except PermissionError as e:
        return False, f"Permission error deleting DB at {DB_PATH}. Is it open elsewhere? ({e})"
    except Exception as e:
        return False, f"Failed to delete DB at {DB_PATH}: {e}"