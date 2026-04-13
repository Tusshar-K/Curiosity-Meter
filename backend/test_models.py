import sys
from google import genai
from app.core.config import settings

client = genai.Client(api_key=settings.GEMINI_API_KEY)
models = client.models.list()
for m in models:
    if 'embed' in m.name or 'embedding' in m.name:
        print(m.name, m.supported_actions)
