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
    
    # @st.cache_resource
    # def get_easyocr_reader():
    #     import easyocr
    #     return easyocr.Reader(['en'], gpu=False, verbose=False)
        
    # ================= LLM Call =================
    def safe_json_load(self, text):
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
    
    # def is_valid_invoice(self, total):
    #     try:
    #         if not total or float(total) == 0.0:
    #             return False
            
    #         return True
        
    #     except Exception as e:
    #         print("is_not_valid(expection): ", str(e))
    #         print("Exception: ", str(e))
    #         return False

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
