import os
import io
import json
import re
from dateutil import parser
import tempfile
import fitz  # PyMuPDF
from typing import Optional, Tuple
from googleapiclient.http import MediaIoBaseDownload
from collections import defaultdict
import ai_models
from dotenv import load_dotenv
# import google.generativeai as genai
import streamlit as st
from app_logger import get_logger
from llm_manager import llm_call

logger = get_logger(__name__)

load_dotenv()

class InvoiceProcessor:
    def __init__(self):
        self.reader = None

        self.year_month_data = defaultdict(lambda: defaultdict(list))
        
    # ================= LLM Call =================
    def safe_json_load(self, text):
        if not text or not text.strip():
            raise ValueError("LLM returned empty response")
        try:
            return json.loads(text)
        except:
            match = re.search(r'\[.*\]', text, re.S)
            if match:
                return json.loads(match.group())
            raise
        
    # ================= Invoice Extraction Logic =================
    def extract_year_month(self, date_str):
        try:
            dt = parser.parse(date_str, dayfirst=True)
            return dt.year, dt.strftime("%B")
        except:
            return None, None

    def format_date(self, invoice_date):
        if not invoice_date:
            return ""
        try:
            dt = parser.parse(invoice_date, dayfirst=True)
            return dt.strftime("%b %d %Y")
        except:
            return invoice_date

    def is_valid_invoice(self, total):
        try:
            if total is None:
                return False

            total = re.sub(r"[^\d.]", "", str(total))
            if total == "":
                return False

            return float(total) > 0
        except:
            return False
    
    # ================= Manual Invoice Parser (Replaces LLM) =================
    def parse_invoices_manual(self, invoice_texts):
        """
        Manually parse invoice texts to extract structured data.
        Replaces LLM-based conversion with regex and pattern matching.
        
        Args:
            invoice_texts: List of invoice text (list of lines or string)
            
        Returns:
            List of dictionaries with invoice data
        """
        parsed_invoices = []
        
        for invoice_text in invoice_texts:
            # Convert to string if it's a list of lines
            if isinstance(invoice_text, list):
                full_text = "\n".join(invoice_text)
                lines = invoice_text
            else:
                full_text = str(invoice_text)
                lines = full_text.split("\n")
            
            invoice_data = {
                "invoice_number": "",
                "invoice_date": "",
                "gst_number": "",
                "vendor_name": "",
                "total_amount": "",
                "description": "",
                "raw_text": full_text
            }
            
            # Extract invoice number
            invoice_patterns = [
                r'invoice\s*(?:number|no|#|num)?\s*:?\s*([A-Z0-9\-/]+)',
                r'challan\s*(?:number|no|#)?\s*:?\s*([A-Z0-9\-/]+)',
                r'bill\s*(?:number|no|#)?\s*:?\s*([A-Z0-9\-/]+)',
                r'invoice\s*#\s*([A-Z0-9\-/]+)',
                r'do\s*no\s*:?\s*([A-Z0-9\-/]+)',
                r'inv\s*:?\s*([A-Z0-9\-/]+)',
            ]
            
            for pattern in invoice_patterns:
                match = re.search(pattern, full_text, re.IGNORECASE)
                if match:
                    invoice_data["invoice_number"] = match.group(1).strip()
                    break
            
            # Extract invoice date - comprehensive pattern matching
            date_patterns = [
                # Patterns with "date" keyword and separators
                r'invoice\s*date\s*:?\s*([0-9]{1,2}[/\-\.\s]+[0-9]{1,2}[/\-\.\s]+[0-9]{2,4})',
                r'date\s*:?\s*([0-9]{1,2}[/\-\.\s]+[0-9]{1,2}[/\-\.\s]+[0-9]{2,4})',
                r'Date\s*:?\s*([0-9]{1,2}[/\-\.\s]+[0-9]{1,2}[/\-\.\s]+[0-9]{2,4})',
                r'bill\s*date\s*:?\s*([0-9]{1,2}[/\-\.\s]+[0-9]{1,2}[/\-\.\s]+[0-9]{2,4})',
                r'dated\s*:?\s*([0-9]{1,2}[/\-\.\s]+[0-9]{1,2}[/\-\.\s]+[0-9]{2,4})',
                # Patterns with month names
                r'invoice\s*date\s*:?\s*([0-9]{1,2}\s+[A-Za-z]{3,9}\s+[0-9]{2,4})',
                r'date\s*:?\s*([0-9]{1,2}\s+[A-Za-z]{3,9}\s+[0-9]{2,4})',
                r'Date\s*:?\s*([0-9]{1,2}\s+[A-Za-z]{3,9}\s+[0-9]{2,4})',
                r'bill\s*date\s*:?\s*([0-9]{1,2}\s+[A-Za-z]{3,9}\s+[0-9]{2,4})',
                r'dated\s*:?\s*([0-9]{1,2}\s+[A-Za-z]{3,9}\s+[0-9]{2,4})',
                # Patterns with month names first
                r'invoice\s*date\s*:?\s*([A-Za-z]{3,9}\s+[0-9]{1,2},?\s+[0-9]{2,4})',
                r'date\s*:?\s*([A-Za-z]{3,9}\s+[0-9]{1,2},?\s+[0-9]{2,4})',
                r'Date\s*:?\s*([A-Za-z]{3,9}\s+[0-9]{1,2},?\s+[0-9]{2,4})',
            ]
            
            for pattern in date_patterns:
                match = re.search(pattern, full_text, re.IGNORECASE)
                if match:
                    date_str = match.group(1).strip()
                    try:
                        # Try to parse and format the date
                        dt = parser.parse(date_str, dayfirst=True, fuzzy=True)
                        invoice_data["invoice_date"] = dt.strftime("%b %d %Y")
                        break
                    except Exception as e:
                        # If parsing fails, try to clean and parse again
                        try:
                            # Remove extra spaces and commas
                            cleaned_date = re.sub(r'\s+', ' ', date_str.replace(',', '')).strip()
                            dt = parser.parse(cleaned_date, dayfirst=True, fuzzy=True)
                            invoice_data["invoice_date"] = dt.strftime("%b %d %Y")
                            break
                        except:
                            pass
            
            # If not found with explicit patterns, search more broadly
            if not invoice_data["invoice_date"]:
                # Search entire text for date-like patterns
                # First try dates with separators
                date_matches = re.findall(r'([0-9]{1,2}[/\-\.][0-9]{1,2}[/\-\.][0-9]{2,4})', full_text)
                for date_str in date_matches:
                    try:
                        dt = parser.parse(date_str, dayfirst=True, fuzzy=True)
                        # Validate it's a reasonable date (not too far in future/past)
                        if 1900 <= dt.year <= 2100:
                            invoice_data["invoice_date"] = dt.strftime("%b %d %Y")
                            break
                    except:
                        pass
                
                # If still not found, try dates with month names
                if not invoice_data["invoice_date"]:
                    month_date_patterns = [
                        r'([0-9]{1,2}\s+[A-Za-z]{3,9}\s+[0-9]{2,4})',  # "20 Dec 2012"
                        r'([A-Za-z]{3,9}\s+[0-9]{1,2},?\s+[0-9]{2,4})',  # "Dec 20, 2012" or "Dec 20 2012"
                    ]
                    for pattern in month_date_patterns:
                        matches = re.findall(pattern, full_text, re.IGNORECASE)
                        for date_str in matches:
                            try:
                                dt = parser.parse(date_str, dayfirst=False, fuzzy=True)
                                if 1900 <= dt.year <= 2100:
                                    invoice_data["invoice_date"] = dt.strftime("%b %d %Y")
                                    break
                            except:
                                pass
                        if invoice_data["invoice_date"]:
                            break
                
                # Last resort: use dateutil's fuzzy parsing on lines that look date-like
                if not invoice_data["invoice_date"]:
                    for line in lines[:15]:  # Check first 15 lines
                        # Look for lines that contain date-like content
                        if re.search(r'\d{1,2}.*\d{2,4}', line):
                            try:
                                dt = parser.parse(line, fuzzy=True, dayfirst=True)
                                if 1900 <= dt.year <= 2100:
                                    invoice_data["invoice_date"] = dt.strftime("%b %d %Y")
                                    break
                            except:
                                pass
                
                # Final fallback: try fuzzy parsing on the entire text (first 500 chars)
                if not invoice_data["invoice_date"]:
                    try:
                        # Use first 500 characters to avoid parsing too much
                        text_sample = full_text[:500] if len(full_text) > 500 else full_text
                        dt = parser.parse(text_sample, fuzzy=True, dayfirst=True)
                        if 1900 <= dt.year <= 2100:
                            invoice_data["invoice_date"] = dt.strftime("%b %d %Y")
                    except:
                        pass
            
            # Extract GST number
            gst_patterns = [
                r'gst\s*(?:number|no|#)?\s*:?\s*([0-9A-Z]{15})',
                r'gstin\s*:?\s*([0-9A-Z]{15})',
                r'gst\s*:?\s*([0-9A-Z]{15})',
            ]
            
            for pattern in gst_patterns:
                match = re.search(pattern, full_text, re.IGNORECASE)
                if match:
                    invoice_data["gst_number"] = match.group(1).strip()
                    break
            
            # Extract vendor name (usually in first few lines or after "from", "vendor", "supplier")
            vendor_patterns = [
                r'(?:from|vendor|supplier|seller|merchant)\s*:?\s*([A-Z][A-Za-z\s&]+)',
                r'^([A-Z][A-Za-z\s&]{3,30})$',  # First line that looks like a company name
            ]
            
            # Check first 5 lines for vendor name
            for i, line in enumerate(lines[:5]):
                for pattern in vendor_patterns:
                    match = re.search(pattern, line, re.IGNORECASE)
                    if match and len(match.group(1).strip()) > 3:
                        invoice_data["vendor_name"] = match.group(1).strip()
                        break
                if invoice_data["vendor_name"]:
                    break
            
            # Extract total amount
            total_patterns = [
                r'total\s*(?:amount|due|payable)?\s*:?\s*[^\d]*([\d,]+\.?\d*)',
                r'grand\s*total\s*:?\s*[^\d]*([\d,]+\.?\d*)',
                r'amount\s*due\s*:?\s*[^\d]*([\d,]+\.?\d*)',
                r'invoice\s*total\s*:?\s*[^\d]*([\d,]+\.?\d*)',
                r'net\s*amount\s*:?\s*[^\d]*([\d,]+\.?\d*)',
                r'\$\s*([\d,]+\.?\d*)',  # USD format
                r'₹\s*([\d,]+\.?\d*)',  # INR format
                r'€\s*([\d,]+\.?\d*)',  # EUR format
                r'RM\s*([\d,]+\.?\d*)',  # MYR format
                r'([\d,]+\.?\d*)\s*(?:total|due|payable)',  # Amount followed by keyword
            ]
            
            # Search from bottom to top (totals are usually at the end)
            # Also check last 10 lines more carefully
            search_lines = lines[-10:] if len(lines) > 10 else lines
            for line in reversed(search_lines):
                for pattern in total_patterns:
                    match = re.search(pattern, line, re.IGNORECASE)
                    if match:
                        amount = match.group(1).replace(",", "").strip()
                        # Validate it's a reasonable amount
                        try:
                            amount_float = float(amount)
                            if amount_float > 0:
                                invoice_data["total_amount"] = amount
                                break
                        except:
                            pass
                if invoice_data["total_amount"]:
                    break
            
            # If still not found, search entire text for currency patterns
            if not invoice_data["total_amount"]:
                currency_patterns = [
                    r'[\$₹€RM]\s*([\d,]+\.?\d{2})',  # Currency symbol with 2 decimal places
                ]
                for pattern in currency_patterns:
                    matches = re.findall(pattern, full_text, re.IGNORECASE)
                    if matches:
                        # Take the largest amount found (likely the total)
                        amounts = [float(m.replace(",", "")) for m in matches]
                        if amounts:
                            max_amount = max(amounts)
                            if max_amount > 0:
                                invoice_data["total_amount"] = str(max_amount)
                                break
            
            # Extract description/category from product/item names
            category_keywords = {
                "Groceries": ["bread", "snack", "beverage", "milk", "rice", "wheat", "flour", "sugar", "tea", "coffee"],
                "Office Supplies": ["pen", "paper", "folder", "stapler", "printer", "ink", "toner", "notebook"],
                "Hardware & Electrical": ["screw", "nail", "wire", "bulb", "switch", "tool", "hammer", "drill"],
                "Personal Care": ["shampoo", "soap", "cream", "lotion", "beauty", "cosmetic", "hair", "skin"],
                "Fashion/Retail": ["shirt", "pant", "dress", "shoe", "cloth", "fabric", "garment"],
                "Food & Dining": ["restaurant", "meal", "food", "dining", "cafe", "pizza", "burger"],
                "Electronics": ["phone", "laptop", "computer", "tablet", "camera", "tv", "electronic"],
            }
            
            full_text_lower = full_text.lower()
            for category, keywords in category_keywords.items():
                if any(keyword in full_text_lower for keyword in keywords):
                    invoice_data["description"] = category
                    break
            
            if not invoice_data["description"]:
                invoice_data["description"] = "General Retail"
            
            parsed_invoices.append(invoice_data)
        
        return parsed_invoices

    def parse_invoices_with_llm(self, invoice_texts):
        """
        Uses LLM to extract structured data from invoice texts.
        This is more robust than regex for varied layouts.
        """
        parsed_invoices = []
        
        for invoice_text in invoice_texts:
            full_text = invoice_text if isinstance(invoice_text, str) else "\n".join(invoice_text)
            
            prompt = f"""
            You are an expert data extractor. Extract the following details from the invoice text below.
            Return ONLY a valid JSON object with these keys:
            - "invoice_number": (string, or empty)
            - "invoice_date": (string, format matching ["Jan 01 2024", "12-Sep-2025", 10 Aug 2000, 2nd Sep 1999, 02-10-2002, 10/12/1999] if possible, else raw)
            - "gst_number": (string, or empty)
            - "vendor_name": (string, name of the seller)
            - "total_amount": (number or string, purely numeric ideally or format matching "₹ 56.00", "$1234.56", "RM 789.00" or next/near to [Total Amount, Total Fare])
            - "description": (string, summary of goods/services, category)
            
            If a field is missing, use an empty string. Do not invent data.
            
            Invoice Text:
            {full_text[:3500]} 
            """
            # Truncated to 3500 chars to fit context window if needed, though most models handle 8k+.
            
            try:
                response_text, model_name = llm_call(prompt)
                
                # Extract JSON from response
                match = re.search(r"\{[\s\S]+\}", response_text)
                if match:
                    data = json.loads(match.group())
                    data["raw_text"] = full_text
                    parsed_invoices.append(data)
                else:
                    # Fallback to manual if LLM fails to output JSON
                    logger.warning(f"LLM did not return JSON. Falling back to manual parse for this doc.")
                    parsed_invoices.extend(self.parse_invoices_manual([full_text]))

            except Exception as e:
                logger.error(f"LLM Parsing failed: {e}")
                # Fallback
                parsed_invoices.extend(self.parse_invoices_manual([full_text]))
                
        return parsed_invoices
        
    def create_and_upload_excel(self,
    drive_manager,
    output_folder_id,
    year,
    months_data
):
        import tempfile, os, time
        import pandas as pd
        from googleapiclient.http import MediaFileUpload

        filename = f"invoices_{year}.xlsx"
        tmp_dir = tempfile.mkdtemp()
        local_path = os.path.join(tmp_dir, filename)

        # --- WRITE EXCEL ---
        with pd.ExcelWriter(local_path, engine="openpyxl", mode="w") as writer:
            sheets_written = False

            for month, invoices in months_data.items():
                if not invoices:
                    continue

                df = pd.DataFrame(invoices)
                df.to_excel(writer, sheet_name=month, index=False)
                sheets_written = True

            if not sheets_written:
                raise RuntimeError("No valid invoice data to write")

        # Ensure file is flushed
        time.sleep(1)

        if not os.path.exists(local_path) or os.path.getsize(local_path) == 0:
            raise RuntimeError("Excel file not created correctly")

        # --- CHECK EXISTING FILE ---
        result = drive_manager.drive_execute(
            drive_manager.service.files().list(
                q=f"name='{filename}' and '{output_folder_id}' in parents and trashed=false",
                fields="files(id)",
                supportsAllDrives=True,
                includeItemsFromAllDrives=True,
            )
        )

        existing = result.get("files", [])
        st.write("existing", existing)
        media = MediaFileUpload(
            local_path,
            mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            resumable=True,
        )

        st.write("media", media)
        
        st.write("Output folder ID:", output_folder_id)

        # --- UPLOAD ---
        if existing:
            request = drive_manager.service.files().update(
                fileId=existing[0]["id"],
                media_body=media,
                supportsAllDrives=True,
            )
        else:
            # request = drive_manager.service.files().create(
            #     body={"name": filename, "parents": [output_folder_id]},
            #     media_body=media,
            #     supportsAllDrives=True,
            # )
            request = drive_manager.service.files().create(
                body={
                    "name": filename,
                    "parents": [output_folder_id],
                    "mimeType": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                },
                media_body=media,
                supportsAllDrives=True,
            )

        drive_manager.drive_execute(request)

        # Cleanup
        import shutil
        shutil.rmtree(tmp_dir, ignore_errors=True)


    def extractor(self, service, files):
        """
        Best-effort text extraction for many file types.

        Supported (best-effort):
        - PDF: extract text via PyMuPDF
        - CSV: read via pandas
        - Excel: read via pandas (xlsx via openpyxl)
        - Google Docs: export to text/plain
        - Google Sheets: export to text/csv
        - Plain text files: decode as utf-8 (fallback latin-1)
        - Images (png/jpg/jpeg): OCR only if an OCR backend is available (optional)

        Returns one entry per input file (so nothing is silently dropped).
        """

        def _download_bytes(file_id: str) -> bytes:
            fh = io.BytesIO()
            request = service.files().get_media(fileId=file_id)
            downloader = MediaIoBaseDownload(fh, request)
            done = False
            while not done:
                _, done = downloader.next_chunk()
            return fh.getvalue()

        def _export_bytes(file_id: str, mime_type: str) -> bytes:
            fh = io.BytesIO()
            request = service.files().export_media(fileId=file_id, mimeType=mime_type)
            downloader = MediaIoBaseDownload(fh, request)
            done = False
            while not done:
                _, done = downloader.next_chunk()
            return fh.getvalue()

        def _bytes_to_text(data: bytes) -> str:
            try:
                return data.decode("utf-8")
            except Exception:
                try:
                    return data.decode("latin-1")
                except Exception:
                    return ""

        def _ocr_image_bytes(image_bytes: bytes) -> Tuple[Optional[str], Optional[str]]:
            """
            Lightweight OCR: tries pytesseract (requires system tesseract + pillow).
            If unavailable, returns a clear message so we don't silently skip files.
            """
            temp_path = None
            try:
                try:
                    import pytesseract  # type: ignore
                    from PIL import Image  # type: ignore
                except Exception:
                    return None, "OCR unavailable: install tesseract + pytesseract + pillow."

                with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
                    tmp.write(image_bytes)
                    temp_path = tmp.name

                img = Image.open(temp_path)
                text = pytesseract.image_to_string(img)
                return text, None
            except Exception as e:
                return None, f"OCR failed: {e}"
            finally:
                if temp_path:
                    try:
                        os.remove(temp_path)
                    except Exception:
                        pass

        results = []
        for f in files:
            name = f.get("name", "")
            file_id = f.get("id", "")
            mime = f.get("mimeType", "") or ""
            ext = os.path.splitext(name)[1].lower()

            text = ""
            error = ""

            try:
                # Google native types
                if mime == "application/vnd.google-apps.document":
                    text = _bytes_to_text(_export_bytes(file_id, "text/plain"))
                elif mime == "application/vnd.google-apps.spreadsheet":
                    # Export as CSV (best-effort single-sheet export)
                    text = _bytes_to_text(_export_bytes(file_id, "text/csv"))

                # PDFs
                elif ext == ".pdf" or mime == "application/pdf":
                    data = _download_bytes(file_id)
                    doc = fitz.open(stream=data, filetype="pdf")
                    text = "\n".join([page.get_text() for page in doc])

                # CSV
                elif ext == ".csv" or mime in ("text/csv", "application/csv"):
                    import pandas as pd
                    data = _download_bytes(file_id)
                    df = pd.read_csv(io.BytesIO(data), dtype=str, keep_default_na=False, na_filter=False)
                    text = df.to_csv(index=False)

                # Excel
                elif ext in (".xlsx", ".xls") or mime in (
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    "application/vnd.ms-excel",
                ):
                    import pandas as pd
                    data = _download_bytes(file_id)
                    xls = pd.ExcelFile(io.BytesIO(data))
                    parts = []
                    for sheet in xls.sheet_names:
                        df = pd.read_excel(xls, sheet_name=sheet, dtype=str).fillna("")
                        parts.append(f"--- Sheet: {sheet} ---")
                        parts.append(df.to_csv(index=False))
                    text = "\n".join(parts)

                # Images (OCR optional)
                elif ext in (".png", ".jpg", ".jpeg") or mime.startswith("image/"):
                    data = _download_bytes(file_id)
                    ocr_text, ocr_err = _ocr_image_bytes(data)
                    if ocr_text:
                        text = ocr_text
                    else:
                        error = ocr_err or "No OCR text extracted."

                # Plain text-ish fallback
                else:
                    data = _download_bytes(file_id)
                    text = _bytes_to_text(data)
                    if not text.strip():
                        error = f"Unsupported or non-text file type (mime={mime}, ext={ext})."

            except Exception as e:
                error = str(e)

            results.append({
                "id": file_id,
                "name": name,
                "mimeType": mime,
                "ext": ext,
                "lines": [l.strip() for l in (text or "").splitlines() if l.strip()],
                "extract_error": error,
            })

        return results
