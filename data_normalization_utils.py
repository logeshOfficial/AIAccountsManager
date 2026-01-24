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

def clean_invoice_number(inv_str: str) -> str:
    """
    Cleans an invoice number string by removing common labels,
    prefixes, and unwanted symbols while preserving alphanumeric characters.
    """
    if not inv_str:
        return ""
    
    # Common labels/prefixes to remove (case-insensitive)
    labels = [
        r"invoice\s*no\.?", r"invoice\s*number", r"bill\s*no\.?", r"bill\s*number",
        r"challan\s*no\.?", r"challan\s*number", r"receipt\s*no\.?", r"receipt\s*number",
        r"inv\s*#", r"bill\s*#", r"no\.?", r"num\.?", r"#"
    ]
    
    cleaned = str(inv_str).strip()
    
    # Remove labels from the beginning
    for label in labels:
        cleaned = re.sub(f"^{label}\s*:?\s*", "", cleaned, flags=re.I)
    
    # Remove noise at the end or around
    cleaned = re.sub(r"^[:\s]+|[:\s]+$", "", cleaned)
    
    return cleaned.strip()

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
    inv_match = re.search(r'(?:invoice|bill|challan|#|receipt|inv)\s*(?:no|number|#)?\s*:?\s*([A-Z0-9\-/]+)', text, re.I)
    if inv_match: 
        data["invoice_number"] = clean_invoice_number(inv_match.group(1))
    
    date_match = re.search(r'(?:date|dated|journey|boarding|boarding\s*date)\s*:?\s*([0-9]{1,2}[/\-\.\s]+(?:[0-9]{1,2}|[A-Za-z]{3})[/\-\.\s]+[0-9]{2,4})', text, re.I)
    if date_match: 
        data["invoice_date"] = normalize_date(date_match.group(1))
    else:
        # Fuzzy fallback for orphaned dates (like 12-Sep-2025 or 12/09/2025)
        orphaned_date = re.search(r'(\d{1,2}[-/](?:[A-Za-z]{3}|\d{1,2})[-/]\d{2,4})', text)
        if orphaned_date: data["invoice_date"] = normalize_date(orphaned_date.group(1))
    
    gst_match = re.search(r'(?:gst|gstin)\s*:?\s*([0-9A-Z]{15})', text, re.I)
    if gst_match: data["gst_number"] = gst_match.group(1).strip()
    
    # Enhanced Universal Amount Search (Fuzzy & Greedy): 
    # Stage 1: Search with high-priority business keywords (includes retail and travel)
    priority_amount_patterns = [
        r'(?:total invoice value|invoice value|total fare|ticket fare|fare\s*\(all\s*inclusive\))\s*[^\d₹$]*([\d,]+\.?\d*)',
        r'(?:grand total|total amount|amount due|total payment|amount payable)\s*:?\s*[^\d₹$]*([\d,]+\.?\d*)'
    ]
    
    found_amounts = []
    for pattern in priority_amount_patterns:
        matches = re.findall(pattern, text, re.I)
        for m in matches:
            val = clean_amount(m)
            if val > 0: found_amounts.append(val)
    
    if found_amounts:
        # Strategy: Pick the largest amount to ensure tax/sub-totals are ignored
        data["total_amount"] = str(max(found_amounts))
    else:
        # Ultimate fallback: look for any line containing "total" followed by a decimal number
        total_line_match = re.search(r'total.*?(?:[:₹$])\s*([\d,]+\.\d{2})', text, re.I)
        if total_line_match:
            data["total_amount"] = total_line_match.group(1).replace(",", "")
    
    return data
