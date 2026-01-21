import streamlit as st
import pandas as pd
from datetime import datetime
from dateutil import parser
from typing import List, Dict, Any, Tuple, Optional
import db
from app_logger import get_logger

logger = get_logger(__name__)

def load_invoices_from_db(user_email: str) -> List[Dict[str, Any]]:
    """Loads invoices from the database and adapts them to the expected schema."""
    if not user_email:
        return []
    
    try:
        # Check if user is admin
        admin_email = st.secrets.get("admin_email", "").strip().lower()
        is_admin = (user_email or "").strip().lower() == admin_email
        
        df = db.read_db(user_id=user_email, is_admin=is_admin)
        records = df.to_dict(orient="records")
        
        # Map DB columns to Chatbot Schema
        adapted_records = []
        for r in records:
            adapted_records.append({
                "invoice_no": r.get("invoice_number", ""),
                "invoice_date": r.get("invoice_date", ""),
                "invoice_description": r.get("description", ""),
                "total_amount": r.get("total_amount", 0),
                "vendor_name": r.get("vendor_name", ""),
                "gst_number": r.get("gst_number", ""),
                "raw_text": r.get("raw_text", "")
            })
        return adapted_records
        
    except Exception as e:
        logger.error(f"Error loading invoices: {e}")
        st.error(f"Error loading invoices: {e}")
        return []

def filter_by_invoice_number(invoices: List[Dict], invoice_number: str) -> List[Dict]:
    normalized = invoice_number.strip().lower()
    return [
        inv for inv in invoices
        if str(inv.get("invoice_no", "")).strip().lower() == normalized
    ]

def filter_by_date_and_category(
    invoices: List[Dict], 
    start_date: datetime, 
    end_date: datetime, 
    category: Optional[str] = None
) -> Tuple[List[Dict], Optional[Dict], Optional[Dict]]:
    
    filtered = []
    
    for inv in invoices:
        date_str = inv.get("invoice_date", "")
        if not date_str:
            continue

        try:
            inv_date = parser.parse(date_str.strip())
        except Exception:
            # Log specific parsing failures to help debug if needed
            continue
        
        if not inv_date:
            continue

        if start_date <= inv_date <= end_date:
            if not category or inv.get("invoice_description", "").lower() == category.lower():
                filtered.append(inv)

    min_inv = None
    max_inv = None
    
    if filtered:
        min_inv = min(filtered, key=lambda x: float(x.get("total_amount", 0)))
        max_inv = max(filtered, key=lambda x: float(x.get("total_amount", 0)))

    return filtered, min_inv, max_inv

def calculate_total_amount(invoices: List[Dict]) -> float:
    return round(sum(float(inv.get("total_amount", 0)) for inv in invoices), 2)
