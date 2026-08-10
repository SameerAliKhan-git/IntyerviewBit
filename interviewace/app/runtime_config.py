"""Runtime configuration helpers for local and Cloud Run execution."""

from __future__ import annotations

import logging
import os
import secrets
from dataclasses import dataclass

logger = logging.getLogger(__name__)


def is_truthy(value: str | None) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, "").strip() or default)
    except ValueError:
        logger.warning("Invalid integer for %s; falling back to %s", name, default)
        return default


@dataclass(frozen=True)
class ModelProfile:
    """Describes how a Live API model should be configured."""

    name: str
    supports_audio_output: bool
    mode: str


_NATIVE_AUDIO_MARKERS = (
    "native-audio",
    "gemini-live-2.5-flash-native-audio",
)

_TEXT_OUTPUT_MARKERS = (
    "gemini-2.0-flash-exp",
    "gemini-2.0-flash-live-001",
    "gemini-live-2.5-flash-preview",
)

# Prebuilt Live API voices this app exposes. Anything else is rejected rather than
# forwarded, because an unknown voice name makes the Live API close the socket with a
# 1007 that surfaces to the user as an unexplained reconnect loop.
ALLOWED_VOICES = ("Kore", "Aoede", "Fenrir", "Puck", "Charon", "Leda")
DEFAULT_VOICE = "Kore"

ALLOWED_ROLES = ("software_engineer", "product_manager", "data_scientist", "general")
ALLOWED_COMPANIES = ("general", "google", "amazon", "meta", "apple", "microsoft", "netflix")
ALLOWED_DIFFICULTIES = ("easy", "medium", "hard")


def normalize_voice(voice: str | None) -> str:
    return voice if voice in ALLOWED_VOICES else DEFAULT_VOICE


def normalize_role(role: str | None) -> str:
    return role if role in ALLOWED_ROLES else "general"


def normalize_company(company: str | None) -> str:
    return company if company in ALLOWED_COMPANIES else "general"


def normalize_difficulty(difficulty: str | None) -> str:
    return difficulty if difficulty in ALLOWED_DIFFICULTIES else "medium"


def get_default_agent_model() -> str:
    """Returns a safe default model for the current runtime."""

    explicit_model = os.getenv("AGENT_MODEL")
    if explicit_model:
        return explicit_model

    if is_truthy(os.getenv("GOOGLE_GENAI_USE_VERTEXAI")):
        return "gemini-live-2.5-flash-native-audio"

    return "gemini-2.5-flash-native-audio-preview-12-2025"


def get_search_model() -> str:
    """Model used by the grounding sub-agent.

    This runs as a plain request/response lookup, not over the Live API, so it uses a
    standard text model rather than the native-audio one.
    """

    return os.getenv("SEARCH_MODEL", "gemini-2.5-flash")


def get_model_profile(model_name: str | None = None) -> ModelProfile:
    """Maps a model name to the output modality expected by the app."""

    resolved_name = model_name or get_default_agent_model()
    normalized = resolved_name.lower()

    if any(marker in normalized for marker in _NATIVE_AUDIO_MARKERS):
        return ModelProfile(name=resolved_name, supports_audio_output=True, mode="native_audio")

    if any(marker in normalized for marker in _TEXT_OUTPUT_MARKERS):
        return ModelProfile(name=resolved_name, supports_audio_output=False, mode="text")

    return ModelProfile(
        name=resolved_name,
        supports_audio_output="native-audio" in normalized,
        mode="native_audio" if "native-audio" in normalized else "text",
    )


def get_session_secret() -> bytes:
    """Secret used to sign session tokens.

    Set SESSION_SECRET in any deployment running more than one instance, otherwise each
    instance signs with its own ephemeral key and tokens will not validate across them.
    """

    configured = os.getenv("SESSION_SECRET", "").strip()
    if configured:
        return configured.encode("utf-8")
    logger.warning(
        "SESSION_SECRET is not set; generating an ephemeral per-instance secret. "
        "Session tokens will not validate across instances or restarts."
    )
    return secrets.token_bytes(32)


@dataclass(frozen=True)
class Limits:
    """Abuse and cost guardrails for a publicly reachable deployment."""

    max_concurrent_sessions: int
    max_sessions_per_ip: int
    max_session_seconds: int
    new_sessions_per_ip_per_hour: int
    silence_nudge_seconds: int


def get_limits() -> Limits:
    """Defaults are tuned for the Gemini API free tier.

    Free-tier Live API concurrency is small. Admitting more sessions than the quota
    allows does not serve more people; it makes every one of them fail mid-interview
    with a 429. Refusing the extra session up front at least gives a clear message.
    Raise these once the project runs against a paid quota.
    """

    return Limits(
        max_concurrent_sessions=env_int("MAX_CONCURRENT_SESSIONS", 2),
        max_sessions_per_ip=env_int("MAX_SESSIONS_PER_IP", 1),
        max_session_seconds=env_int("MAX_SESSION_SECONDS", 10 * 60),
        new_sessions_per_ip_per_hour=env_int("NEW_SESSIONS_PER_IP_PER_HOUR", 10),
        silence_nudge_seconds=env_int("SILENCE_NUDGE_SECONDS", 12),
    )


def debug_endpoint_enabled() -> bool:
    return is_truthy(os.getenv("ENABLE_DEBUG_ENDPOINT"))


def search_grounding_enabled() -> bool:
    return is_truthy(os.getenv("ENABLE_SEARCH_GROUNDING", "true"))
