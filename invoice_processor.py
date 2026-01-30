import os
import io
import json
import re
from typing import Optional, List, Dict
from googleapiclient.http import MediaIoBaseDownload
from collections import defaultdict
from app_logger import get_logger
from app_logger import get_logger
from llm_manager import llm_call, async_llm_call
import data_normalization_utils as utils
import asyncio
import data_normalization_utils as utils
import pdf_engine
import config
import time

logger = get_logger(__name__)

class InvoiceProcessor:
    def __init__(self):
        self.year_month_data = defaultdict(lambda: defaultdict(list))
        
    def safe_json_load(self, text: str) -> Dict:
        """Safely parses JSON from LLM response strings, handling nested lists and extracting the main object."""
        if not text or not text.strip():
            raise ValueError("LLM returned empty response")
        
        def _unwrap(data):
            # Recursively unwrap lists until we find a dictionary or empty
            while isinstance(data, list) and data:
                data = data[0]
            return data if isinstance(data, dict) else {}

        try:
            # Try direct parse
            data = json.loads(text)
            result = _unwrap(data)
            if result: return result
        except Exception:
            pass

        # Try regex extraction
        match = re.search(r'(\{.*\}|\[.*\])', text, re.S)
        if match:
            try:
                data = json.loads(match.group())
                result = _unwrap(data)
                if result: return result
            except:
                pass
                
        raise ValueError("Could not extract valid JSON dictionary from LLM response")

    async def _process_single_invoice_async(self, invoice_text: str, index: int) -> Dict:
        """Async worker for processing a single invoice."""
        full_text = invoice_text if isinstance(invoice_text, str) else "\n".join(invoice_text)
        
        # --- Tier 0: Check for empty text (Vision failure) ---
        if not full_text.strip():
            logger.warning(f"⏩ Doc {index+1}: Skipping LLM parsing because text content is empty.")
            return {"invoice_date": "Unknown", "total_amount": 0.0, "vendor_name": "Unknown", "raw_text": "", "extraction_method": "Skipped (No Text)"}

        # --- Stage 1: Primary Extraction ---
        prompt = f"{config.prompt}\n\nInvoice Text Content:\n{full_text[:4000]}"
        
        data = {}
        try:
            response_text, model_name = await async_llm_call(prompt)
            data = self.safe_json_load(response_text)
            
            # --- Stage 2: Deep Extraction Retry ---
            critical_fields = ["invoice_date", "total_amount", "vendor_name"]
            missing = [f for f in critical_fields if not data.get(f) or str(data.get(f)).strip() in ("", "None", "null")]
            
            if missing:
                logger.warning(f"⚠️ Doc {index+1}: Missing critical fields {missing}. Triggering Deep Extraction...")
                retry_prompt = f"RE-EXAMINE the text for these missing fields: {', '.join(missing)}.\nText: {full_text[:4000]}\nExisting: {json.dumps(data)}"
                retry_response, _ = await async_llm_call(retry_prompt)
                retry_data = self.safe_json_load(retry_response)
                data.update({k: v for k, v in retry_data.items() if v and str(v).lower() != "none"})
            
            # Normalize and finish
            data["invoice_date"] = utils.normalize_date(data.get("invoice_date", ""))
            data["raw_text"] = full_text
            data["extraction_method"] = f"Async LLM ({model_name})"
            
        except Exception as e:
            logger.warning(f"Async LLM Primary/Deep failed for doc {index+1}, using Stage 3 (Regex): {e}")
            data = utils.regex_parse_invoice(full_text)
            data["raw_text"] = full_text

        # --- Stage 4: Final Rescue (AI) ---
        # If after Regex/LLM we still lack fields, try one last hyper-focused AI call
        critical_fields = ["invoice_date", "total_amount", "vendor_name"]
        still_missing = [f for f in critical_fields if not data.get(f) or str(data.get(f)).strip() in ("", "None", "null", "0", "0.0")]
        
        if still_missing and full_text.strip():
            try:
                logger.info(f"🆘 Final Rescue triggered for doc {index+1}: Searching for {still_missing}")
                rescue_prompt = f"Extract ONLY these fields: {', '.join(still_missing)}. Format: JSON.\nText: {full_text[:3000]}"
                rescue_response, r_model = await async_llm_call(rescue_prompt)
                rescue_data = self.safe_json_load(rescue_response)
                for k, v in rescue_data.items():
                    if v and str(v).lower() != "none" and k in critical_fields:
                        data[k] = v
                        data["extraction_method"] = f"Rescue Async AI ({r_model})"
            except Exception:
                pass

        # Final normalization
        data["invoice_date"] = utils.normalize_date(data.get("invoice_date", ""))
        data["invoice_number"] = utils.clean_invoice_number(data.get("invoice_number", ""))
        logger.info(f"✓ Processing doc {index+1} complete. Method: {data.get('extraction_method')}")
        return data

    async def parse_invoices_async(self, invoice_texts: List[str]) -> List[Dict]:
        """Creates async tasks for all invoices and runs them in parallel."""
        tasks = [self._process_single_invoice_async(text, i) for i, text in enumerate(invoice_texts)]
        return await asyncio.gather(*tasks)

    def parse_invoices_with_llm(self, invoice_texts: List[str]) -> List[Dict]:
        """Wrapper to run async parsing in a synchronous context."""
        logger.info(f"Starting Async Parallel parsing for {len(invoice_texts)} document(s)")
        try:
            return asyncio.run(self.parse_invoices_async(invoice_texts))
        except RuntimeError:
            # If an event loop is already running (e.g. in some environments), use it
            loop = asyncio.get_event_loop()
            return loop.run_until_complete(self.parse_invoices_async(invoice_texts))

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

        for idx, f in enumerate(files):
            name, file_id, mime = f.get("name", ""), f.get("id", ""), f.get("mimeType", "")
            ext = os.path.splitext(name)[1].lower()
            text, error = "", ""
            try:
                if ext == ".pdf" or mime == "application/pdf":
                    text = pdf_engine.extract_text_from_pdf(_get_bytes(file_id))
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
