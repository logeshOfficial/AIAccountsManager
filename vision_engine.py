import io
import base64
import streamlit as st
from PIL import Image
from google import genai
from openai import OpenAI
from transformers import pipeline
from app_logger import get_logger

logger = get_logger(__name__)

@st.cache_resource
def get_hf_pipeline():
    """Loads and caches the Hugging Face OCR pipeline (TrOCR)."""
    # Using TrOCR which is a dedicated OCR model (reads text instead of just describing)
    model_id = "microsoft/trocr-base-printed"
    logger.info(f"📦 Loading Hugging Face OCR Model ({model_id})...")
    try:
        # Note: TrOCR is used with 'image-to-text' pipeline as well
        return pipeline("image-to-text", model=model_id)
    except Exception as e:
        logger.error(f"Failed to load HF pipeline: {e}")
        return None

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

    # --- Tier 1: Gemini Vision (Multi-Model Rotation) ---
    try:
        gemini_key = st.secrets.get("gemini_api_key")
        if gemini_key:
            client = get_gemini_client(gemini_key)
            img = Image.open(io.BytesIO(image_bytes))
            prompt = "Extract all text from this invoice or receipt image. Preserve labels and values. Return the complete text content."
            
            # List of models to try in order of efficiency/reliability
            gemini_models = [
                'gemini-1.5-flash-latest', 'gemini-1.5-pro-latest',
                'gemini-1.5-flash', 'gemini-1.5-pro', 'gemini-2.0-flash-exp'
            ]
            
            for model_id in gemini_models:
                for attempt in range(2): # Retry once on transient failures
                    try:
                        response = client.models.generate_content(
                            model=model_id,
                            contents=[prompt, img]
                        )
                        if response.text:
                            logger.info(f"✓ Tier 1 (Gemini {model_id}) extracted text.")
                            return response.text
                    except Exception as model_e:
                        err_str = str(model_e).lower()
                        if "404" in err_str:
                            break # This model isn't available, try next model ID
                        if "429" in err_str or "exhausted" in err_str:
                            logger.warning(f"⏳ Tier 1 ({model_id}) quota exhausted. Waiting 5s...")
                            import time
                            time.sleep(5)
                            continue # Retry current model once
                        logger.warning(f"Tier 1 ({model_id}) failed: {model_e}")
                        break # Try next model ID
    except Exception as e:
        logger.warning(f"✗ Tier 1 (Gemini) major failure for {file_name}: {e}")

    # --- Tier 2: OpenAI Vision ---
    try:
        openai_key = st.secrets.get("openai_api_key")
        if openai_key and str(openai_key).startswith("sk-"):
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

    # --- Tier 3: Hugging Face Local Fallback (OCR) ---
    try:
        logger.info("🔄 Falling back to Tier 3: Hugging Face Local OCR (TrOCR)...")
        pipe = get_hf_pipeline()
        if pipe:
            img = Image.open(io.BytesIO(image_bytes))
            result = pipe(img)
            if result and len(result) > 0:
                extracted_text = result[0].get('generated_text', '')
                logger.info(f"✓ Tier 3 (Hugging Face TrOCR) extracted: {extracted_text}")
                return extracted_text
    except Exception as e:
        logger.error(f"✗ Tier 3 (Hugging Face) failed for {file_name}: {e}")

    logger.error(f"All vision fallback tiers failed for {file_name}")
    return ""
