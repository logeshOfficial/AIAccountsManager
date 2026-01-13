import re
import pandas as pd
import json
from dotenv import load_dotenv
load_dotenv()  # Load from .env file
# import google.generativeai as genai
# from mistralai import Mistral
import os
import config
from datetime import datetime
import streamlit as st
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
from io import BytesIO
import pandas as pd
import streamlit as st
from drive_manager import DriveManager
import ai_models

if st.button("Drive Manager"):
    st.switch_page("pages/load_files_from_gdrive.py")
    
# ================= Streamlit UI =================
st.title("Accounts Manager Chat bot")

client_info = ai_models.initiate_huggingface_model()
client = client_info["client"]
OPENAI_MODEL = client_info["model"]

def llm_call(prompt: str) -> str:
    response = client.chat.completions.create(
        model=OPENAI_MODEL,
        messages=[
            {"role": "system", "content": "You are a precise financial invoice assistant."},
            {"role": "user", "content": prompt}
        ],
    )
    return response.choices[0].message.content.strip()

SCOPES = ['https://www.googleapis.com/auth/drive']

drive_manager = DriveManager(SCOPES)

@st.cache_data(show_spinner=True)
def load_invoices_from_drive():
    try:
        creds = Credentials.from_service_account_info(st.secrets["google_service_account"], SCOPES)
        drive_service = build("drive", "v3", credentials=creds)
        DRIVE_PROJECT_ROOT = "Invoice_Processing"
        OUTPUT_FOLDER_NAME = "output"
        
        root_folder_id = drive_manager.get_or_create_folder(drive_service, DRIVE_PROJECT_ROOT)
        
        output_folder_id = drive_manager.get_or_create_folder(
        drive_service,
        OUTPUT_FOLDER_NAME,
        parent_id=root_folder_id
    )
        
        query = (
            f"'{output_folder_id}' in parents and "
            "mimeType='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'"
        )

        response = drive_service.files().list(
            q=query,
            fields="files(id, name)"
        ).execute()

        all_invoice_data = []

        for file in response.get("files", []):
            request = drive_service.files().get_media(fileId=file["id"])
            fh = BytesIO()
            downloader = MediaIoBaseDownload(fh, request)

            done = False
            while not done:
                _, done = downloader.next_chunk()

            fh.seek(0)

            xls = pd.ExcelFile(fh)
            for sheet in xls.sheet_names:
                df = pd.read_excel(xls, sheet_name=sheet)
                df = df.fillna("")
                all_invoice_data.extend(df.to_dict(orient="records"))

        return all_invoice_data
    except Exception as e:
        st.error(f"Error loading invoices: {e}")
        return []

# ------------------- FILTERING LOGIC -------------------
def filter_by_invoice_number(invoices, invoice_number: str):
    normalized = invoice_number.strip().lower()
    return [
        inv for inv in invoices
        if str(inv.get("invoice_no", "")).strip().lower() == normalized
    ]

def filter_invoices_by_date_range_and_category(invoices, start_date, end_date, category=None):
    filtered = []
    min_inv, max_inv = None, None

    for inv in invoices:
        date_str = inv.get("invoice_date", "")
        if not date_str:
            continue

        try:
            invoice_date = datetime.strptime(date_str.strip(), "%b %d %Y")
        except ValueError:
            continue

        if start_date <= invoice_date <= end_date:
            if not category or inv.get("invoice_description", "").lower() == category.lower():
                filtered.append(inv)

    if filtered:
        min_inv = min(filtered, key=lambda x: float(x.get("total_amount", 0)))
        max_inv = max(filtered, key=lambda x: float(x.get("total_amount", 0)))

    return filtered, min_inv, max_inv

def calculate_total_amount(invoices):
    return round(
        sum(float(inv.get("total_amount", 0)) for inv in invoices),
        2
    )

# ------------------- PARAM EXTRACTION (LLM) -------------------
def extract_filter_parameters(user_input: str):
    prompt = f"""
Return ONLY valid JSON.

User query:
"{user_input}"

JSON format:
{{
  "filter_type": "month_year | year | exact_date | date_range",
  "start_date": "Feb 01 2013",
  "end_date": "Feb 28 2013",
  "category": null,
  "invoice_no": null,
  "action": "details | total | count | highest | lowest"
}}
"""
    text = llm_call(prompt)
    # response = model.generate_content(prompt)
    # text = response.text.strip()

    match = re.search(r"\{[\s\S]+\}", text)
    return json.loads(match.group()) if match else None

# ------------------- RESPONSE REPHRASING -------------------
def rephrase_answer(question, invoices, total, min_inv, max_inv):
    prompt = f"""
User question:
"{question}"

Invoices matched: {len(invoices)}
Total amount: {total}
Lowest invoice: {min_inv}
Highest invoice: {max_inv}

Write a clear, concise answer.
"""
    # response = model.generate_content(prompt)
    # return response.text.strip()
    
    return llm_call(prompt)

# ------------------- STREAMLIT UI -------------------
st.set_page_config(page_title="Invoice Assistant", layout="wide")

st.title("📊 Invoice Query Assistant")
st.caption("Ask questions like: *Total office supply invoices in Feb 2013*")

invoice_data = load_invoices_from_drive()

st.success(f"Loaded {len(invoice_data)} invoices")

query = st.text_input("Ask your invoice question")

if st.button("🔍 Run Query") and query:
    with st.spinner("Analyzing invoices..."):
        params = extract_filter_parameters(query)

        if not params:
            st.error("Could not understand the query.")
            st.stop()

        invoice_no = params.get("invoice_no", None)

        if invoice_no:
            st.info(f"🔍 Looking for invoice number: {invoice_no}")
            filtered = filter_by_invoice_number(invoice_data, invoice_no)
            total = calculate_total_amount(filtered)
            answer = rephrase_answer(query, filtered, total, None, None)

        elif params["start_date"] and params["end_date"]:
            # st.info(f"🎯 Extracted filter parameters: {params}")
            
            start = datetime.strptime(params["start_date"], "%b %d %Y")
            end = datetime.strptime(params["end_date"], "%b %d %Y")

            filtered, min_inv, max_inv = filter_invoices_by_date_range_and_category(
                invoice_data,
                start,
                end,
                params.get("category")
            )

            if not filtered:
                st.warning("No invoices found for this query.")
                st.stop()

            total = calculate_total_amount(filtered)
            answer = rephrase_answer(query, filtered, total, min_inv, max_inv)

        else:
            answer = rephrase_answer(query, invoice_data, 0, None, None)
            
        st.subheader("📌 Answer")
        st.write(answer)

        if filtered:
            with st.expander("📄 View Matched Invoices"):
                st.dataframe(pd.DataFrame(filtered))
