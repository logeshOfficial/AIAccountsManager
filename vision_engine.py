import io
import base64
import streamlit as st
from PIL import Image
from google import genai
from openai import OpenAI
from app_logger import get_logger

logger = get_logger(__name__)

@st.cache_resource
def get_gemini_client(api_key: str):
    return genai.Client(api_key=api_key)

@st.cache_resource
def get_openai_client(api_key: str):
    return OpenAI(api_key=api_key)

def extract_text_with_vision(image_bytes: bytes, file_name: str) -> str:
    """Extracts text from image bytes using a 3-tier fallback vision system."""
    ext = file_name.split('.')[-1].lower()
    mime_type = f"image/{ext if ext != 'jpg' else 'jpeg'}"
    
    logger.info(f"🔮 Vision Engine: Processing {file_name} (Mime: {mime_type}, Size: {len(image_bytes)} bytes)")

    # --- Tier 1: Gemini Vision ---
    try:
        gemini_key = st.secrets.get("gemini_api_key")
        if gemini_key:
            client = get_gemini_client(gemini_key)
            img = Image.open(io.BytesIO(image_bytes))
            prompt = "Extract all text from this invoice or receipt image. Preserve labels and values. Return the complete text content."
            
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

    # --- Tier 2: OpenAI Vision ---
    openai_key = st.secrets.get("openai_api_key")
    if openai_key and str(openai_key).startswith("sk-"):
        try:
            client = get_openai_client(openai_key)
            base64_image = base64.b64encode(image_bytes).decode('utf-8')
            
            # Use correct mime in data URI
            data_uri = f"data:{mime_type};base64,{base64_image}"
            
            response = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "Extract all text from this invoice image. Return complete content."},
                        {"type": "image_url", "image_url": {"url": data_uri}}
                    ]
                }],
                max_tokens=1000
            )
            
            if response.choices[0].message.content:
                logger.info(f"✓ Tier 2 (OpenAI Mini) extracted text from: {file_name}")
                return response.choices[0].message.content
        except Exception as e:
            logger.warning(f"✗ Tier 2 (OpenAI Mini) failed for {file_name}: {e}")

    logger.error(f"All vision fallback tiers failed for {file_name}")
    return ""
