import re
from dateutil import parser
from typing import Optional, Tuple, List, Dict
from app_logger import get_logger

logger = get_logger(__name__)

def normalize_date(date_str: str) -> str:
    """Normalizes invoice date to standard format: DD-Mon-YYYY (e.g., 12-Sep-2025)."""
    if not date_str:
        return ""
    try:
        dt = parser.parse(str(date_str).strip(), dayfirst=True, fuzzy=True)
        return dt.strftime("%d-%b-%Y")
    except Exception as e:
        logger.debug(f"Normalization failed for date '{date_str}': {e}")
        return date_str

def extract_year_month(date_str: str) -> Tuple[Optional[int], Optional[str]]:
    """Extracts year and month name from a date string."""
    try:
        dt = parser.parse(date_str, dayfirst=True)
        return dt.year, dt.strftime("%B")
    except Exception:
        return None, None

def clean_amount(amount_str: str) -> float:
    """Cleans a string amount and returns a float."""
    if amount_str is None:
        return 0.0
    try:
        # Remove currency symbols (like ₹, $, RM) and non-numeric chars except .
        clean_str = re.sub(r"[^\d.]", "", str(amount_str).replace(",", "").replace("₹", ""))
        return float(clean_str) if clean_str else 0.0
    except Exception:
        return 0.0

def is_valid_invoice_amount(total: any) -> bool:
    """Checks if the total amount represents a valid invoice (> 0)."""
    val = clean_amount(total)
    return val > 0

def regex_parse_invoice(text: str) -> Dict[str, str]:
    """Fallback regex-based parser for invoice data."""
    lines = text.split("\n")
    data = {
        "invoice_number": "",
        "invoice_date": "",
        "gst_number": "",
        "vendor_name": "",
        "total_amount": "",
        "description": "General Retail",
        "raw_text": text,
        "extraction_method": "Regex (Manual)"
    }
    
    # Optimized regex for invoice numbers
    inv_match = re.search(r'(?:invoice|bill|challan|#|receipt)\s*(?:no|number|#)?\s*:?\s*([A-Z0-9\-/]+)', text, re.I)
    if inv_match: data["invoice_number"] = inv_match.group(1).strip()
    
    date_match = re.search(r'(?:date|dated|journey|boarding)\s*:?\s*([0-9]{1,2}[/\-\.\s]+(?:[0-9]{1,2}|[A-Za-z]{3})[/\-\.\s]+[0-9]{2,4})', text, re.I)
    if date_match: 
        data["invoice_date"] = normalize_date(date_match.group(1))
    else:
        # Fallback date search for orphaned dates (like 12-Sep-2025)
        orphaned_date = re.search(r'(\d{1,2}-[A-Za-z]{3}-\d{4})', text)
        if orphaned_date: data["invoice_date"] = normalize_date(orphaned_date.group(1))
    
    gst_match = re.search(r'(?:gst|gstin)\s*:?\s*([0-9A-Z]{15})', text, re.I)
    if gst_match: data["gst_number"] = gst_match.group(1).strip()
    
    # Enhanced amount search: 
    # Try IRCTC specific "Total Fare" first
    fare_match = re.search(r'(?:total fare|ticket fare|all inclusive)\s*[^\d₹]*(\d+,?\d*\.?\d*)', text, re.I)
    if fare_match:
        data["total_amount"] = fare_match.group(1).replace(",", "")
    else:
        # General amount search
        amounts = re.findall(r'(?:total|grand total|amount due|fare)\s*:?\s*[^\d₹]*([\d,]+\.?\d*)', text, re.I)
        if amounts:
            # Pick the largest amount found near "total" words, to skip small fees
            data["total_amount"] = max([float(a.replace(",", "")) for a in amounts])
    
    return data
