"""Test client to verify the full ADK Live API interaction works end-to-end."""
import asyncio
import json
import websockets

async def test_websocket():
    url = "ws://localhost:8080/ws/test_user/test_session_2"
    print(f"Connecting to {url}...")
    try:
        async with websockets.connect(url) as ws:
            print("✅ Connected!")

            # Send a text message to the agent
            msg = {"type": "text", "text": "Hello Coach Ace! I am ready for my interview practice."}
            print(f"📤 Sending: {msg['text']}")
            await ws.send(json.dumps(msg))

            print("⏳ Waiting for agent response events...")
            for _ in range(20):
                try:
                    response = await asyncio.wait_for(ws.recv(), timeout=15.0)
                    evt = json.loads(response)

                    # Parse official ADK event format
                    if "content" in evt and evt["content"] and "parts" in evt["content"]:
                        for part in evt["content"]["parts"]:
                            if "text" in part and part["text"]:
                                print(f"🤖 AGENT TEXT: {part['text'][:200]}")
                            if "inline_data" in part:
                                print(f"🔊 AGENT AUDIO: received audio chunk")
                    
                    if "server_content" in evt and evt["server_content"]:
                        sc = evt["server_content"]
                        if "input_transcription" in sc and sc["input_transcription"]:
                            print(f"🎤 USER TRANSCRIPT: {sc['input_transcription']}")
                        if "output_transcription" in sc and sc["output_transcription"]:
                            print(f"🤖 AGENT TRANSCRIPT: {sc['output_transcription'][:200]}")

                    if "actions" in evt and evt["actions"]:
                        print(f"🔧 TOOL CALL: {json.dumps(evt['actions'])[:200]}")

                    if evt.get("turn_complete"):
                        print("✅ Turn complete!")
                        break

                except asyncio.TimeoutError:
                    print("⏰ Timeout waiting for more messages.")
                    break

            print("🏁 Test complete!")

    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_websocket())
