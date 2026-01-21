import json
import re
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple
from dateutil import parser  # Robust date parsing

import pandas as pd
import streamlit as st

import ai_models
import db
import oauth

# ==============================================================================
# CONFIGURATION & CLIENTS
# ==============================================================================

DEFAULT_PRIMARY_MODEL = "meta-llama/Meta-Llama-3-8B-Instruct"
DEFAULT_GROQ_MODEL = "llama3-8b-8192"
DEFAULT_FALLBACK_MODEL = "gemini-1.5-flash"
BASE_URL = "https://router.huggingface.co/v1"

@st.cache_resource
def get_primary_client():
    """Initializes the primary AI client (Hugging Face / OpenAI compatible)."""
    api_key = st.secrets.get("openai_api_key")
    base_url = st.secrets.get("base_url", BASE_URL)
    
    if not api_key:
        st.error("Missing 'openai_api_key' in secrets.toml for Primary Model.")
        return None
        
    try:
        return ai_models.initiate_huggingface_model(api_key=api_key, base_url=base_url)
    except Exception as e:
        st.error(f"Failed to initialize Primary Client: {e}")
        return None

@st.cache_resource
def get_groq_client():
    """Initializes the Groq AI client."""
    api_key = st.secrets.get("groq_api_key")
    
    if not api_key:
        return None
        
    try:
        return ai_models.initiate_groq_model(api_key=api_key)
    except Exception as e:
        return None

@st.cache_resource
def get_fallback_client():
    """Initializes the fallback AI client (Gemini)."""
    api_key = st.secrets.get("gemini_api_key")
    
    if not api_key:
        # Fallback is optional, so just return None if not configured
        return None
        
    try:
        return ai_models.initiate_gemini_model(api_key=api_key)
    except Exception as e:
        # Silently fail or log debug
        return None

# ==============================================================================
# CORE LLM LOGIC
# ==============================================================================

def llm_call(prompt: str) -> str:
    """
    Executes an LLM call with a fallback mechanism.
    1. Tries Primary Client (HF/OpenAI).
    2. If it fails, tries Fallback Client (Gemini).
    """
    
    # --- Attempt 1: Primary Model ---
    client = get_primary_client()
    primary_error = None
    
    if client:
        model_name = st.secrets.get("openai_model", DEFAULT_PRIMARY_MODEL)
        try:
            response = client.chat.completions.create(
                model=model_name,
                messages=[
                    {"role": "system", "content": "You are a precise financial invoice assistant."},
                    {"role": "user", "content": prompt}
                ],
                max_tokens=500
            )
            return response.choices[0].message.content.strip()
            
        except Exception as e:
            primary_error = e
            st.warning(f"Primary model encountered an error: {e}. Attempting fallback to Groq...")

    # --- Attempt 2: Groq Model ---
    groq_client = get_groq_client()
    groq_error = None

    if groq_client:
        model_name = st.secrets.get("groq_model", DEFAULT_GROQ_MODEL)
        try:
            response = groq_client.chat.completions.create(
                model=model_name,
                messages=[
                    {"role": "system", "content": "You are a precise financial invoice assistant."},
                    {"role": "user", "content": prompt}
                ],
                max_tokens=500
            )
            return response.choices[0].message.content.strip()
        except Exception as e:
            groq_error = e
            st.warning(f"Groq model encountered an error: {e}. Attempting fallback to Gemini...")

    # --- Attempt 3: Fallback Model (Gemini) ---
    gemini_client = get_fallback_client()
    
    if gemini_client:
        model_name = st.secrets.get("gemini_model", DEFAULT_FALLBACK_MODEL)
        try:
            model = gemini_client.GenerativeModel(model_name)
            # Gemini 'generate_content' is simple text-in-text-out
            full_prompt = f"System: You are a precise financial invoice assistant.\n\nUser: {prompt}"
            response = model.generate_content(full_prompt)
            if response.text:
                return response.text.strip()
        except Exception as e:
            st.error(f"Fallback model also failed: {e}")
            
    # --- Failure ---
    if primary_error:
        st.error(f"Original error (Primary): {primary_error}")
    if groq_error:
        st.error(f"Secondary error (Groq): {groq_error}")
    
    return "{}"

# ==============================================================================
# DATA LOADING & PROCESSING
# ==============================================================================

@st.cache_data(show_spinner=True)
def load_invoices_from_db(user_email: str) -> List[Dict[str, Any]]:
    """Loads invoices from the database and adapts them to the expected schema."""
    if not user_email:
        return []
    
    try:
        # Check if user is admin (logic duplicated from main.py or db.py)
        # Check if user is admin (logic duplicated from main.py or db.py)
        admin_email = st.secrets.get("admin_email", "").strip().lower()
        is_admin = (user_email or "").strip().lower() == admin_email
        
        df = db.read_db(user_id=user_email, is_admin=is_admin)
        records = df.to_dict(orient="records")
        
        # Map DB columns to Chatbot Schema
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

# ==============================================================================
# DATA FILTERING HELPERS
# ==============================================================================

def filter_by_invoice_number(invoices: List[Dict], invoice_number: str) -> List[Dict]:
    normalized = invoice_number.strip().lower()
    return [
        inv for inv in invoices
        if str(inv.get("invoice_no", "")).strip().lower() == normalized
    ]

def filter_by_date_and_category(
    invoices: List[Dict], 
    start_date: datetime, 
    end_date: datetime, 
    category: Optional[str] = None
) -> Tuple[List[Dict], Optional[Dict], Optional[Dict]]:
    
    filtered = []
    
    for inv in invoices:
        date_str = inv.get("invoice_date", "")
        if not date_str:
            continue

        # Use dateutil parser for best-effort parsing of ANY valid format
        inv_date = None
        try:
            inv_date = parser.parse(date_str.strip())
        except Exception as e:
            # Log specific parsing failures to help debug
            # st.warning(f"Skipping invalid date format: '{date_str}' ({e})")
            continue
        
        if not inv_date:
            continue

        if start_date <= inv_date <= end_date:
            if not category or inv.get("invoice_description", "").lower() == category.lower():
                filtered.append(inv)

    min_inv = None
    max_inv = None
    
    if filtered:
        # Find min/max by amount
        min_inv = min(filtered, key=lambda x: float(x.get("total_amount", 0)))
        max_inv = max(filtered, key=lambda x: float(x.get("total_amount", 0)))

    return filtered, min_inv, max_inv

def calculate_total_amount(invoices: List[Dict]) -> float:
    return round(sum(float(inv.get("total_amount", 0)) for inv in invoices), 2)

# ==============================================================================
# INTELLIGENT PARSING & ANSWERS
# ==============================================================================

def extract_filter_parameters(user_input: str) -> Optional[Dict]:
    """Uses LLM to extract structured filter parameters from natural language."""
    prompt = f"""
    You are an API parameter extractor. Return ONLY a valid JSON object.
    
    User Query: "{user_input}"
    
    Output JSON Schema:
    {{
      "filter_type": "month_year | year | exact_date | date_range",
      "start_date": "Feb 01 2013",
      "end_date": "Feb 28 2013",
      "category": null, 
      "invoice_no": null,
      "action": "details | total | count | highest | lowest"
    }}
    
    Notes:
    - Dates must be in 'MMM DD YYYY' format (e.g. Feb 01 2023).
    - If a whole year is mentioned (e.g. "2025"), return the full range: "Jan 01 2025" to "Dec 31 2025".
    - If no year is specified, assume 2023 or contextually relevant.
    """
    
    response_text = llm_call(prompt)
    
    # Simple regex to find JSON block
    match = re.search(r"\{[\s\S]+\}", response_text)
    if match:
        try:
            return json.loads(match.group())
        except json.JSONDecodeError:
            pass
            
    return None

def generate_human_response(query: str, invoices: List[Dict], total: float, min_inv: Any, max_inv: Any) -> str:
    """Uses LLM to generate a natural language response based on the data found."""
    count = len(invoices)
    
    prompt = f"""
    User Question: "{query}"
    
    Data Found:
    - Matched Invoices Count: {count}
    - Total Amount: {total}
    - Lowest Amount Invoice: {min_inv}
    - Highest Amount Invoice: {max_inv}
    
    Task: Write a helpful, concise answer to the user's question using this data.
    """
    return llm_call(prompt)

# ==============================================================================
# MAIN INTERFACE
# ==============================================================================

def ensure_user_login():
    """Checks login status and halts execution if not logged in."""
    if "creds" not in st.session_state:
        st.warning("Please log in to use the Chat Bot.")
        oauth.ensure_google_login(show_ui=True)
        if "creds" not in st.session_state:
            st.stop()
            
    user_email = st.session_state.get("user_email")
    if not user_email:
        st.error("Authentication Error: User email missing.")
        st.stop()
        
    return user_email

def run_chat_interface():
    """Main entry point for the Chat Bot view."""
    
    st.title("📊 AI Invoice Assistant")
    st.caption("Ask questions about your finances, e.g., 'How much did I spend in 2024?'")
    
    # 1. Login Check
    user_email = ensure_user_login()
    
    # 2. Load Data
    invoices = load_invoices_from_db(user_email)
    st.toast(f"Loaded {len(invoices)} invoices.", icon="✅")
    
    # 3. Query Input
    query = st.text_input("Message", placeholder="Type your question here...")
    
    if st.button("Send", type="primary") and query:
        with st.spinner("Thinking..."):
            # A. Extract Intent
            params = extract_filter_parameters(query)
            
            if not params:
                st.error("I couldn't understand that query. Please try being more specific about dates or categories.")
                return

            filtered_invoices = []
            min_inv, max_inv = None, None
            
            # B. Execute Filtering
            invoice_no = params.get("invoice_no")
            
            if invoice_no:
                # Specific Invoice Search
                st.info(f"Searching for Invoice #{invoice_no}")
                filtered_invoices = filter_by_invoice_number(invoices, invoice_no)
            
            elif params.get("start_date") and params.get("end_date"):
                # Date Range Search
                try:
                    start = datetime.strptime(params["start_date"], "%b %d %Y")
                    end = datetime.strptime(params["end_date"], "%b %d %Y")
                    
                    filtered_invoices, min_inv, max_inv = filter_by_date_and_category(
                        invoices, start, end, params.get("category")
                    )
                    st.info(f"Filtered {len(filtered_invoices)} invoices from {start.strftime('%b %d, %Y')} to {end.strftime('%b %d, %Y')}")
                except ValueError:
                    st.error("Date parsing failed. Please try a clearer date format.")
                    return
            else:
                # Default case (e.g. "Show me all") - might be risky if huge data, but ok for now
                filtered_invoices = invoices

            # C. Synthesize Answer
            if not filtered_invoices:
                st.warning("No invoices match your criteria.")
            else:
                total_val = calculate_total_amount(filtered_invoices)
                answer = generate_human_response(query, filtered_invoices, total_val, min_inv, max_inv)
                
                st.markdown("### 🤖 Answer")
                st.write(answer)
                
                with st.expander(f"View {len(filtered_invoices)} Source Documents"):
                    st.dataframe(pd.DataFrame(filtered_invoices))
