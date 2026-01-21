from openai import OpenAI
import google.generativeai as genai
from groq import Groq
from app_logger import get_logger

logger = get_logger(__name__)

def initiate_huggingface_model(api_key=None, base_url="https://router.huggingface.co/v1"):
    try: 
        client = OpenAI(api_key=api_key, base_url=base_url)
        return client
    except Exception as e:
        logger.error(f"Error initiating Huggingface model: {e}")
        raise Exception("Error initiating Huggingface model: ", e)

def initiate_gemini_model(api_key=None):
    try:
        genai.configure(api_key=api_key)
        return genai
    except Exception as e:
        logger.error(f"Error initiating Gemini model: {e}")
        raise Exception("Error initiating Gemini model: ", e)

def initiate_groq_model(api_key=None):
    try:
        client = Groq(api_key=api_key)
        return client
    except Exception as e:
        logger.error(f"Error initiating Groq model: {e}")
        raise Exception("Error initiating Groq model: ", e)