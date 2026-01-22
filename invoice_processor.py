import os
import io
import json
import re
import streamlit as st
from typing import Optional, List, Dict
from googleapiclient.http import MediaIoBaseDownload
from collections import defaultdict
from app_logger import get_logger
from llm_manager import llm_call
import data_normalization_utils as utils
import pdf_engine
import vision_engine
import config
from concurrent.futures import ThreadPoolExecutor

logger = get_logger(__name__)

class InvoiceProcessor:
    def __init__(self):
        self.year_month_data = defaultdict(lambda: defaultdict(list))
        
    def safe_json_load(self, text: str) -> Dict:
        """Safely parses JSON from LLM response strings."""
        if not text or not text.strip():
            raise ValueError("LLM returned empty response")
        try:
            return json.loads(text)
        except Exception:
            match = re.search(r'\{.*\}', text, re.S)
            if match:
                return json.loads(match.group())
            raise ValueError("Could not extract valid JSON from LLM response")

    def parse_invoices_with_llm(self, invoice_texts: List[str]) -> List[Dict]:
        """Uses LLM to extract structured data from invoice texts."""
        parsed_invoices = []
        logger.info(f"Starting LLM parsing for {len(invoice_texts)} document(s)")
        
        for i, invoice_text in enumerate(invoice_texts):
            full_text = invoice_text if isinstance(invoice_text, str) else "\n".join(invoice_text)
            
            prompt = f"""
            {config.prompt}
            
            Invoice Text Content:
            {full_text[:4000]}
            """
            
            try:
                response_text, model_name = llm_call(prompt)
                data = self.safe_json_load(response_text)
                
                # Normalize extracted data
                data["invoice_date"] = utils.normalize_date(data.get("invoice_date", ""))
                data["raw_text"] = full_text
                data["extraction_method"] = f"LLM ({model_name})"
                
                parsed_invoices.append(data)
                logger.info(f"✓ LLM parsing successful for doc {i+1}/{len(invoice_texts)} using {model_name}")
            except Exception as e:
                logger.warning(f"LLM Parsing failed for doc {i+1}, falling back to regex: {e}")
                parsed_invoices.append(utils.regex_parse_invoice(full_text))
                
        return parsed_invoices

    def extractor(self, service, files: List[Dict]) -> List[Dict]:
        """Coordinates multi-threaded text extraction from various file types."""
        logger.info(f"Starting parallel extraction for {len(files)} file(s)")

        def _get_bytes(file_id: str, is_export=False, mime_type=None) -> bytes:
            fh = io.BytesIO()
            if is_export:
                request = service.files().export_media(fileId=file_id, mimeType=mime_type)
            else:
                request = service.files().get_media(fileId=file_id)
            downloader = MediaIoBaseDownload(fh, request)
            done = False
            while not done: _, done = downloader.next_chunk()
            return fh.getvalue()

        def _process_single_file(f):
            name, file_id, mime = f.get("name", ""), f.get("id", ""), f.get("mimeType", "")
            ext = os.path.splitext(name)[1].lower()
            text, error = "", ""
            try:
                if mime == "application/vnd.google-apps.document":
                    text = _get_bytes(file_id, True, "text/plain").decode("utf-8")
                elif mime == "application/vnd.google-apps.spreadsheet":
                    text = _get_bytes(file_id, True, "text/csv").decode("utf-8")
                elif ext == ".pdf" or mime == "application/pdf":
                    text = pdf_engine.extract_text_from_pdf(_get_bytes(file_id))
                elif ext in (".csv", ".xlsx", ".xls"):
                    import pandas as pd
                    data = _get_bytes(file_id)
                    df = pd.read_csv(io.BytesIO(data), dtype=str) if ext == ".csv" else pd.read_excel(io.BytesIO(data), dtype=str)
                    text = df.fillna("").to_csv(index=False)
                elif ext in (".png", ".jpg", ".jpeg") or mime.startswith("image/"):
                    text = vision_engine.extract_text_with_vision(_get_bytes(file_id), name)
                    if not text: error = "Vision extraction failed"
                else:
                    text = _get_bytes(file_id).decode("utf-8", errors="ignore")
            except Exception as e:
                error = str(e)
                logger.error(f"Error extracting {name}: {e}")

            return {
                "id": file_id, "name": name, "mimeType": mime,
                "lines": [l.strip() for l in (text or "").splitlines() if l.strip()],
                "extract_error": error
            }

        with ThreadPoolExecutor(max_workers=5) as executor:
            results = list(executor.map(_process_single_file, files))

        return results
