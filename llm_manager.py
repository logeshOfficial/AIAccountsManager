import streamlit as st
import ai_models
import json
import re
from typing import Tuple, Dict, Optional, Any
from google.genai import types
from app_logger import get_logger

logger = get_logger(__name__)

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
        logger.error(f"Failed to initialize Primary Client: {e}")
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
        return None
        
    try:
        return ai_models.initiate_gemini_model(api_key=api_key)
    except Exception as e:
        return None

def llm_call(prompt: str) -> Tuple[str, str]:
    """
    Executes an LLM call with a fallback mechanism.
    Returns: (response_text, model_name)
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
            logger.info(f"LLM Call successful using model: {model_name}")
            return response.choices[0].message.content.strip(), model_name
            
        except Exception as e:
            logger.warning(f"Primary model failed: {e}")
            primary_error = e
            # st.warning(f"Primary model encountered an error: {e}. Attempting fallback to Groq...")

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
            
            logger.info(f"LLM Call successful using Groq fallback: {model_name}")
            return response.choices[0].message.content.strip(), model_name
        except Exception as e:
            logger.warning(f"Groq fallback model failed: {e}")
            groq_error = e
            # st.warning(f"Groq model encountered an error: {e}. Attempting fallback to Gemini...")

    # --- Attempt 3: Fallback Model (Gemini) ---
    gemini_client = get_fallback_client()
    
    if gemini_client:
        model_name = st.secrets.get("gemini_model", DEFAULT_FALLBACK_MODEL)
        try:
            
            # Use system instruction if available in new SDK
            try:
                response = gemini_client.models.generate_content(
                    model=model_name,
                    contents=prompt,
                    config=types.GenerateContentConfig(
                        system_instruction="You are a precise financial invoice assistant."
                    )
                )
            except Exception as flash_e:
                logger.warning(f"Gemini {model_name} failed, trying gemini-1.5-pro: {flash_e}")
                response = gemini_client.models.generate_content(
                    model='gemini-1.5-pro',
                    contents=prompt,
                    config=types.GenerateContentConfig(
                        system_instruction="You are a precise financial invoice assistant."
                    )
                )
            
            if response.text:
                logger.info(f"LLM Call successful using Gemini fallback: {model_name}")
                return response.text.strip(), model_name
        except Exception as e:
            logger.error(f"Gemini fallback model also failed: {e}")
            # st.error(f"Fallback model also failed: {e}")
            
    # --- Failure ---
    if primary_error:
        logger.error(f"Original error (Primary): {primary_error}")
        st.error(f"Original error (Primary): {primary_error}")
    if groq_error:
        logger.error(f"Secondary error (Groq): {groq_error}")
        st.error(f"Secondary error (Groq): {groq_error}")
    
    return "{}", "None"

@st.cache_data(show_spinner=False)
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
      "invoice_number": null,
      "action": "details | total | count | highest | lowest"
    }}
    
    Notes:
    - Dates must be in 'MMM DD YYYY' format (e.g. Feb 01 2023).
    - If a whole year is mentioned (e.g. "2025"), return the full range: "Jan 01 2025" to "Dec 31 2025".
    - If no year is specified, assume 2023 or contextually relevant.
    """
    
    response_text, _ = llm_call(prompt)
    
    match = re.search(r"\{[\s\S]+\}", response_text)
    if match:
        try:
            return json.loads(match.group())
        except json.JSONDecodeError:
            pass
            
    return None

@st.cache_data(show_spinner=False)
def generate_human_response(query: str, invoices: list, total: float, min_inv: Any, max_inv: Any) -> Tuple[str, str]:
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
