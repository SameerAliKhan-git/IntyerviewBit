"""Manual Live API bidi smoke test.

This script is intentionally opt-in and is not collected by the automated test suite.
"""

from __future__ import annotations

import asyncio
import os


async def manual_bidi_smoke_test() -> None:
    from google import genai

    api_key = os.getenv("GOOGLE_API_KEY")
    if not api_key:
        raise RuntimeError("Set GOOGLE_API_KEY before running this smoke test.")

    client = genai.Client(api_key=api_key)
    config = {"response_modalities": ["TEXT"]}
    async with client.aio.live.connect(
        model="gemini-2.5-flash-native-audio-preview-12-2025",
        config=config,
    ) as session:
        await session.send(input="Say hello in one sentence.", end_of_turn=True)
        async for response in session.receive():
            if response.server_content is not None:
                model_turn = response.server_content.model_turn
                if model_turn:
                    for part in model_turn.parts:
                        if part.text:
                            print(part.text)
                if response.server_content.turn_complete:
                    break


if __name__ == "__main__":
    asyncio.run(manual_bidi_smoke_test())
