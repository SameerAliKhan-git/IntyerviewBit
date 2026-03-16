"""Manual websocket smoke test.

This file is intentionally not part of the automated test suite.
Set INTERVIEWACE_LIVE_SERVER_URL and run it directly if you want to
exercise a live local server.
"""

from __future__ import annotations

import asyncio
import json
import os


async def manual_websocket_smoke_test() -> None:
    import websockets

    url = os.getenv("INTERVIEWACE_LIVE_SERVER_URL")
    if not url:
        raise RuntimeError("Set INTERVIEWACE_LIVE_SERVER_URL to run this smoke test.")

    async with websockets.connect(url) as websocket:
        await websocket.send(
            json.dumps(
                {
                    "type": "text",
                    "text": "Hello Coach Ace, I am ready for interview practice.",
                }
            )
        )
        for _ in range(5):
            response = await asyncio.wait_for(websocket.recv(), timeout=15.0)
            print(response)


if __name__ == "__main__":
    asyncio.run(manual_websocket_smoke_test())
