"""Runtime configuration helpers for local and Cloud Run execution."""

from __future__ import annotations

import os
from dataclasses import dataclass


def _is_truthy(value: str | None) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


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


def get_default_agent_model() -> str:
    """Returns a safe default model for the current runtime."""

    explicit_model = os.getenv("AGENT_MODEL")
    if explicit_model:
        return explicit_model

    if _is_truthy(os.getenv("GOOGLE_GENAI_USE_VERTEXAI")):
        return "gemini-live-2.5-flash-native-audio"

    return "gemini-2.5-flash-native-audio-preview-12-2025"


def get_model_profile(model_name: str | None = None) -> ModelProfile:
    """Maps a model name to the output modality expected by the app."""

    resolved_name = model_name or get_default_agent_model()
    normalized = resolved_name.lower()

    if any(marker in normalized for marker in _NATIVE_AUDIO_MARKERS):
        return ModelProfile(
            name=resolved_name,
            supports_audio_output=True,
            mode="native_audio",
        )

    if any(marker in normalized for marker in _TEXT_OUTPUT_MARKERS):
        return ModelProfile(
            name=resolved_name,
            supports_audio_output=False,
            mode="text",
        )

    return ModelProfile(
        name=resolved_name,
        supports_audio_output="native-audio" in normalized,
        mode="native_audio" if "native-audio" in normalized else "text",
    )
