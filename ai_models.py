from openai import OpenAI

def initiate_huggingface_model(api_key=None, base_url="https://router.huggingface.co/v1"):
    try: 
        client = OpenAI(api_key=api_key, base_url=base_url)
        return client
    except Exception as e:
        raise Exception("Error initiating Huggingface model: ", e)