import os
from google import genai
client = genai.Client(api_key="AIzaSyC9--PzoZPrSCIsRO3PcwWCEIYwcQVwT34")
for m in client.models.list():
    if 'bidi' in m.name or 'live' in m.name or 'audio' in m.name or '2.0-flash' in m.name:
        print(m.name)
