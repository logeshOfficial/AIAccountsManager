import re
import pandas as pd
import json
from datetime import datetime
import streamlit as st
import db
import oauth
import ai_models

@st.cache_resource
def get_ai_client():
    try:
        return ai_models.initiate_huggingface_model(
            api_key=st.secrets.get("openai_api_key"),
            base_url=st.secrets.get("base_url", "https://router.huggingface.co/v1")
        )
    except Exception as e:
        st.error(f"Error initializing AI client: {e}")
        return None

@st.cache_resource
def get_gemini_client():
    try:
        return ai_models.initiate_gemini_model(st.secrets.get("gemini_api_key"))
    except Exception as e:
        return None

def llm_call(prompt: str) -> str:
    # 1. Try Primary Client (HF)
    client = get_ai_client()
    primary_error = None
    
    if client:
        OPENAI_MODEL = st.secrets.get("openai_model", "meta-llama/Meta-Llama-3-8B-Instruct")
        try:
            response = client.chat.completions.create(
                model=OPENAI_MODEL,
                messages=[
                    {"role": "system", "content": "You are a precise financial invoice assistant."},
                    {"role": "user", "content": prompt}
                ],
                max_tokens=500
            )
            return response.choices[0].message
        except Exception as e:
            primary_error = e
            st.warning(f"Primary model failed. Switching to fallback... Error: {e}")

    # 2. Fallback: Gemini
    gemini_client = get_gemini_client()
    if gemini_client:
        GEMINI_MODEL_NAME = st.secrets.get("gemini_model", "gemini-1.5-flash")
        try:
            model = gemini_client.GenerativeModel(GEMINI_MODEL_NAME)
            full_prompt = f"System: You are a precise financial invoice assistant.\nUser: {prompt}"
            response = model.generate_content(full_prompt)
            if response.text:
                return response.text.strip()
        except Exception as e:
            st.error(f"Fallback model also failed: {e}")
            if primary_error:
                st.error(f"Original error was: {primary_error}")
            return "{}"

    st.error("All AI models failed.")
    return "{}"

@st.cache_data(show_spinner=True)
def load_invoices_from_db(user_email: str):
    try:
        if not user_email:
            return []
        
        # Read from DB as dataframe
        df = db.read_db(user_id=user_email)
        
        # Convert to list of dicts for compatibility with existing logic
        # format: we need 'invoice_no' key etc?
        # db.py schema: 
        # invoice_number -> mapped to what? 
        # The chatbot logic uses: "invoice_no", "invoice_date", "invoice_description", "total_amount"
        # The DB schema has: invoice_number, invoice_date, description, total_amount
        
        # Let's check filter_by_invoice_number: uses "invoice_no"
        # filter_invoices_by_date_range_and_category: uses "invoice_date", "invoice_description", "total_amount"
        
        # We need to rename columns to match what the chatbot expects OR update chatbot logic.
        # Updating the chatbot logic key names is cleaner but modifying this loader to adapt is safer for preserving logic.
        
        # Let's map DB columns to chatbot expected keys:
        # invoice_number -> invoice_no
        # description -> invoice_description
        # total_amount -> total_amount (same)
        # invoice_date -> invoice_date (same)
        
        records = df.to_dict(orient="records")
        adapted_records = []
        for r in records:
            adapted_records.append({
                "invoice_no": r.get("invoice_number", ""),
                "invoice_date": r.get("invoice_date", ""),
                "invoice_description": r.get("description", ""),
                "total_amount": r.get("total_amount", 0),
                "vendor_name": r.get("vendor_name", ""),
                "gst_number": r.get("gst_number", ""),
                "raw_text": r.get("raw_text", "")
            })
            
        return adapted_records
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
# ------------------- STREAMLIT UI -------------------
def run_chat_interface():
    # st.set_page_config(page_title="Invoice Assistant", layout="wide") # Moved to main.py or handled by parent

    st.title("📊 Invoice Query Assistant")
    st.caption("Ask questions like: *Total office supply invoices in Feb 2013*")

    # 1. Ensure Login
    if "creds" not in st.session_state:
        st.warning("Please log in to continue.")
        oauth.ensure_google_login(show_ui=True)
        # If ensure_google_login doesn't stop, we might need to return
        # But usually ensure_google_login handles reruns or stops.
        # Just in case:
        if "creds" not in st.session_state:
            st.stop()

    user_email = st.session_state.get("user_email", "")

    if not user_email:
        st.error("User email not found. Please try logging in again.")
        st.stop()

    invoice_data = load_invoices_from_db(user_email)

    st.success(f"Loaded {len(invoice_data)} invoices for {user_email}")

    query = st.text_input("Ask your invoice question")

    if st.button("🔍 Run Query") and query:
        with st.spinner("Analyzing invoices..."):
            params = extract_filter_parameters(query)

            if not params:
                st.error("Could not understand the query.")
                return # Instead of st.stop() to keep UI responsive if embedded, though st.stop refers to script execution.

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
                    return # exit this button callback

                total = calculate_total_amount(filtered)
                answer = rephrase_answer(query, filtered, total, min_inv, max_inv)

            else:
                answer = rephrase_answer(query, invoice_data, 0, None, None)
                
            st.subheader("📌 Answer")
            st.write(answer)

            if filtered:
                with st.expander("📄 View Matched Invoices"):
                    st.dataframe(pd.DataFrame(filtered))
