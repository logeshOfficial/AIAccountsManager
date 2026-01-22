import streamlit as st
from supabase import create_client, Client
import json 
import pandas as pd
from typing import Tuple, Optional
import datetime
from app_logger import get_logger, IST

logger = get_logger(__name__)

@st.cache_resource
def get_supabase_client() -> Optional[Client]:
    """Initializes and returns the Supabase client."""
    url = st.secrets.get("supabase_url")
    key = st.secrets.get("supabase_key")
    
    if not url or not key:
        return None
        
    try:
        return create_client(url, key)
    except Exception as e:
        logger.error(f"Failed to initialize Supabase client: {e}")
        return None

def init_db():
    """
    Supabase handles table creation via the dashboard or SQL editor.
    This function remains as a placeholder or for remote table validation.
    """
    pass

def check_invoice_exists(file_id: str) -> bool:
    """Checks if an invoice with the given file_id already exists in Supabase."""
    client = get_supabase_client()
    if not client:
        return False
        
    try:
        response = client.table("invoices").select("file_id").eq("file_id", file_id).execute()
        return len(response.data) > 0
    except Exception as e:
        logger.error(f"Error checking invoice existence in Supabase: {e}")
        return False

def insert_invoice(invoice, user_id: str):
    """Inserts a new invoice record into Supabase."""
    client = get_supabase_client()
    if not client:
        logger.error("Supabase client not initialized. Cannot insert invoice.")
        return

    # 1. Check for duplicates
    if check_invoice_exists(invoice["_file"]["id"]):
        logger.info(f"Skipping duplicate invoice: {invoice['_file']['name']} (ID: {invoice['_file']['id']})")
        return

    ts = datetime.datetime.now(IST).strftime("%Y-%m-%d %H:%M:%S %Z")
    try:
        data = {
            "user_id": user_id,
            "file_id": invoice["_file"]["id"],
            "file_name": invoice["_file"]["name"],
            "invoice_number": invoice.get("invoice_number"),
            "invoice_date": invoice.get("invoice_date"),
            "gst_number": invoice.get("gst_number"),
            "vendor_name": invoice.get("vendor_name"),
            "description": invoice.get("description"),
            "total_amount": float(invoice.get("total_amount", 0) or 0),
            "raw_text": invoice.get("raw_text", ""),
            "extraction_method": invoice.get("extraction_method", "Unknown"),
            "timestamp": ts 
        }
        
        client.table("invoices").insert(data).execute()
        logger.info(f"Successfully inserted invoice to Supabase: {invoice['_file']['name']}", extra={"user_id": user_id})
        
    except Exception as e:
        logger.error(f"Error while insert_invoice to Supabase: {e}")
        raise Exception(f"Error while insert_invoice to Supabase: {e}")

def read_db(user_id: str | None = None, is_admin: bool = False):
    """Reads invoice data from Supabase."""
    client = get_supabase_client()
    if not client:
        return pd.DataFrame([])

    try:
        query = client.table("invoices").select("*")
        
        if is_admin:
            # Admins see everything
            response = query.order("created_at", desc=True).execute()
        else:
            if not user_id:
                return pd.DataFrame([])
            # Filter by user_id
            response = query.eq("user_id", user_id).order("created_at", desc=True).execute()
            
        return pd.DataFrame(response.data)

    except Exception as e:
        logger.error(f"Error while read_db from Supabase: {e}")
        return pd.DataFrame([])

def delete_user_data(user_id: str) -> Tuple[bool, str]:
    """Deletes all invoices associated with a specific user_id in Supabase."""
    client = get_supabase_client()
    if not client:
        return False, "Supabase client not initialized."

    try:
        # Check count first
        response_count = client.table("invoices").select("file_id", count="exact").eq("user_id", user_id).execute()
        count = response_count.count
        
        if count == 0:
            return True, "No records found to delete."
            
        client.table("invoices").delete().eq("user_id", user_id).execute()
        
        logger.info(f"User {user_id} deleted their data ({count} records) from Supabase.", extra={"user_id": user_id})
        return True, f"Successfully deleted {count} records."
        
    except Exception as e:
        logger.error(f"Failed to delete Supabase data for user {user_id}: {e}")
        return False, f"Error deleting data: {e}" 

def drop_invoices_db(recreate: bool = True) -> Tuple[bool, str]:
    """
    Drops all records from the invoices table in Supabase.
    (Postgres tables aren't usually 'dropped' dynamically in a production app).
    """
    client = get_supabase_client()
    if not client:
        return False, "Supabase client not initialized."

    try:
        # Delete all rows
        client.table("invoices").delete().neq("file_id", "force_all_delete").execute()
        logger.warning("Database cleared (all records deleted) in Supabase.")
        return True, "Successfully cleared all records from Supabase."
    except Exception as e:
        logger.error(f"Failed to clear Supabase table: {e}")
        return False, f"Failed to clear database: {e}"