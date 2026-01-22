import gc
import re
import time
import json
import streamlit as st
from random import randint
from typing import List, Dict
import db
import data_normalization_utils as utils
from drive_manager import DriveManager
from invoice_processor import InvoiceProcessor
from app_logger import get_logger

logger = get_logger(__name__)

def process_batch(batch: List[Dict], drive_manager, processor: InvoiceProcessor, user_id: str, DRIVE_DIRS: Dict):
    """Processes a single batch of files: extraction, filtering, parsing, and storage."""
    # 1. Extraction
    batch_extracted = processor.extractor(drive_manager.service, batch)
    
    # 2. Keyword Filtering
    KEYWORDS = ["total", "amount due", "grand total", "total amount", "total fare", "balance due", "total invoice value", "invoice value", "total fare (all inclusive)"]
    filtered_for_llm = []
    skipped_files = []

    for item in batch_extracted:
        if item.get("extract_error") and not item.get("lines"):
            skipped_files.append({"id": item["id"], "name": item["name"]})
            continue
            
        text_lines = item["lines"]
        if any(any(k in line.lower() for k in KEYWORDS) for line in text_lines):
            filtered_for_llm.append({"text": "\n".join(text_lines), "file": {"id": item["id"], "name": item["name"]}})
        else:
            # If no keywords, we still try parsing (or skip based on strictness)
            filtered_for_llm.append({"text": "\n".join(text_lines), "file": {"id": item["id"], "name": item["name"]}})

    # 3. LLM Parsing
    if not filtered_for_llm: return
    
    chunk_texts = [f["text"] for f in filtered_for_llm]
    parsed_chunk = processor.parse_invoices_with_llm(chunk_texts)
    
    # 4. Validation & Storage
    valid_files = []
    invalid_files = skipped_files
    
    for idx, entry in enumerate(parsed_chunk):
        file_info = filtered_for_llm[idx]["file"]
        entry["_file"] = file_info
        
        amount = utils.clean_amount(entry.get("total_amount"))
        vendor = str(entry.get("vendor_name", "")).strip()
        date = str(entry.get("invoice_date", "")).strip()
        
        # ULTRA-PERSISTENCE RULE: Save if we have ANY meaningful data point.
        # This prevents skipping invoices that might be messy but still have useful info.
        if amount > 0 or (vendor and vendor != "Unknown") or (date and date != "Unknown"):
            entry["total_amount"] = amount
            db.insert_invoice(entry, user_id=user_id)
            valid_files.append(file_info)
        else:
            logger.warning(f"Skipping file {file_info['name']}: No identifiable data found across 4 extraction stages.")
            invalid_files.append(file_info)

    # 5. Move Files in Drive
    drive_manager.move_files_drive(valid_files, "valid_docs", DRIVE_DIRS)
    drive_manager.move_files_drive(invalid_files, "invalid_docs", DRIVE_DIRS)
    
    logger.info(f"Batch complete: {len(valid_files)} valid, {len(invalid_files)} invalid.", extra={"user_id": user_id})

def start_processing(drive_manager: DriveManager, processor: InvoiceProcessor, input_folder_id: str, DRIVE_DIRS: Dict):
    st.info("📄 Processing invoices... Please do not refresh the page.")
    all_files = drive_manager.list_files_in_folder(input_folder_id)
    
    if not all_files:
        st.warning("No files found.")
        return

    progress_bar = st.progress(0)
    user_id = st.session_state.get("user_email")
    batch_size = 10 # Smaller batches for stability
    
    for i in range(0, len(all_files), batch_size):
        batch = all_files[i:i+batch_size]
        
        with st.status(f"Processing batch {i//batch_size + 1}...", expanded=True) as status:
            try:
                process_batch(batch, drive_manager, processor, user_id, DRIVE_DIRS)
                status.update(label=f"✅ Batch {i//batch_size + 1} complete", state="complete", expanded=False)
            except Exception as e:
                logger.error(f"Error in batch: {e}")
                st.error(f"Error processing batch: {e}")
                status.update(label=f"❌ Batch {i//batch_size + 1} failed", state="error")
            
        progress_bar.progress(min((i + batch_size) / len(all_files), 1.0))
        time.sleep(0.5) 
        gc.collect()

    st.success("✅ Processing complete!")
    st.toast("Invoices processed successfully!", icon="✅")

def setup_drive_folders(drive: DriveManager):
    """Ensures necessary Drive folders exist and returns their IDs."""
    input_folder_id = drive.get_or_create_folder(st.secrets["INPUT_DOCS"])
    root_id = drive.get_or_create_folder("Invoice_Processing")
    
    DRIVE_DIRS = {
        "project_id": root_id,
        "input_folder_id": input_folder_id,
        "valid_docs": drive.get_or_create_folder("scanned_docs", root_id),
        "invalid_docs": drive.get_or_create_folder("invalid_docs", root_id),
    }
    return DRIVE_DIRS

def initiate_drive(creds):
    processor = InvoiceProcessor()
    drive = DriveManager(creds)
    
    # Auto-initialize folders on login
    DRIVE_DIRS = setup_drive_folders(drive)
    st.session_state["drive_dirs"] = DRIVE_DIRS
    
    st.success(f"Before you click the below button to start the progress, Please upload the invoice files in you Google drive '{st.secrets['INPUT_DOCS']}' folder then proceed.")
    # st.success(f"Successfully created '{st.secrets['INPUT_DOCS']}' folder in your 📂 Google Drive. Kindly please upload the invoice files then click the button below to start process")

    if st.button("🚀 Start Invoice Processing"):
        start_processing(drive, processor, DRIVE_DIRS["input_folder_id"], DRIVE_DIRS)
        st.session_state["drive_ready"] = True