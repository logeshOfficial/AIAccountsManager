# from mistralai import Mistral
# import google.generativeai as genai
from openai import OpenAI

import os
from dotenv import load_dotenv
load_dotenv()  # Load from .env file

def initiate_huggingface_model(api_key=None):
    client = OpenAI(api_key=api_key, base_url="https://router.huggingface.co/v1")
    return client

def initiate_openai_model():
    OPENAI_API_KEY = os.getenv("api_key")  
    client = OpenAI(api_key=OPENAI_API_KEY)
    MODEL = os.getenv("model", "gpt-4.1")
    return {
        "client": client,
        "model": MODEL
    }

def initiate_deepseek_model():
    OPENAI_API_KEY = os.getenv("api_key")  
    client = OpenAI(api_key=OPENAI_API_KEY, base_url="https://api.deepseek.com")
    MODEL = os.getenv("model", "deepseek-chat")
    return {
        "client": client,
        "model": MODEL
    }
    
def initiate_mistral_model():
    MISTRAL_API_KEY = os.getenv("api_key")  
    MODEL = os.getenv("model", "ministral-8b-2512")
    client = Mistral(api_key=MISTRAL_API_KEY)
    return {
        "client": client,
        "model": MODEL
    }

def initiate_gemini_model():
    GEMINI_API_KEY = os.getenv("api_key")  
    MODEL = os.getenv("model", "gemini-2.5-flash-lite")
    genai.configure(api_key=GEMINI_API_KEY)
    model = genai.GenerativeModel(MODEL)
    return model
