"""Manual API key smoke test.

Reads GOOGLE_API_KEY from the environment and runs only when executed directly.
"""

from __future__ import annotations

import os


def main() -> None:
    from google import genai

    api_key = os.getenv("GOOGLE_API_KEY")
    if not api_key:
        raise RuntimeError("Set GOOGLE_API_KEY before running this smoke test.")

    client = genai.Client(api_key=api_key)
    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents="Tell me a one-line joke.",
    )
    print(response.text)


if __name__ == "__main__":
    main()
