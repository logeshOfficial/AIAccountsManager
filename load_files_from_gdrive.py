
import gc
import re
import tempfile
import time
import pandas as pd
import streamlit as st
from random import randint
import os
import json
from drive_manager import DriveManager
from invoice_processor import InvoiceProcessor
import db

def start_processing(drive_manager, invoice_processor, input_docs_folder_id, DRIVE_DIRS):
    
    st.success("🟢 System ready")
    st.info("📄 Processing invoices from Google Drive. Kindly please wait until the progress complete \n Note: *** Don't refresh the page.***")


    all_files = drive_manager.list_files_in_folder(
        input_docs_folder_id
    )

    # ================= Main Processing Loop =================
    start_time = time.time()

    batch_size = 20
    filepaths = []
    batch_data =[]
    batch_wise_filtered_data = []
    filtered_batch_data = [] 

    st.info(f"all_files: {all_files}")
    # ================= Process Selected Folder =================
    filepaths = [f for f in all_files]

    progress = st.progress(0)
    status = st.empty()

    total_files = len(filepaths)
    processed_files = 0

    if not filepaths:
        st.warning("No files found in the selected folder.")
    else:
        st.info(f"{len(filepaths)} files found. Processing...")

    try:
        for i in range(0, len(filepaths), batch_size):
            valid_file_paths = []
            not_valid_file_paths = []
            parsed_data = []
            batch = filepaths[i:i+batch_size]
            status.info(
                f"Processing files {i + 1} → {min(i + batch_size, total_files)} of {total_files}"
            )
            
            st.info(f"Batch_len: {len(filepaths[i:i+batch_size])}")
            batch_extracted  = invoice_processor.extractor(drive_manager.service, filepaths[i:i+batch_size])
            
            st.info(batch_extracted)
            batch_data = []
            file_path_mapping = []

            for item in batch_extracted:
                batch_data.append(item["lines"])
                
                file_path_mapping.append({
                    "id": item["id"],
                    "name": item["name"]
                })

            KEYWORDS = ["total", "amount due", "grand total", "invoice total"]

            for idx, text in enumerate(batch_data):  
                has_total = any(
                    any(k in line.lower() for k in KEYWORDS)
                    and not re.search(r'0\.00|zero', line.lower())
                    for line in text
                    )           
            
                if not has_total:
                    continue            
                
                filtered_batch_data.append({
                    "text": text,
                    "file": file_path_mapping[idx]   
                })   
                
            try:
                # Use manual parser instead of LLM
                chunk_texts = [item["text"] for item in filtered_batch_data]
                
                # Parse invoices manually using regex and pattern matching
                parsed_chunk = invoice_processor.parse_invoices_manual(chunk_texts)
                
                # Add file information to each parsed entry
                for k, entry in enumerate(parsed_chunk):
                    if k < len(filtered_batch_data):
                        entry["_file"] = filtered_batch_data[k]["file"]
                    else:
                        # Fallback if indices don't match
                        entry["_file"] = filtered_batch_data[-1]["file"] if filtered_batch_data else {}

                parsed_data.extend(parsed_chunk)
                            
                filtered_data = []
                
                for idx, entry in enumerate(parsed_data):
                    value = entry.get("total_amount", "")
                    total = re.sub(r'[^\d.]', '', value.replace(",", "").replace("$", "").replace("₹", "").strip())

                    if invoice_processor.is_valid_invoice(total):
                        entry["total_amount"] = total
                        filtered_data.append(entry)
                        valid_file_paths.append(entry["_file"])
                    else:
                        not_valid_file_paths.append(entry["_file"])

                st.info(f"Parsed invoices count: {len(parsed_data)}")
                st.info(f"Valid invoices count: {len(filtered_data)}")

                from db import insert_invoice

                for entry in filtered_data:
                    entry["raw_text"] = entry.get("raw_text", "")  # optional
                    entry["vendor_name"] = entry.get("vendor_name", "")
                    entry["invoice_date"] = entry.get("invoice_date", "")  # Ensure invoice_date is always set
                    st.info(entry)
                    insert_invoice(entry)

                # batch_wise_filtered_data.append(filtered_data)
                
            except Exception as e:
                st.error(f"❌ Failed to parse or extract batch: {e}")
                with open("failed_batch.json", "w", encoding="utf-8") as f:
                    f.write(json.dumps(filtered_batch_data, indent=2))
                continue
            
            filtered_batch_data.clear()
            time.sleep(randint(3, 7))
            
            # Move processed files in Drive        
            drive_manager.move_files_drive(
                valid_file_paths,
                dest_dir="valid_docs",
                drive_dirs=DRIVE_DIRS
            )
            time.sleep(2) 
            drive_manager.move_files_drive(
                not_valid_file_paths,
                dest_dir="invalid_docs",
                drive_dirs=DRIVE_DIRS
            )
            
            processed_files += len(batch)
            progress.progress(min(processed_files / total_files, 1.0))

            batch_extracted.clear()
            batch_data.clear()
            file_path_mapping.clear()
            gc.collect()
            valid_file_paths.clear()
            not_valid_file_paths.clear()
            
            st.dataframe(db.read_db())
            
    except Exception as e:
        print("❌Error:", str(e))

    finally:
        status.info("✅ Processing complete!")
        st.success(f"✅ Completed in {time.time()-start_time:.2f}s")

        end_time = time.time()
        elapsed_time = end_time - start_time
        print(f"Loop execution time: {elapsed_time:.2f}s")


def initiate_drive(creds):
    invoice_processor = InvoiceProcessor()
    drive_manager = DriveManager(creds)
    
    if st.button("Chat Bot"):
        st.cache_data.clear()
        st.switch_page("pages/chat_bot.py")
            
    st.title("Accounts Manager - Google Drive")
    INPUT_DOCS = st.secrets["INPUT_DOCS"]        

    if st.button("Start Invoice Processing"):
        input_docs_folder_id = drive_manager.get_or_create_folder(INPUT_DOCS)
        
        PROJECT_ROOT = "Invoice_Processing"
        
        st.subheader("🚀 Initializing workspace")
        progress = st.progress(0)
        status = st.empty()
        
        # Step 1: Root folder
        status.info("📁 Checking root folder...")
        root_folder_id = drive_manager.get_or_create_folder(PROJECT_ROOT)
        
        progress.progress(25)
        st.info(f"Processing files from folder: {INPUT_DOCS}")
        
        DRIVE_DIRS = {
            "project_id": root_folder_id,
            "valid_docs": drive_manager.get_or_create_folder(
                "scanned_docs", root_folder_id
            ),
            "invalid_docs": drive_manager.get_or_create_folder(
                "invalid_docs", root_folder_id
            ),
        }

        progress.progress(100)
        status.success("✅ Initialization complete")
        time.sleep(1)
        
        start_processing(drive_manager, invoice_processor, input_docs_folder_id, DRIVE_DIRS)

        st.session_state["drive_ready"] = True

    