from openai import OpenAI

async def initiate_huggingface_model(api_key=None):
    client = OpenAI(api_key=api_key, base_url="https://router.huggingface.co/v1")
    return client
