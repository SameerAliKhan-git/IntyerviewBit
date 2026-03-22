import os
from google import genai

api_key = os.environ.get("GEMINI_API_KEY")
if not api_key:
    raise EnvironmentError("GEMINI_API_KEY environment variable is not set. "
                           "Copy .env.example to .env and add your key.")
client = genai.Client(api_key=api_key)
for m in client.models.list():
    if 'bidi' in m.name or 'live' in m.name or 'audio' in m.name or '2.0-flash' in m.name:
        print(m.name)
