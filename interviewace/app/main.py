"""InterviewAce FastAPI application and Gemini Live WebSocket bridge."""

from __future__ import annotations

import asyncio
import base64
import hmac
import json
import logging
import os
import secrets
import time
import warnings
from collections import defaultdict, deque
from contextlib import asynccontextmanager
from hashlib import sha256
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

# Load from project root first, then app/.env as fallback
load_dotenv(Path(__file__).parent.parent / ".env", override=True)
load_dotenv(Path(__file__).parent / ".env", override=False)

from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect  # noqa: E402
from fastapi.responses import FileResponse, JSONResponse  # noqa: E402
from fastapi.staticfiles import StaticFiles  # noqa: E402
from google.adk.agents.live_request_queue import LiveRequestQueue  # noqa: E402
from google.adk.agents.run_config import RunConfig, StreamingMode  # noqa: E402
from google.adk.runners import Runner  # noqa: E402
from google.adk.sessions import InMemorySessionService  # noqa: E402
from google.genai import types  # noqa: E402

try:  # noqa: E402
    from .interview_coach_agent.agent import root_agent
    from .interview_coach_agent.tools import (
        build_session_dashboard,
        build_session_history,
        build_session_report,
        record_candidate_speech,
        seed_session_context,
    )
    from .runtime_config import (
        debug_endpoint_enabled,
        get_limits,
        get_model_profile,
        get_session_secret,
        normalize_company,
        normalize_difficulty,
        normalize_role,
        normalize_voice,
    )
    from .ws_manager import active_session_count, is_registered, register_ws, unregister_ws
except ImportError:  # pragma: no cover - supports running from app/ directly
    from interview_coach_agent.agent import root_agent  # type: ignore
    from interview_coach_agent.tools import (  # type: ignore
        build_session_dashboard,
        build_session_history,
        build_session_report,
        record_candidate_speech,
        seed_session_context,
    )
    from runtime_config import (  # type: ignore
        debug_endpoint_enabled,
        get_limits,
        get_model_profile,
        get_session_secret,
        normalize_company,
        normalize_difficulty,
        normalize_role,
        normalize_voice,
    )
    from ws_manager import (  # type: ignore
        active_session_count,
        is_registered,
        register_ws,
        unregister_ws,
    )


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

warnings.filterwarnings("ignore", category=UserWarning, module="pydantic")

APP_NAME = "interviewace"
MODEL_PROFILE = get_model_profile(root_agent.model)
LIMITS = get_limits()
SESSION_SECRET = get_session_secret()
TOKEN_GRACE_SECONDS = 300

static_dir = Path(__file__).parent / "static"

# Google Fonts is the only external origin the page needs. Scripts are same-origin only,
# so an injected string can never execute even if it reaches the DOM.
CONTENT_SECURITY_POLICY = "; ".join(
    [
        "default-src 'self'",
        "script-src 'self'",
        "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com",
        "font-src 'self' https://fonts.gstatic.com",
        "img-src 'self' data: blob:",
        "media-src 'self' blob:",
        "connect-src 'self' ws: wss:",
        "object-src 'none'",
        "base-uri 'self'",
        "form-action 'self'",
        "frame-ancestors 'none'",
    ]
)

# --------------------------------------------------------------------------------------
# Abuse guardrails
# --------------------------------------------------------------------------------------
# This service runs unauthenticated, so an open WebSocket is an open tap on the API key's
# quota. Defaults are sized for the Gemini free tier, where over-admitting sessions makes
# all of them fail with a 429 rather than serving more people. On a key with billing
# attached these become cost controls, and a budget alert should back them up.

_session_starts_by_ip: dict[str, deque[float]] = defaultdict(deque)
_active_sessions_by_ip: dict[str, set[str]] = defaultdict(set)

# session_id -> when the opening prompt was sent. Kept so a reconnect does not restart
# the interview with a second greeting, and pruned so it cannot grow without bound.
_intro_sent: dict[str, float] = {}

_RATE_WINDOW_SECONDS = 3600


def _prune_guardrail_state() -> None:
    """Drops per-IP and per-session bookkeeping that can no longer affect a decision.

    Without this, every distinct client address and every session id ever seen would be
    retained for the lifetime of the process.
    """

    now = time.monotonic()

    for ip in list(_session_starts_by_ip):
        window = _session_starts_by_ip[ip]
        while window and now - window[0] > _RATE_WINDOW_SECONDS:
            window.popleft()
        if not window and not _active_sessions_by_ip.get(ip):
            _session_starts_by_ip.pop(ip, None)
            _active_sessions_by_ip.pop(ip, None)

    intro_ttl = LIMITS.max_session_seconds * 2
    for session_id in [key for key, sent in _intro_sent.items() if now - sent > intro_ttl]:
        _intro_sent.pop(session_id, None)


def _client_ip(request_or_ws) -> str:
    forwarded = request_or_ws.headers.get("x-forwarded-for", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    client = getattr(request_or_ws, "client", None)
    return getattr(client, "host", None) or "unknown"


def _mint_session_token(session_id: str) -> str:
    issued_at = str(int(time.time()))
    signature = hmac.new(
        SESSION_SECRET, f"{session_id}:{issued_at}".encode(), sha256
    ).hexdigest()
    return f"{issued_at}.{signature}"


def _verify_session_token(session_id: str, token: str | None) -> bool:
    if not token or "." not in token:
        return False
    issued_at, _, signature = token.partition(".")
    if not issued_at.isdigit():
        return False

    age = time.time() - int(issued_at)
    if age < -TOKEN_GRACE_SECONDS or age > LIMITS.max_session_seconds + TOKEN_GRACE_SECONDS:
        return False

    expected = hmac.new(
        SESSION_SECRET, f"{session_id}:{issued_at}".encode(), sha256
    ).hexdigest()
    return hmac.compare_digest(expected, signature)


def classify_live_error(error_text: str) -> str:
    """Buckets a Live API failure so the client knows whether retrying can help.

    Quota exhaustion is the normal failure mode on the free tier, and it must be
    distinguished from a transient drop: reconnecting into an exhausted quota just
    produces another rejection and hides the real reason from the candidate.
    """

    lowered = error_text.lower()

    if any(
        marker in lowered
        for marker in ("resource_exhausted", "429", "quota", "rate limit", "rate-limit")
    ):
        return "quota"
    if any(
        marker in lowered
        for marker in ("api key", "api_key", "permission_denied", "unauthenticated", "401", "403")
    ):
        return "auth"
    if "1007" in lowered or "1008" in lowered:
        return "protocol"
    return "transient"


def _rate_limit_new_session(ip: str) -> str | None:
    """Returns a rejection reason, or None when the request may proceed."""

    _prune_guardrail_state()

    now = time.monotonic()
    window = _session_starts_by_ip[ip]

    if len(window) >= LIMITS.new_sessions_per_ip_per_hour:
        return "Too many sessions started from this address. Try again later."
    if len(_active_sessions_by_ip[ip]) >= LIMITS.max_sessions_per_ip:
        return "Too many concurrent sessions from this address."
    if active_session_count() >= LIMITS.max_concurrent_sessions:
        return "The coach is at capacity right now. Please try again in a few minutes."

    window.append(now)
    return None


@asynccontextmanager
async def lifespan(_app: FastAPI):
    logger.info(
        "InterviewAce starting: model=%s mode=%s audio_output=%s",
        MODEL_PROFILE.name,
        MODEL_PROFILE.mode,
        MODEL_PROFILE.supports_audio_output,
    )
    if not os.getenv("GOOGLE_API_KEY") and not os.getenv("GOOGLE_GENAI_USE_VERTEXAI"):
        logger.error(
            "Neither GOOGLE_API_KEY nor GOOGLE_GENAI_USE_VERTEXAI is set. "
            "Live sessions will fail to connect."
        )
    yield


app = FastAPI(title="InterviewAce", version="2.0.0", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=static_dir), name="static")

session_service = InMemorySessionService()
runner = Runner(app_name=APP_NAME, agent=root_agent, session_service=session_service)


@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["Content-Security-Policy"] = CONTENT_SECURITY_POLICY
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Permissions-Policy"] = "camera=(self), microphone=(self), geolocation=()"
    if request.url.scheme == "https":
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    return response


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


# --------------------------------------------------------------------------------------
# HTTP surface
# --------------------------------------------------------------------------------------


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
        "active_sessions": active_session_count(),
    }


@app.get("/debug")
async def debug():
    """Runtime diagnostics. Disabled unless ENABLE_DEBUG_ENDPOINT is set.

    This never returns any part of the API key: a prefix plus a length is enough to
    meaningfully narrow a brute-force search against a key that is otherwise secret.
    """

    if not debug_endpoint_enabled():
        raise HTTPException(status_code=404, detail="Not found")

    return {
        "api_key_configured": bool(os.getenv("GOOGLE_API_KEY")),
        "agent": root_agent.name,
        "model": MODEL_PROFILE.name,
        "mode": MODEL_PROFILE.mode,
        "audio_output": MODEL_PROFILE.supports_audio_output,
        "tools_count": len(root_agent.tools) if root_agent.tools else 0,
        "vertexai": os.getenv("GOOGLE_GENAI_USE_VERTEXAI", "not_set"),
        "active_sessions": active_session_count(),
        "limits": {
            "max_concurrent_sessions": LIMITS.max_concurrent_sessions,
            "max_sessions_per_ip": LIMITS.max_sessions_per_ip,
            "max_session_seconds": LIMITS.max_session_seconds,
        },
    }


@app.get("/favicon.ico", include_in_schema=False)
async def favicon():
    """Serves the favicon without generating a noisy 404."""

    icon_path = static_dir / "favicon.ico"
    if icon_path.exists():
        return FileResponse(icon_path, media_type="image/x-icon")
    return JSONResponse({"detail": "No favicon"}, status_code=404)


@app.post("/api/session")
async def create_session_ticket(request: Request):
    """Mints a server-side session id and a signed token for it.

    Session ids are generated here rather than in the browser so they cannot be guessed
    or chosen, and every later read of that session's analytics must present the
    matching signature.
    """

    ip = _client_ip(request)
    rejection = _rate_limit_new_session(ip)
    if rejection:
        raise HTTPException(status_code=429, detail=rejection)

    session_id = secrets.token_urlsafe(24)
    return {
        "session_id": session_id,
        "token": _mint_session_token(session_id),
        "max_session_seconds": LIMITS.max_session_seconds,
    }


def _require_token(session_id: str, token: str | None) -> None:
    if not _verify_session_token(session_id, token):
        raise HTTPException(status_code=403, detail="Invalid or expired session token")


@app.get("/api/sessions/{session_id}/analytics")
async def session_analytics(session_id: str, token: str | None = None):
    """Live analytics snapshot for the owning client."""

    _require_token(session_id, token)
    return build_session_dashboard(session_id)


@app.get("/api/sessions/{session_id}/history")
async def session_history(session_id: str, token: str | None = None):
    """Full backend history payload for the owning client."""

    _require_token(session_id, token)
    return build_session_history(session_id)


@app.post("/api/sessions/{session_id}/report")
async def session_report(session_id: str, token: str | None = None):
    """Generates the end-of-interview report deterministically.

    Ending an interview must not depend on the model deciding to call a tool in time, so
    the report is computed here from recorded state and returned directly.
    """

    _require_token(session_id, token)
    return build_session_report(session_id)


# --------------------------------------------------------------------------------------
# WebSocket bridge
# --------------------------------------------------------------------------------------


@app.websocket("/ws/{session_id}")
async def websocket_endpoint(
    websocket: WebSocket,
    session_id: str,
    token: str | None = None,
    voice: str = "Kore",
    role: str = "general",
    company: str = "general",
    difficulty: str = "medium",
) -> None:
    """Handles bidirectional Gemini Live streaming over WebSockets."""

    if not _verify_session_token(session_id, token):
        await websocket.close(code=1008, reason="Invalid or expired session token")
        return

    if is_registered(session_id):
        # A previous socket for this session is still live. Refusing here keeps one
        # session bound to exactly one Live API stream; the client retries after the
        # old socket finishes tearing down.
        await websocket.close(code=1013, reason="Session already active")
        return

    ip = _client_ip(websocket)
    if active_session_count() >= LIMITS.max_concurrent_sessions:
        await websocket.close(code=1013, reason="Server at capacity")
        return

    voice = normalize_voice(voice)
    role = normalize_role(role)
    company = normalize_company(company)
    difficulty = normalize_difficulty(difficulty)

    # user_id is derived, never client-supplied, so one client cannot address another's
    # ADK session namespace.
    user_id = f"u_{sha256(session_id.encode()).hexdigest()[:16]}"

    logger.info(
        "WebSocket open: session=%s role=%s company=%s difficulty=%s voice=%s model=%s",
        session_id,
        role,
        company,
        difficulty,
        voice,
        MODEL_PROFILE.name,
    )

    await websocket.accept()
    register_ws(session_id, websocket)
    _active_sessions_by_ip[ip].add(session_id)

    live_request_queue = LiveRequestQueue()
    run_config = build_run_config(voice)
    started_at = time.monotonic()

    # Coordination for the silence nudge: reset whenever the candidate speaks so we
    # prompt at most once per silence.
    last_candidate_speech = time.monotonic()
    nudge_pending = False
    interview_active = True

    seed_session_context(
        session_id,
        role=role,
        company_style=company,
        difficulty=difficulty,
    )

    session = await session_service.get_session(
        app_name=APP_NAME, user_id=user_id, session_id=session_id
    )
    if not session:
        await session_service.create_session(
            app_name=APP_NAME,
            user_id=user_id,
            session_id=session_id,
            # Tools read session_id from here instead of taking it as a model argument.
            state={
                "session_id": session_id,
                "role": role,
                "company_style": company,
                "difficulty": difficulty,
            },
        )

    def send_intro_once() -> None:
        """Kicks off the interview exactly once per session.

        The queue buffers until the Live connection is up, so there is nothing to wait
        for. Sending this on every reconnect would make Coach Ace greet the candidate
        again mid-interview.
        """

        if session_id in _intro_sent:
            return
        _intro_sent[session_id] = time.monotonic()
        company_label = company if company != "general" else "general tech"
        role_label = role.replace("_", " ")
        intro = (
            "Hello, I have joined the interview. "
            f"I want a {difficulty} {company_label} interview for a {role_label} role."
        )
        live_request_queue.send_content(
            types.Content(parts=[types.Part(text=intro)])
        )

    async def upstream_task() -> None:
        nonlocal last_candidate_speech, nudge_pending
        while True:
            message = await websocket.receive()
            if message.get("type") == "websocket.disconnect":
                raise WebSocketDisconnect(message.get("code", 1000))

            if message.get("bytes"):
                live_request_queue.send_realtime(
                    types.Blob(mime_type="audio/pcm;rate=16000", data=message["bytes"])
                )
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
                text = str(payload.get("text", ""))[:4000]
                if not text.strip():
                    continue
                last_candidate_speech = time.monotonic()
                nudge_pending = False
                live_request_queue.send_content(
                    types.Content(parts=[types.Part(text=text)])
                )
                continue

            if payload_type == "image":
                try:
                    image_data = base64.b64decode(payload["data"], validate=True)
                except Exception:
                    logger.warning("Ignoring malformed image payload for session %s", session_id)
                    continue
                mime = payload.get("mimeType", "image/jpeg")
                if mime not in {"image/jpeg", "image/png", "image/webp"}:
                    continue
                live_request_queue.send_realtime(types.Blob(mime_type=mime, data=image_data))
                continue

            logger.debug("Ignoring unsupported payload type %s", payload_type)

    async def downstream_task() -> None:
        nonlocal last_candidate_speech, nudge_pending
        try:
            async for event in runner.run_live(
                user_id=user_id,
                session_id=session_id,
                live_request_queue=live_request_queue,
                run_config=run_config,
            ):
                # Capture the real transcript of the candidate's speech. This is what
                # filler-word detection is measured from, rather than the model's
                # paraphrase of what it thinks it heard.
                transcription = getattr(event, "input_transcription", None)
                text = getattr(transcription, "text", None) if transcription else None
                if text and text.strip():
                    record_candidate_speech(session_id, text)
                    last_candidate_speech = time.monotonic()
                    nudge_pending = False

                try:
                    await websocket.send_text(
                        event.model_dump_json(exclude_none=True, by_alias=True)
                    )
                except Exception:
                    break
        except asyncio.CancelledError:
            raise
        except Exception as api_err:
            err_str = str(api_err)
            category = classify_live_error(err_str)
            logger.warning(
                "Live API error for session %s (%s): %s", session_id, category, err_str
            )
            messages = {
                "quota": (
                    "The Gemini free-tier quota is exhausted right now. "
                    "Your scores so far are saved — wait a minute and start a new session."
                ),
                "auth": "The API key was rejected. Check GOOGLE_API_KEY on the server.",
                "protocol": "The audio stream was rejected. Reconnecting.",
                "transient": "The connection to the AI was interrupted. Reconnecting.",
            }
            try:
                await websocket.send_text(
                    json.dumps(
                        {
                            "type": "server_error",
                            "category": category,
                            "message": messages[category],
                            "error": err_str[:500],
                            # Retrying only helps for a genuinely transient drop.
                            "recoverable": category in {"transient", "protocol"},
                        }
                    )
                )
            except Exception:
                pass

    async def supervisor_task() -> None:
        """Enforces the session time cap and issues the silence nudge.

        The model cannot perceive elapsed silence, so the prompt tells it not to guess
        and this loop supplies the signal instead.
        """

        nonlocal nudge_pending, interview_active
        while interview_active:
            await asyncio.sleep(2)

            if time.monotonic() - started_at > LIMITS.max_session_seconds:
                logger.info("Session %s hit the duration cap", session_id)
                try:
                    await websocket.send_text(
                        json.dumps({"type": "session_expired", "reason": "time_limit"})
                    )
                except Exception:
                    pass
                interview_active = False
                return

            silence = time.monotonic() - last_candidate_speech
            if silence > LIMITS.silence_nudge_seconds and not nudge_pending:
                nudge_pending = True
                live_request_queue.send_content(
                    types.Content(
                        parts=[
                            types.Part(
                                text=(
                                    "[system] The candidate has been silent for a while. "
                                    "Offer one short, warm nudge such as "
                                    "'Take your time, whenever you're ready', then wait."
                                )
                            )
                        ]
                    )
                )

    send_intro_once()

    upstream = asyncio.create_task(upstream_task(), name=f"upstream-{session_id}")
    downstream = asyncio.create_task(downstream_task(), name=f"downstream-{session_id}")
    supervisor = asyncio.create_task(supervisor_task(), name=f"supervisor-{session_id}")

    try:
        await websocket.send_text(json.dumps({"type": "live_ready"}))

        done, _pending = await asyncio.wait(
            {upstream, downstream, supervisor},
            return_when=asyncio.FIRST_COMPLETED,
        )
        for task in done:
            exc = task.exception()
            if exc and not isinstance(exc, WebSocketDisconnect):
                logger.warning("Task error for session %s: %s", session_id, exc)
    except WebSocketDisconnect:
        logger.info("WebSocket disconnected for session %s", session_id)
    except Exception as exc:
        logger.exception("Streaming error for session %s: %s", session_id, exc)
    finally:
        interview_active = False
        for task in (upstream, downstream, supervisor):
            if not task.done():
                task.cancel()
        await asyncio.gather(upstream, downstream, supervisor, return_exceptions=True)

        live_request_queue.close()
        unregister_ws(session_id, websocket)
        _active_sessions_by_ip[ip].discard(session_id)
        if not _active_sessions_by_ip[ip]:
            _active_sessions_by_ip.pop(ip, None)
        logger.info("Session %s closed after %.0fs", session_id, time.monotonic() - started_at)


if __name__ == "__main__":
    import uvicorn

    port = int(os.getenv("PORT", "8080"))
    is_cloud = bool(os.getenv("K_SERVICE") or os.getenv("CLOUD_RUN", ""))

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
        reload=not is_cloud,
        log_level="info",
        ws_max_size=16 * 1024 * 1024,
        timeout_keep_alive=300,
    )
