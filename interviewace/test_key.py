import os
from google import genai

key = "AIzaSyC9--PzoZPrSCIsRO3PcwWCEIYwcQVwT34"
print(f"Testing key: {key}")
try:
    client = genai.Client(api_key=key)
    response = client.models.generate_content(
        model='gemini-2.5-flash',
        contents='Tell me a joke.'
    )
    print("SUCCESS")
    print(response.text)
except Exception as e:
    print(f"ERROR: {e}")
