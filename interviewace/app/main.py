"""InterviewAce FastAPI application and Gemini Live WebSocket bridge."""

from __future__ import annotations

import asyncio
import base64
import json
import logging
import os
import warnings
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

# Load from project root first, then app/.env as fallback
load_dotenv(Path(__file__).parent.parent / ".env", override=True)
load_dotenv(Path(__file__).parent / ".env", override=False)

from fastapi import FastAPI, WebSocket, WebSocketDisconnect  # noqa: E402
from fastapi.responses import FileResponse  # noqa: E402
from fastapi.staticfiles import StaticFiles  # noqa: E402
from google.adk.agents.live_request_queue import LiveRequestQueue  # noqa: E402
from google.adk.agents.run_config import RunConfig, StreamingMode  # noqa: E402
from google.adk.runners import Runner  # noqa: E402
from google.adk.sessions import InMemorySessionService  # noqa: E402
from google.genai import types  # noqa: E402

try:  # noqa: E402
    from .interview_coach_agent.agent import root_agent
    from .interview_coach_agent.tools import get_session_dashboard, get_session_history
    from .runtime_config import get_model_profile
    from .ws_manager import register_ws, unregister_ws
except ImportError:  # pragma: no cover - supports running from app/ directly
    from interview_coach_agent.agent import root_agent  # type: ignore
    from interview_coach_agent.tools import get_session_dashboard, get_session_history  # type: ignore
    from runtime_config import get_model_profile  # type: ignore
    from ws_manager import register_ws, unregister_ws  # type: ignore


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

warnings.filterwarnings("ignore", category=UserWarning, module="pydantic")

APP_NAME = "interviewace"
MODEL_PROFILE = get_model_profile(root_agent.model)

app = FastAPI(title="InterviewAce", version="1.1.0")
static_dir = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=static_dir), name="static")

session_service = InMemorySessionService()
runner = Runner(app_name=APP_NAME, agent=root_agent, session_service=session_service)


def build_run_config(voice: str) -> RunConfig:
    """Builds a model-aware ADK run configuration."""

    common_args: dict[str, Any] = {
        "streaming_mode": StreamingMode.BIDI,
        "session_resumption": types.SessionResumptionConfig(),
    }

    if MODEL_PROFILE.supports_audio_output:
        return RunConfig(
            response_modalities=["AUDIO"],
            input_audio_transcription=types.AudioTranscriptionConfig(),
            output_audio_transcription=types.AudioTranscriptionConfig(),
            speech_config=types.SpeechConfig(
                voice_config=types.VoiceConfig(
                    prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name=voice)
                )
            ),
            **common_args,
        )

    return RunConfig(
        response_modalities=["TEXT"],
        input_audio_transcription=types.AudioTranscriptionConfig(),
        output_audio_transcription=None,
        **common_args,
    )


@app.get("/")
async def root():
    """Serves the main web app."""

    return FileResponse(static_dir / "index.html")


@app.get("/health")
async def health():
    """Cloud Run health check endpoint."""

    return {
        "status": "healthy",
        "agent": root_agent.name,
        "model": MODEL_PROFILE.name,
        "mode": MODEL_PROFILE.mode,
        "audio_output": MODEL_PROFILE.supports_audio_output,
    }


@app.get("/debug")
async def debug():
    """Returns runtime diagnostics helpful during hackathon demos."""

    api_key = os.getenv("GOOGLE_API_KEY", "")
    return {
        "api_key_set": bool(api_key),
        "api_key_length": len(api_key),
        "api_key_prefix": api_key[:8] + "..." if len(api_key) > 8 else "MISSING",
        "agent": root_agent.name,
        "model": MODEL_PROFILE.name,
        "mode": MODEL_PROFILE.mode,
        "audio_output": MODEL_PROFILE.supports_audio_output,
        "tools_count": len(root_agent.tools) if root_agent.tools else 0,
        "vertexai": os.getenv("GOOGLE_GENAI_USE_VERTEXAI", "not_set"),
        "active_sessions": len(getattr(session_service, "_sessions", {})),
    }


@app.get("/favicon.ico", include_in_schema=False)
async def favicon():
    """Serves the favicon without generating a noisy 404."""

    icon_path = static_dir / "favicon.ico"
    if icon_path.exists():
        return FileResponse(icon_path, media_type="image/x-icon")
    return FileResponse(static_dir / "index.html")


@app.get("/api/sessions/{session_id}/analytics")
async def session_analytics(session_id: str):
    """Exposes the live analytics snapshot for the frontend and tests."""

    return get_session_dashboard(session_id)


@app.get("/api/sessions/{session_id}/history")
async def session_history(session_id: str):
    """Returns the full backend history payload for a session."""

    return get_session_history(session_id)


@app.websocket("/ws/{user_id}/{session_id}")
async def websocket_endpoint(
    websocket: WebSocket,
    user_id: str,
    session_id: str,
    voice: str = "Kore",
    role: str = "general",
    company: str = "general",
    difficulty: str = "medium",
) -> None:
    """Handles bidirectional Gemini Live streaming over WebSockets."""

    logger.info(
        "WebSocket connection: user=%s session=%s voice=%s model=%s",
        user_id,
        session_id,
        voice,
        MODEL_PROFILE.name,
    )

    live_request_queue = LiveRequestQueue()
    live_ready = asyncio.Event()
    await websocket.accept()
    register_ws(session_id, websocket)

    run_config = build_run_config(voice)
    session = await session_service.get_session(
        app_name=APP_NAME,
        user_id=user_id,
        session_id=session_id,
    )
    if not session:
        await session_service.create_session(
            app_name=APP_NAME,
            user_id=user_id,
            session_id=session_id,
        )

    async def upstream_task() -> None:
        while True:
            message = await websocket.receive()
            event_type = message.get("type")

            if event_type == "websocket.disconnect":
                raise WebSocketDisconnect(message.get("code", 1000))

            if message.get("bytes"):
                audio_blob = types.Blob(
                    mime_type="audio/pcm;rate=16000",
                    data=message["bytes"],
                )
                live_request_queue.send_realtime(audio_blob)
                continue

            text_data = message.get("text")
            if not text_data:
                continue

            try:
                payload = json.loads(text_data)
            except json.JSONDecodeError:
                logger.warning("Ignoring malformed JSON payload for session %s", session_id)
                continue

            payload_type = payload.get("type")
            if payload_type == "ping":
                await websocket.send_text(json.dumps({"type": "pong"}))
                continue

            if payload_type == "text":
                content = types.Content(parts=[types.Part(text=payload.get("text", ""))])
                live_request_queue.send_content(content)
                continue

            if payload_type == "image":
                try:
                    image_data = base64.b64decode(payload["data"])
                except Exception:
                    logger.warning("Ignoring malformed image payload for session %s", session_id)
                    continue
                image_blob = types.Blob(
                    mime_type=payload.get("mimeType", "image/jpeg"),
                    data=image_data,
                )
                live_request_queue.send_realtime(image_blob)
                continue

            logger.debug("Ignoring unsupported payload type %s", payload_type)

    async def downstream_task() -> None:
        first_event = True
        try:
            async for event in runner.run_live(
                user_id=user_id,
                session_id=session_id,
                live_request_queue=live_request_queue,
                run_config=run_config,
            ):
                if first_event:
                    first_event = False
                    live_ready.set()
                try:
                    await websocket.send_text(event.model_dump_json(exclude_none=True, by_alias=True))
                except Exception:
                    break
        except Exception as api_err:
            err_str = str(api_err)
            logger.warning("Live API error for session %s: %s", session_id, err_str)
            # Send a graceful error event to the frontend
            try:
                await websocket.send_text(json.dumps({
                    "type": "server_error",
                    "error": err_str,
                    "recoverable": "1007" not in err_str and "1008" not in err_str,
                }))
            except Exception:
                pass

    async def send_intro_when_ready() -> None:
        """Waits for the Live API to be connected, then sends the greeting."""
        # Give the Live connection up to 15 seconds to establish
        try:
            await asyncio.wait_for(live_ready.wait(), timeout=15.0)
        except asyncio.TimeoutError:
            pass
        # Small grace period after first event
        await asyncio.sleep(0.5)
        # Always send the intro prompt server-side so it never races
        company_label = company if company != "general" else "general tech"
        role_label = role.replace("_", " ")
        intro = (
            f"Hello, I have joined the interview. "
            f"I want a {difficulty} {company_label} interview for a {role_label} role."
        )
        logger.info("Sending server-side intro prompt for session %s", session_id)
        content = types.Content(parts=[types.Part(text=intro)])
        live_request_queue.send_content(content)
        # Signal the frontend that we are live
        try:
            await websocket.send_text(json.dumps({"type": "live_ready"}))
        except Exception:
            pass

    upstream = asyncio.create_task(upstream_task(), name=f"upstream-{session_id}")
    downstream = asyncio.create_task(downstream_task(), name=f"downstream-{session_id}")
    intro_task = asyncio.create_task(send_intro_when_ready(), name=f"intro-{session_id}")

    try:
        done, pending = await asyncio.wait(
            {upstream, downstream},
            return_when=asyncio.FIRST_COMPLETED,
        )

        for task in done:
            exc = task.exception()
            if exc and not isinstance(exc, WebSocketDisconnect):
                logger.warning("Task error (handled) for session %s: %s", session_id, exc)
    except WebSocketDisconnect:
        logger.info("WebSocket disconnected for session %s", session_id)
    except Exception as exc:
        logger.exception("Streaming error for session %s: %s", session_id, exc)
        try:
            await websocket.send_text(
                json.dumps({"type": "server_error", "error": str(exc)})
            )
        except Exception:
            pass
    finally:
        for task in (upstream, downstream, intro_task):
            if not task.done():
                task.cancel()
        unregister_ws(session_id)
        live_request_queue.close()


if __name__ == "__main__":
    import uvicorn

    port = int(os.getenv("PORT", 8080))
    is_cloud = os.getenv("K_SERVICE") or os.getenv("CLOUD_RUN", "")

    print("=" * 60)
    print("  InterviewAce - AI Interview Coach")
    print("  Built with Google ADK and Gemini Live API")
    print("=" * 60)
    print(f"  Agent: {root_agent.name}")
    print(f"  Model: {MODEL_PROFILE.name}")
    print(f"  Mode: {MODEL_PROFILE.mode}")
    print(f"  Environment: {'Cloud Run' if is_cloud else 'Local'}")
    print("=" * 60)

    uvicorn.run(
        "app.main:app" if is_cloud else "main:app",
        host="0.0.0.0",
        port=port,
        reload=not bool(is_cloud),
        log_level="info",
        ws_max_size=16 * 1024 * 1024,
        timeout_keep_alive=300,
    )
    # force reload to load new env vars 
