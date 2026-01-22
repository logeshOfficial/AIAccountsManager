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
        """Uses LLM to extract structured data with a multi-stage validation and retry mechanism."""
        parsed_invoices = []
        logger.info(f"Starting Guaranteed LLM parsing for {len(invoice_texts)} document(s)")
        
        for i, invoice_text in enumerate(invoice_texts):
            full_text = invoice_text if isinstance(invoice_text, str) else "\n".join(invoice_text)
            
            # --- Stage 1: Primary Extraction ---
            prompt = f"{config.prompt}\n\nInvoice Text Content:\n{full_text[:4000]}"
            
            try:
                response_text, model_name = llm_call(prompt)
                data = self.safe_json_load(response_text)
                
                # --- Stage 2: Validation & Deep Extraction Retry ---
                critical_fields = ["invoice_date", "total_amount", "vendor_name"]
                missing = [f for f in critical_fields if not data.get(f) or str(data.get(f)).strip() == ""]
                
                if missing:
                    logger.warning(f"⚠️ Doc {i+1}: Missing critical fields {missing}. Triggering Deep Extraction...")
                    retry_prompt = f"""
                    RE-EXAMINE the text below specifically for these missing fields: {', '.join(missing)}.
                    Return ONLY a JSON object updating these fields.
                    
                    Text: {full_text[:4000]}
                    Existing Data: {json.dumps(data)}
                    """
                    retry_response, _ = llm_call(retry_prompt)
                    retry_data = self.safe_json_load(retry_response)
                    data.update({k: v for k, v in retry_data.items() if v})
                
                # Normalize and finish
                data["invoice_date"] = utils.normalize_date(data.get("invoice_date", ""))
                data["raw_text"] = full_text
                data["extraction_method"] = f"LLM ({model_name})"
                
                parsed_invoices.append(data)
                logger.info(f"✓ LLM parsing successful for doc {i+1} using {model_name}")
                
            except Exception as e:
                logger.warning(f"LLM Parsing failed for doc {i+1}, falling back to regex: {e}")
                parsed_invoices.append(utils.regex_parse_invoice(full_text))
                
        return parsed_invoices

    def extractor(self, service, files: List[Dict]) -> List[Dict]:
        """Coordinates text extraction from various file types sequentially for stability."""
        logger.info(f"Starting extraction for {len(files)} file(s)")
        results = []

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

        for f in files:
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

            results.append({
                "id": file_id, "name": name, "mimeType": mime,
                "lines": [l.strip() for l in (text or "").splitlines() if l.strip()],
                "extract_error": error
            })

        return results
