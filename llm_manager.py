import streamlit as st
import json
from openai import OpenAI
from google import genai
from groq import Groq
import re
from typing import Tuple, Dict, Optional, Any
from google.genai import types
from datetime import datetime
from langchain_openai import ChatOpenAI
from langchain_groq import ChatGroq
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
        return OpenAI(api_key=api_key, base_url=base_url)
    except Exception as e:
        logger.error(f"Failed to initialize Primary Client: {e}")
        return None

@st.cache_resource
def get_groq_client():
    """Initializes the Groq AI client."""
    api_key = st.secrets.get("groq_api_key")
    
    if not api_key:
        return None
        
    try:
        return Groq(api_key=api_key)
    except Exception:
        return None

@st.cache_resource
def get_fallback_client():
    """Initializes the fallback AI client (Gemini)."""
    api_key = st.secrets.get("gemini_api_key")
    if not api_key:
        return None
    try:
        return genai.Client(api_key=api_key)
    except Exception:
        return None

def get_agent_llm():
    """
    Standardized LangChain-compatible LLM provider with fallback logic.
    Priority: Groq (llama-3.3-70b) -> OpenAI (gpt-4o-mini) -> Gemini (1.5-flash)
    """
    # 1. Try Groq (Fastest)
    groq_key = st.secrets.get("groq_api_key")
    if groq_key:
        try:
            return ChatGroq(api_key=groq_key, model_name="llama-3.3-70b-versatile", timeout=10)
        except Exception as e:
            logger.warning(f"Failed to init ChatGroq: {e}")

    # 2. Try OpenAI (Smartest fallback)
    openai_key = st.secrets.get("openai_api_key")
    if openai_key:
        try:
            return ChatOpenAI(api_key=openai_key, model="gpt-4o-mini")
        except Exception as e:
            logger.warning(f"Failed to init ChatOpenAI: {e}")

    # 3. Final Fallback (If strictly needed - use Groq with default settings if keys exist)
    logger.error("No reliable agent LLM could be initialized.")
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
                max_tokens=5000
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
                max_tokens=5000
            )
            
            logger.info(f"LLM Call successful using Groq fallback: {model_name}")
            return response.choices[0].message.content.strip(), model_name
        except Exception as e:
            logger.warning(f"Groq fallback model failed: {e}")
            groq_error = e
            # st.warning(f"Groq model encountered an error: {e}. Attempting fallback to Gemini...")

    # --- Attempt 3: Fallback Model (Gemini) ---
    gemini_client = get_fallback_client()
    gemini_error= None
    
    if gemini_client:
        # Rotation for Gemini fallback
        gemini_variants = [
            st.secrets.get("gemini_model", DEFAULT_FALLBACK_MODEL),
            "gemini-1.5-flash-latest",
            "gemini-2.0-flash-exp",
            "gemini-1.5-pro-latest"
        ]
        
        for model_id in gemini_variants:
            try:
                response = gemini_client.models.generate_content(
                    model=model_id,
                    contents=prompt,
                    config=types.GenerateContentConfig(
                        system_instruction="You are a precise financial invoice assistant."
                    )
                )
                if response.text:
                    logger.info(f"LLM Call successful using Gemini fallback: {model_id}")
                    return response.text.strip(), model_id
            except Exception as e:
                logger.warning(f"Gemini {model_id} failed: {e}")
                gemini_error = e
                continue
            
    # --- Failure ---
    if primary_error:
        logger.error(f"Original error (Primary): {primary_error}")
        st.error(f"Original error (Primary): {primary_error}")
    if groq_error:
        logger.error(f"Secondary error (Groq): {groq_error}")
        st.error(f"Secondary error (Groq): {groq_error}")
    if gemini_error:
        logger.error(f"Tertiary error (Gemini): {gemini_error}")
        st.error(f"Tertiary error (Gemini): {gemini_error}")
    
    return "{}", "None"

