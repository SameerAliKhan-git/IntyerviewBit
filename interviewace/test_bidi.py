import os
import asyncio
from google import genai
from google.genai import types

async def main():
    key = "AIzaSyC9--PzoZPrSCIsRO3PcwWCEIYwcQVwT34"
    client = genai.Client(api_key=key)
    print("Testing bidiGenerateContent on gemini-2.0-flash-exp")
    try:
        async with client.aio.live.connect(model="gemini-2.0-flash") as session:
            print("Connected!")
            await session.send(input="Hello", end_of_turn=True)
            print("Message sent, waiting for response...")
            async for response in session.receive():
                if response.server_content is not None:
                    model_turn = response.server_content.model_turn
                    if model_turn:
                        for part in model_turn.parts:
                            if part.text:
                                print(f"Agent: {part.text}")
    except Exception as e:
        print(f"ERROR: {e}")

if __name__ == "__main__":
    asyncio.run(main())
