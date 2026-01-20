from openai import OpenAI
import google.generativeai as genai

def initiate_huggingface_model(api_key=None, base_url="https://router.huggingface.co/v1"):
    try: 
        client = OpenAI(api_key=api_key, base_url=base_url)
        return client
    except Exception as e:
        raise Exception("Error initiating Huggingface model: ", e)

def initiate_gemini_model(api_key=None):
    try:
        genai.configure(api_key=api_key)
        return genai
    except Exception as e:
        raise Exception("Error initiating Gemini model: ", e)