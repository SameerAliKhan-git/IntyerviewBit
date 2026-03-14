"""Direct test of Live API connection to verify the API key works for bidi streaming."""
import asyncio
import os
os.environ["SSL_CERT_FILE"] = ""  # Will be set externally

from google import genai

async def main():
    key = "AIzaSyCnihpm_6suwKpC3OLQ04_TTJSFBuaYVxA"
    client = genai.Client(api_key=key)
    
    # First test: simple generate_content (this works)
    print("Test 1: Simple text generation...")
    try:
        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents='Say hello in one sentence.'
        )
        print(f"  ✅ Text generation works: {response.text[:100]}")
    except Exception as e:
        print(f"  ❌ Text generation failed: {e}")
    
    # Second test: Live API with gemini-2.5-flash-native-audio-preview-12-2025
    print("\nTest 2: Live API (bidi streaming)...")
    try:
        config = {"response_modalities": ["TEXT"]}
        async with client.aio.live.connect(
            model="gemini-2.5-flash-native-audio-preview-12-2025",
            config=config
        ) as session:
            print("  ✅ Live API connected!")
            await session.send(input="Hello! Say hi back in one sentence.", end_of_turn=True)
            async for response in session.receive():
                if response.server_content is not None:
                    model_turn = response.server_content.model_turn
                    if model_turn:
                        for part in model_turn.parts:
                            if part.text:
                                print(f"  🤖 Agent says: {part.text}")
                    if response.server_content.turn_complete:
                        print("  ✅ Turn complete!")
                        break
    except Exception as e:
        print(f"  ❌ Live API failed: {e}")
    
    # Third test: Try with gemini-2.0-flash-live-001
    print("\nTest 3: Live API with gemini-2.0-flash-live-001...")
    try:
        config = {"response_modalities": ["TEXT"]}
        async with client.aio.live.connect(
            model="gemini-2.0-flash-live-001",
            config=config
        ) as session:
            print("  ✅ Connected!")
            await session.send(input="Hi! What's your name?", end_of_turn=True)
            async for response in session.receive():
                if response.server_content is not None:
                    model_turn = response.server_content.model_turn
                    if model_turn:
                        for part in model_turn.parts:
                            if part.text:
                                print(f"  🤖 Agent says: {part.text}")
                    if response.server_content.turn_complete:
                        print("  ✅ Turn complete!")
                        break
    except Exception as e:
        print(f"  ❌ Failed: {e}")

if __name__ == "__main__":
    asyncio.run(main())
