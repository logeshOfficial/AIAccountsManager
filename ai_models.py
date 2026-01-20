from openai import OpenAI

def initiate_huggingface_model(api_key=None):
    try: 
        client = OpenAI(api_key=api_key, base_url="https://router.huggingface.co/v1")
        return client
    except Exception as e:
        raise Exception("Error initiating Huggingface model: ", e)