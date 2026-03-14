"""
InterviewAce — Main FastAPI Application with WebSocket Handler.
Implements the ADK Gemini Live API Toolkit bidirectional streaming pattern
for real-time voice + video interview coaching.

Architecture follows the official ADK bidi-demo pattern:
  1. Application Initialization: Agent, SessionService, Runner at startup
  2. Session Initialization: Session, RunConfig, LiveRequestQueue per connection
  3. Bidirectional Streaming: Concurrent upstream/downstream async tasks
  4. Graceful Termination: Proper cleanup of resources
"""

import os
import json
import asyncio
import base64
import uuid
import traceback
from contextlib import asynccontextmanager

from dotenv import load_dotenv

load_dotenv(override=True)

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from google.adk.agents.llm_agent import Agent
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.adk.agents.live_request_queue import LiveRequestQueue
from google.adk.agents.run_config import RunConfig, StreamingMode
from google.genai import types

from interview_coach_agent.agent import root_agent

# ─────────────────────────────────────────────
# Application Initialization (Startup)
# ─────────────────────────────────────────────

session_service = InMemorySessionService()
runner = Runner(
    app_name="interviewace",
    agent=root_agent,
    session_service=session_service,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler for startup/shutdown."""
    print("═" * 60)
    print("  🎯 InterviewAce — AI Interview Coach")
    print("  Built with Google ADK & Gemini Live API")
    print("═" * 60)
    print(f"  Agent: {root_agent.name}")
    print(f"  Model: {root_agent.model}")
    print("═" * 60)
    yield
    print("\n🛑 InterviewAce shutting down...")


app = FastAPI(
    title="InterviewAce",
    description="AI-powered real-time interview coach",
    version="1.0.0",
    lifespan=lifespan,
)

# Mount static files (frontend)
STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/")
async def serve_index():
    """Serve the main frontend UI."""
    return FileResponse(os.path.join(STATIC_DIR, "index.html"))


@app.get("/health")
async def health_check():
    """Health check endpoint for Cloud Run."""
    return {"status": "healthy", "agent": root_agent.name, "model": root_agent.model}


# ─────────────────────────────────────────────
# WebSocket Handler — Bidirectional Streaming
# ─────────────────────────────────────────────

@app.websocket("/ws/{user_id}/{session_id}")
async def websocket_handler(websocket: WebSocket, user_id: str, session_id: str):
    """
    WebSocket endpoint for bidirectional streaming with the interview coach agent.
    
    Implements the ADK Live API Toolkit pattern:
    - Upstream task: Client → LiveRequestQueue (audio/video/text input)
    - Downstream task: run_live() events → Client (agent responses)
    """
    await websocket.accept()
    print(f"\n🔗 New connection: user={user_id}, session={session_id}")

    # ── Create or retrieve session ──
    session = await session_service.get_session(
        app_name="interviewace",
        user_id=user_id,
        session_id=session_id,
    )
    if session is None:
        session = await session_service.create_session(
            app_name="interviewace",
            user_id=user_id,
            session_id=session_id,
        )
        print(f"  ✅ Created new session: {session.id}")
    else:
        print(f"  ♻️  Resumed session: {session.id}")

    # ── Configure RunConfig based on model ──
    model_name = root_agent.model or ""
    
    if "flash" in model_name:
        # Native Audio Model — full audio bidi streaming
        run_config = RunConfig(
            streaming_mode=StreamingMode.BIDI,
            response_modalities=["AUDIO"],
            input_audio_transcription=types.AudioTranscriptionConfig(),
            output_audio_transcription=types.AudioTranscriptionConfig(),
            session_resumption=types.SessionResumptionConfig(
                handle=None,
            ),
            speech_config=types.SpeechConfig(
                voice_config=types.VoiceConfig(
                    prebuilt_voice_config=types.PrebuiltVoiceConfig(
                        voice_name="Kore"  # Professional, warm voice for Coach Ace
                    )
                )
            ),
        )
        print("  🎙️  Mode: Native Audio (full bidi streaming)")
    else:
        # Half-cascade model — text-based responses
        run_config = RunConfig(
            streaming_mode=StreamingMode.BIDI,
            response_modalities=["TEXT"],
            input_audio_transcription=types.AudioTranscriptionConfig(),
            output_audio_transcription=None,
            session_resumption=types.SessionResumptionConfig(
                handle=None,
            ),
        )
        print("  📝 Mode: Text response (half-cascade)")

    # ── Initialize LiveRequestQueue ──
    live_request_queue = LiveRequestQueue()

    # ── Define concurrent tasks ──
    
    async def upstream_task():
        """Receives WebSocket messages and forwards to LiveRequestQueue.
        Handles text, audio binary, and image/video data."""
        try:
            while True:
                try:
                    # Try receiving text message first
                    data = await websocket.receive()
                    
                    if "text" in data:
                        msg = json.loads(data["text"])
                        msg_type = msg.get("type", "text")
                        
                        if msg_type == "text":
                            # Text message from user
                            text_content = msg.get("content", "")
                            if text_content:
                                content = types.Content(
                                    role="user",
                                    parts=[types.Part(text=text_content)],
                                )
                                live_request_queue.send_content(content)
                                print(f"  📤 Text: {text_content[:80]}...")
                        
                        elif msg_type == "image":
                            # Image/video frame (base64 encoded)
                            image_data = msg.get("data", "")
                            mime_type = msg.get("mimeType", "image/jpeg")
                            if image_data:
                                decoded = base64.b64decode(image_data)
                                blob = types.Blob(
                                    mime_type=mime_type,
                                    data=decoded,
                                )
                                live_request_queue.send_realtime(blob)
                        
                        elif msg_type == "audio_config":
                            # Audio configuration (not actual audio data)
                            print(f"  🔧 Audio config received")
                    
                    elif "bytes" in data:
                        # Raw binary audio data
                        audio_bytes = data["bytes"]
                        if audio_bytes:
                            blob = types.Blob(
                                mime_type="audio/pcm;rate=16000",
                                data=audio_bytes,
                            )
                            live_request_queue.send_realtime(blob)
                
                except WebSocketDisconnect:
                    print(f"  🔌 Client disconnected: {user_id}")
                    break
                except Exception as e:
                    if "disconnect" in str(e).lower() or "close" in str(e).lower():
                        break
                    print(f"  ⚠️  Upstream error: {e}")
                    traceback.print_exc()
                    break
        finally:
            print(f"  ⬆️  Upstream task ended for {user_id}")

    async def downstream_task():
        """Processes run_live() events and sends to WebSocket client.
        Handles audio responses, text transcriptions, and tool calls."""
        try:
            async for event in runner.run_live(
                session=session,
                live_request_queue=live_request_queue,
                run_config=run_config,
            ):
                # Convert event to a serializable format
                event_dict = {
                    "type": "event",
                    "author": getattr(event, "author", "agent"),
                    "partial": getattr(event, "partial", False),
                    "turn_complete": getattr(event, "turn_complete", False),
                    "server_content": None,
                    "actions": None,
                }
                
                # Handle different content types in the event
                if hasattr(event, "content") and event.content:
                    content = event.content
                    if hasattr(content, "parts") and content.parts:
                        for part in content.parts:
                            # Text content
                            if hasattr(part, "text") and part.text:
                                text_msg = {
                                    "type": "text",
                                    "content": part.text,
                                    "author": event_dict["author"],
                                    "partial": event_dict["partial"],
                                    "turn_complete": event_dict["turn_complete"],
                                }
                                await websocket.send_text(json.dumps(text_msg))
                            
                            # Audio content (inline data)
                            if hasattr(part, "inline_data") and part.inline_data:
                                inline = part.inline_data
                                if hasattr(inline, "data") and inline.data:
                                    audio_msg = {
                                        "type": "audio",
                                        "data": base64.b64encode(inline.data).decode("utf-8"),
                                        "mimeType": getattr(inline, "mime_type", "audio/pcm;rate=24000"),
                                    }
                                    await websocket.send_text(json.dumps(audio_msg))

                # Handle transcriptions
                if hasattr(event, "server_content"):
                    sc = event.server_content
                    if sc and hasattr(sc, "input_transcription") and sc.input_transcription:
                        trans_msg = {
                            "type": "input_transcription",
                            "content": sc.input_transcription,
                        }
                        await websocket.send_text(json.dumps(trans_msg))
                    
                    if sc and hasattr(sc, "output_transcription") and sc.output_transcription:
                        trans_msg = {
                            "type": "output_transcription",
                            "content": sc.output_transcription,
                        }
                        await websocket.send_text(json.dumps(trans_msg))

                # Handle tool calls/actions (for dashboard score updates) 
                if hasattr(event, "actions") and event.actions:
                    if hasattr(event.actions, "function_calls"):
                        for fc in event.actions.function_calls:
                            if fc.name == "save_session_feedback":
                                # Send score update to dashboard
                                score_msg = {
                                    "type": "score_update",
                                    "data": dict(fc.args) if hasattr(fc, "args") else {},
                                }
                                await websocket.send_text(json.dumps(score_msg))

                # Turn complete signal
                if getattr(event, "turn_complete", False):
                    turn_msg = {"type": "turn_complete"}
                    await websocket.send_text(json.dumps(turn_msg))

        except Exception as e:
            if "disconnect" not in str(e).lower() and "close" not in str(e).lower():
                print(f"  ⚠️  Downstream error: {e}")
                traceback.print_exc()
        finally:
            print(f"  ⬇️  Downstream task ended for {user_id}")

    # ── Run both tasks concurrently ──
    upstream = asyncio.create_task(upstream_task())
    downstream = asyncio.create_task(downstream_task())

    try:
        # Wait for either task to complete (usually upstream when client disconnects)
        done, pending = await asyncio.wait(
            [upstream, downstream],
            return_when=asyncio.FIRST_COMPLETED,
        )
        
        # Cancel the remaining task
        for task in pending:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
    except Exception as e:
        print(f"  ❌ Session error: {e}")
    finally:
        # Graceful cleanup
        live_request_queue.close()
        try:
            await websocket.close()
        except Exception:
            pass
        print(f"  🏁 Session ended: user={user_id}, session={session_id}\n")


# ─────────────────────────────────────────────
# Run with Uvicorn
# ─────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn

    port = int(os.getenv("PORT", 8080))
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=port,
        reload=True,
        log_level="info",
    )
