import asyncio
import websockets
import json

async def test_websocket():
    url = "ws://localhost:8080/ws/test_user/test_session"
    print(f"Connecting to {url}...")
    try:
        async with websockets.connect(url) as websocket:
            print("Connected! Sending a text request to the Gemini Live Agent...")
            msg = {"type": "text", "content": "Hello, I am ready for my interview."}
            await websocket.send(json.dumps(msg))
            
            print("Waiting for response from the Agent...")
            for _ in range(5): # Wait for up to 5 events
                try:
                    response = await asyncio.wait_for(websocket.recv(), timeout=10.0)
                    resp_data = json.loads(response)
                    msg_type = resp_data.get("type")
                    if msg_type == "text":
                        print(f"AGENT TEXT: {resp_data.get('content')}")
                    elif msg_type == "audio":
                        print(f"AGENT AUDIO: Received {len(resp_data.get('data', ''))} bytes of base64 audio")
                    elif msg_type == "score_update":
                        print(f"AGENT SCORE UPDATE: {resp_data.get('data')}")
                    else:
                        print(f"AGENT MESSAGE: {msg_type}")
                except asyncio.TimeoutError:
                    print("Timeout waiting for more messages.")
                    break
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    asyncio.run(test_websocket())
