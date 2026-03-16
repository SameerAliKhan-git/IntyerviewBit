import json
import asyncio
from typing import Dict, Any
from fastapi import WebSocket

# session_id -> (WebSocket, asyncio.AbstractEventLoop)
_active_websockets: Dict[str, tuple[WebSocket, asyncio.AbstractEventLoop]] = {}

def register_ws(session_id: str, ws: WebSocket):
    loop = asyncio.get_running_loop()
    _active_websockets[session_id] = (ws, loop)

def unregister_ws(session_id: str):
    _active_websockets.pop(session_id, None)

def send_tool_result_sync(session_id: str, tool_name: str, response_data: dict):
    """Called by synchronous tools to send their result down the WebSocket."""
    if not _active_websockets:
        return
        
    if session_id in _active_websockets:
        ws, loop = _active_websockets[session_id]
    else:
        # Fallback for LLM hallucinated session IDs like "default"
        ws, loop = next(iter(_active_websockets.values()))
    
    # We send a custom event that mimics what the UI expects or what we can easily parse
    payload = {
        "customToolResponse": {
            "name": tool_name,
            "response": response_data
        }
    }
    
    async def _send():
        try:
            await ws.send_text(json.dumps(payload))
        except Exception as e:
            print(f"Error sending tool result: {e}")
            pass
            
    # Schedule threadsafe operation
    if loop.is_running():
        asyncio.run_coroutine_threadsafe(_send(), loop)
