"""
InterviewAce — Main FastAPI Application with WebSocket Handler.
Implements the ADK Gemini Live API Toolkit bidirectional streaming pattern
for real-time voice + video interview coaching.

Architecture follows the official ADK bidi-demo pattern exactly:
  1. Application Initialization: Agent, SessionService, Runner at startup
  2. Session Initialization: Session, RunConfig, LiveRequestQueue per connection
  3. Bidirectional Streaming: Concurrent upstream/downstream async tasks
  4. Graceful Termination: Proper cleanup of resources
"""

import asyncio
import base64
import json
import logging
import warnings
from pathlib import Path

from dotenv import load_dotenv

# Load environment variables from .env file BEFORE importing agent
load_dotenv(Path(__file__).parent.parent / ".env", override=True)

# pylint: disable=wrong-import-position
from fastapi import FastAPI, WebSocket, WebSocketDisconnect  # noqa: E402
from fastapi.responses import FileResponse  # noqa: E402
from fastapi.staticfiles import StaticFiles  # noqa: E402
from google.adk.agents.live_request_queue import LiveRequestQueue  # noqa: E402
from google.adk.agents.run_config import RunConfig, StreamingMode  # noqa: E402
from google.adk.runners import Runner  # noqa: E402
from google.adk.sessions import InMemorySessionService  # noqa: E402
from google.genai import types  # noqa: E402

from interview_coach_agent.agent import root_agent  # noqa: E402

# Configure logging
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# Suppress Pydantic serialization warnings
warnings.filterwarnings("ignore", category=UserWarning, module="pydantic")

# Application name constant
APP_NAME = "interviewace"

# ========================================
app = FastAPI(title="InterviewAce", version="1.0.0")

# Mount static files
static_dir = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=static_dir), name="static")

# Define your session service
session_service = InMemorySessionService()

# Define your runner
runner = Runner(app_name=APP_NAME, agent=root_agent, session_service=session_service)


# ========================================
@app.get("/")
async def root():
    """Serve the index.html page."""
    return FileResponse(Path(__file__).parent / "static" / "index.html")


@app.get("/health")
async def health():
    """Health check for Cloud Run."""
    return {"status": "healthy", "agent": root_agent.name, "model": root_agent.model}


# ========================================
@app.websocket("/ws/{user_id}/{session_id}")
async def websocket_endpoint(
    websocket: WebSocket,
    user_id: str,
    session_id: str,
    voice: str = "Kore",
) -> None:
    """WebSocket endpoint for bidirectional streaming with ADK.

    This follows the EXACT official ADK bidi-demo pattern.
    Accepts a 'voice' query parameter for selecting the agent's voice.
    """
    logger.info(
        f"WebSocket connection: user={user_id}, session={session_id}, voice={voice}"
    )
    await websocket.accept()
    logger.info("WebSocket connection accepted")

    # ========================================
    # Phase 2: Session Initialization
    # ========================================

    model_name = root_agent.model or ""
    is_native_audio = "native-audio" in model_name.lower() or "gemini-2" in model_name.lower() or "gemini-live" in model_name.lower()

    if is_native_audio:
        run_config = RunConfig(
            streaming_mode=StreamingMode.BIDI,
            response_modalities=["AUDIO"],
            input_audio_transcription=types.AudioTranscriptionConfig(),
            output_audio_transcription=types.AudioTranscriptionConfig(),
            session_resumption=types.SessionResumptionConfig(),
            speech_config=types.SpeechConfig(
                voice_config=types.VoiceConfig(
                    prebuilt_voice_config=types.PrebuiltVoiceConfig(
                        voice_name=voice
                    )
                )
            ),
        )
        logger.info(f"Native audio model: {model_name}, voice={voice}, AUDIO modality")
    else:
        run_config = RunConfig(
            streaming_mode=StreamingMode.BIDI,
            response_modalities=["TEXT"],
            input_audio_transcription=None,
            output_audio_transcription=None,
            session_resumption=types.SessionResumptionConfig(),
        )
        logger.info(f"Half-cascade model detected: {model_name}, using TEXT modality")

    # Get or create session
    session = await session_service.get_session(
        app_name=APP_NAME, user_id=user_id, session_id=session_id
    )
    if not session:
        await session_service.create_session(
            app_name=APP_NAME, user_id=user_id, session_id=session_id
        )
        logger.info(f"Created new session: {session_id}")

    live_request_queue = LiveRequestQueue()

    # ========================================
    # Phase 3: Active Session (concurrent bidirectional communication)
    # ========================================

    async def upstream_task() -> None:
        """Receives messages from WebSocket and sends to LiveRequestQueue."""
        logger.debug("upstream_task started")
        while True:
            message = await websocket.receive()

            # Handle binary frames (audio data)
            if "bytes" in message:
                audio_data = message["bytes"]
                logger.debug(f"Received binary audio chunk: {len(audio_data)} bytes")
                audio_blob = types.Blob(
                    mime_type="audio/pcm;rate=16000", data=audio_data
                )
                live_request_queue.send_realtime(audio_blob)

            # Handle text frames (JSON messages)
            elif "text" in message:
                text_data = message["text"]
                logger.debug(f"Received text message: {text_data[:100]}...")

                json_message = json.loads(text_data)

                # Extract text from JSON and send to LiveRequestQueue
                if json_message.get("type") == "text":
                    logger.debug(f"Sending text content: {json_message['text']}")
                    content = types.Content(
                        parts=[types.Part(text=json_message["text"])]
                    )
                    live_request_queue.send_content(content)

                # Handle image data
                elif json_message.get("type") == "image":
                    logger.debug("Received image data")
                    image_data = base64.b64decode(json_message["data"])
                    mime_type = json_message.get("mimeType", "image/jpeg")
                    logger.debug(
                        f"Sending image: {len(image_data)} bytes, type: {mime_type}"
                    )
                    image_blob = types.Blob(mime_type=mime_type, data=image_data)
                    live_request_queue.send_realtime(image_blob)

    async def downstream_task() -> None:
        """Receives Events from run_live() and sends to WebSocket."""
        logger.debug("downstream_task started, calling runner.run_live()")
        async for event in runner.run_live(
            user_id=user_id,
            session_id=session_id,
            live_request_queue=live_request_queue,
            run_config=run_config,
        ):
            event_json = event.model_dump_json(exclude_none=True, by_alias=True)
            logger.debug(f"[SERVER] Event: {event_json[:200]}")
            await websocket.send_text(event_json)
        logger.debug("run_live() generator completed")

    # Run both tasks concurrently
    try:
        logger.debug("Starting asyncio.gather for upstream and downstream tasks")
        await asyncio.gather(upstream_task(), downstream_task())
        logger.debug("asyncio.gather completed normally")
    except WebSocketDisconnect:
        logger.info("Client disconnected normally")
    except Exception as e:
        logger.error(f"Unexpected error in streaming tasks: {e}", exc_info=True)
    finally:
        # ========================================
        # Phase 4: Session Termination
        # ========================================
        logger.info("Closing live_request_queue")
        live_request_queue.close()


# ========================================
# Run with Uvicorn
# ========================================
if __name__ == "__main__":
    import os
    import uvicorn

    port = int(os.getenv("PORT", 8080))
    print("="*60)
    print("  InterviewAce - AI Interview Coach")
    print("  Built with Google ADK & Gemini Live API")
    print("="*60)
    print(f"  Agent: {root_agent.name}")
    print(f"  Model: {root_agent.model}")
    print("=" * 60)

    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=port,
        reload=True,
        log_level="info",
    )
