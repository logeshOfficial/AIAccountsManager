import io
import base64
import streamlit as st
from PIL import Image
from google import genai
from openai import OpenAI
from app_logger import get_logger

logger = get_logger(__name__)

def extract_text_with_vision(image_bytes: bytes, file_name: str) -> str:
    """
    Extracts text from image bytes using a 3-tier fallback vision system.
    Tier 1: Gemini Vision (Flash -> Pro)
    Tier 2: OpenAI GPT-4o-mini
    Tier 3: OpenAI GPT-4o
    """
    
    # --- Tier 1: Gemini Vision ---
    try:
        gemini_key = st.secrets.get("gemini_api_key")
        if gemini_key:
            client = genai.Client(api_key=gemini_key)
            img = Image.open(io.BytesIO(image_bytes))
            prompt = "Extract all text from this invoice image. Return the complete text content."
            
            try:
                response = client.models.generate_content(
                    model='gemini-1.5-flash',
                    contents=[prompt, img]
                )
            except Exception as flash_e:
                logger.warning(f"Tier 1 (Gemini Flash) failed, trying Pro: {flash_e}")
                response = client.models.generate_content(
                    model='gemini-1.5-pro',
                    contents=[prompt, img]
                )
            
            if response.text:
                logger.info(f"✓ Tier 1 (Gemini) extracted text from: {file_name}")
                return response.text
    except Exception as e:
        logger.warning(f"✗ Tier 1 (Gemini) failed for {file_name}: {e}")

    # --- Tier 2: OpenAI Vision Mini ---
    openai_key = st.secrets.get("openai_api_key")
    if openai_key and openai_key.startswith("sk-"):
        try:
            client = OpenAI(api_key=openai_key)
            base64_image = base64.b64encode(image_bytes).decode('utf-8')
            
            response = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "Extract all text from this invoice image. Return the complete text content."},
                        {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{base64_image}"}}
                    ]
                }],
                max_tokens=1000
            )
            
            if response.choices[0].message.content:
                logger.info(f"✓ Tier 2 (OpenAI Mini) extracted text from: {file_name}")
                return response.choices[0].message.content
        except Exception as e:
            logger.warning(f"✗ Tier 2 (OpenAI Mini) failed for {file_name}: {e}")

    # --- Tier 3: OpenAI Vision Premium ---
    if openai_key and openai_key.startswith("sk-"):
        try:
            client = OpenAI(api_key=openai_key)
            base64_image = base64.b64encode(image_bytes).decode('utf-8')
            
            response = client.chat.completions.create(
                model="gpt-4o",
                messages=[{
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "Extract all text from this invoice image. Return the complete text content."},
                        {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{base64_image}"}}
                    ]
                }],
                max_tokens=1500
            )
            
            if response.choices[0].message.content:
                logger.info(f"✓ Tier 3 (OpenAI Premium) extracted text from: {file_name}")
                return response.choices[0].message.content
        except Exception as e:
            logger.error(f"✗ Tier 3 (OpenAI Premium) failed for {file_name}: {e}")

    logger.error(f"All vision fallback tiers failed for {file_name}")
    return ""
