import os
import io
import json
import re
from dateutil import parser
import tempfile
import fitz  # PyMuPDF
# import easyocr
from googleapiclient.http import MediaIoBaseDownload
from collections import defaultdict
import ai_models
from dotenv import load_dotenv
# import google.generativeai as genai
import streamlit as st

load_dotenv()

class InvoiceProcessor:
    def __init__(self):
        self.client = ai_models.initiate_huggingface_model(st.secrets["api_key"])
        self.OPENAI_MODEL = st.secrets["model"]

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
            
            # Extract invoice date
            date_patterns = [
                r'invoice\s*date\s*:?\s*([0-9]{1,2}[/\-\.][0-9]{1,2}[/\-\.][0-9]{2,4})',
                r'date\s*:?\s*([0-9]{1,2}[/\-\.][0-9]{1,2}[/\-\.][0-9]{2,4})',
                r'bill\s*date\s*:?\s*([0-9]{1,2}[/\-\.][0-9]{1,2}[/\-\.][0-9]{2,4})',
                r'dated\s*:?\s*([0-9]{1,2}[/\-\.][0-9]{1,2}[/\-\.][0-9]{2,4})',
            ]
            
            for pattern in date_patterns:
                match = re.search(pattern, full_text, re.IGNORECASE)
                if match:
                    date_str = match.group(1).strip()
                    try:
                        # Try to parse and format the date
                        dt = parser.parse(date_str, dayfirst=True, fuzzy=True)
                        invoice_data["invoice_date"] = dt.strftime("%b %d %Y")
                    except:
                        invoice_data["invoice_date"] = date_str
                    break
            
            # If not found with patterns, try generic date search in first 10 lines
            if not invoice_data["invoice_date"]:
                for line in lines[:10]:
                    # Look for dates in common formats
                    date_match = re.search(r'([0-9]{1,2}[/\-\.][0-9]{1,2}[/\-\.][0-9]{2,4})', line)
                    if date_match:
                        date_str = date_match.group(1).strip()
                        try:
                            dt = parser.parse(date_str, dayfirst=True, fuzzy=True)
                            invoice_data["invoice_date"] = dt.strftime("%b %d %Y")
                            break
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
        results = []
        for f in files:
            ext = os.path.splitext(f['name'])[1].lower()
            text = ""

            if ext == ".pdf":
                fh = io.BytesIO()
                request = service.files().get_media(fileId=f['id'])
                downloader = MediaIoBaseDownload(fh, request)
                done = False
                while not done:
                    _, done = downloader.next_chunk()

                doc = fitz.open(stream=fh.getvalue(), filetype="pdf")
                for page in doc:
                    text += page.get_text()

            # elif ext in [".png", ".jpg", ".jpeg"]:
            #     fh = io.BytesIO()
            #     request = service.files().get_media(fileId=f['id'])
            #     downloader = MediaIoBaseDownload(fh, request)
            #     done = False
            #     while not done:
            #         _, done = downloader.next_chunk()

            #     with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as tmp:
            #         tmp.write(fh.getvalue())
            #         temp_path = tmp.name

            #     self.reader = self.get_easyocr_reader()
            #     text = "\n".join(self.reader.readtext(temp_path, detail=0, paragraph=True))
            #     os.remove(temp_path)

            else:
                continue

            results.append({
                "id": f["id"],
                "name": f["name"],
                "lines": [l.strip() for l in text.splitlines() if l.strip()]
            })

        return results
