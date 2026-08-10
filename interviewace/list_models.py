"""Developer utility: lists Gemini models that support live/bidi streaming.

Run directly when you need to confirm which Live API models your key can reach:
    python list_models.py
"""

from __future__ import annotations

import os


def main() -> None:
    from google import genai

    # GOOGLE_API_KEY is the name the google-genai SDK and the app itself use.
    api_key = os.getenv("GOOGLE_API_KEY")
    if not api_key:
        raise SystemExit(
            "GOOGLE_API_KEY is not set. Copy .env.example to .env and add your key."
        )

    client = genai.Client(api_key=api_key)
    for model in client.models.list():
        name = model.name
        if any(marker in name for marker in ("bidi", "live", "audio", "2.0-flash")):
            print(name)


if __name__ == "__main__":
    main()
