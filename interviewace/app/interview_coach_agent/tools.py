"""InterviewAce analytics and coaching tools.

Session binding
---------------
Every tool that touches session state receives its ``session_id`` from the ADK
``ToolContext`` (seeded server-side at connect time), never from a model-supplied
argument. A tool invoked without a resolvable session is a hard no-op that returns
an error payload; it must never fall back to "some other active session", because
that silently writes one candidate's analytics into another candidate's dashboard.
"""

from __future__ import annotations

import hashlib
import random
import re
import time
from collections import deque
from datetime import datetime, timezone
from statistics import mean
from typing import Any

try:  # pragma: no cover - only taken when google-adk is installed
    from google.adk.tools import ToolContext
except ImportError:  # pragma: no cover - unit tests run without the ADK installed

    class ToolContext:  # type: ignore[no-redef]
        """Minimal stand-in so annotations resolve when ADK is absent."""

        state: dict[str, Any]


try:
    from ..ws_manager import send_tool_result_sync
except ImportError:  # pragma: no cover - supports running from app/ directly
    try:
        from app.ws_manager import send_tool_result_sync
    except ImportError:  # pragma: no cover
        from ws_manager import send_tool_result_sync

from .grounding_data import GROUNDING_KNOWLEDGE, IMPROVEMENT_TIPS, INTERVIEW_QUESTIONS

# --------------------------------------------------------------------------------------
# Bounded in-process state
# --------------------------------------------------------------------------------------
# This process holds session analytics in memory. It is bounded on two axes so a long
# running Cloud Run instance cannot grow without limit: idle sessions expire after
# _SESSION_TTL_SECONDS, and the newest _MAX_SESSIONS are kept if that is still exceeded.

_SESSION_TTL_SECONDS = 60 * 60
_MAX_SESSIONS = 500
_MAX_ARCHIVED_REPORTS = 200
_MAX_TRANSCRIPT_CHARS = 20_000

_sessions: dict[str, dict[str, Any]] = {}
_recordings: dict[str, list[dict[str, Any]]] = {}
_archived_reports: deque[dict[str, Any]] = deque(maxlen=_MAX_ARCHIVED_REPORTS)

SESSION_UNAVAILABLE = {
    "status": "error",
    "error": "session_unavailable",
    "message": (
        "No interview session is bound to this call, so nothing was recorded. "
        "Continue the conversation normally."
    ),
}

_ROLE_DEFAULT_CATEGORY = {
    "software_engineer": "technical",
    "product_manager": "behavioral",
    "data_scientist": "technical",
    "general": "behavioral",
}

_ROLE_COACHING = {
    "software_engineer": [
        "Lead with scale, trade-offs, and measurable engineering impact.",
        "Make your individual actions explicit when discussing debugging, design, and delivery.",
        "Use metrics like latency, reliability, cost, or developer productivity in your results.",
    ],
    "product_manager": [
        "Show user empathy, prioritization logic, and how you aligned stakeholders.",
        "Quantify business impact with adoption, retention, conversion, or learning velocity.",
        "Be explicit about what decision you made and why it was the right trade-off.",
    ],
    "data_scientist": [
        "Explain your method simply, then connect it to a business or user outcome.",
        "Highlight experiment design, model quality, and how you influenced non-technical partners.",
        "Use precision, recall, lift, time saved, or revenue impact to quantify results.",
    ],
    "general": [
        "Use a clear STAR narrative with one main storyline per answer.",
        "Anchor every answer in ownership, collaboration, and measurable outcomes.",
        "Close each response with what changed because of your actions.",
    ],
}

_INDUSTRY_COACHING = {
    "consulting": [
        "Structure answers top-down and make your recommendation early.",
        "Show how you synthesized ambiguity into an actionable plan.",
    ],
    "finance": [
        "Demonstrate rigor, risk awareness, and precision in decision-making.",
        "Use numbers confidently and explain how you protected downside risk.",
    ],
    "healthcare": [
        "Show patient empathy, safety awareness, and collaboration across functions.",
        "Emphasize reliability, trust, and the consequences of poor execution.",
    ],
    "general": [
        "Tie your story to the role, team impact, and a measurable result.",
    ],
}

_COMPANY_HINTS = {
    "google": [
        "Show structured thinking, learning agility, and technical depth.",
        "Use first-principles reasoning and quantify your impact.",
    ],
    "amazon": [
        "Name the ownership trade-off you faced and the principle you demonstrated.",
        "Emphasize frugality, delivery, and data-backed judgment.",
    ],
    "meta": [
        "Speak to speed, iteration, and learning from imperfect decisions.",
        "Highlight how you moved quickly without losing the core user outcome.",
    ],
    "apple": [
        "Stress craft, quality bar, and attention to details that affect user trust.",
        "Balance innovation with reliability and cross-functional alignment.",
    ],
    "microsoft": [
        "Show a growth mindset and what you changed after a setback.",
        "Connect technical decisions to customer success and team collaboration.",
    ],
    "netflix": [
        "Demonstrate independent judgment and candour about trade-offs you owned.",
        "Show high impact per decision rather than volume of activity.",
    ],
    "general": [
        "Stay concise and practical, then back up your story with evidence.",
    ],
}

# Ordered longest-first so multi-word phrases are counted before their constituent words.
_FILLER_PATTERNS = [
    "you know",
    "i mean",
    "sort of",
    "kind of",
    "so yeah",
    "basically",
    "literally",
    "actually",
    "right",
    "like",
    "um",
    "uh",
]

_MILESTONES = {
    "first_answer": {"badge": "First Rep", "description": "Completed the first scored answer."},
    "steady_voice": {"badge": "Voice Control", "description": "Sustained an average voice score of 80+."},
    "star_storyteller": {"badge": "STAR Storyteller", "description": "Averaged 85+ on STAR structure."},
    "low_fillers": {"badge": "Clear Speaker", "description": "Kept filler usage under control across the session."},
    "engaged_presence": {"badge": "Locked In", "description": "Maintained 80+ engagement across the latest turns."},
    "confidence_gain": {"badge": "Momentum", "description": "Improved overall performance by 10+ points."},
}


# --------------------------------------------------------------------------------------
# Session plumbing
# --------------------------------------------------------------------------------------


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _clamp(value: float, minimum: int = 0, maximum: int = 100) -> int:
    return max(minimum, min(maximum, round(value)))


def _safe_mean(values: list[Any]) -> int:
    return round(mean(values)) if values else 0


def _trend_label(current: int, previous: int | None) -> str:
    if previous is None:
        return "first_answer"
    diff = current - previous
    if diff > 0:
        return f"improved_by_{diff}_points"
    if diff < 0:
        return f"decreased_by_{abs(diff)}_points"
    return "same_as_previous"


def _new_state() -> dict[str, Any]:
    return {
        "feedback": [],
        "fillers": [],
        "body": [],
        "voice": [],
        "star": [],
        "fusion": [],
        "emotion": [],
        "engagement": [],
        "reports": [],
        "context": {},
        "milestones": [],
        "asked_questions": [],
        "transcript": [],
        "pending_transcript": [],
        "last_touched": time.monotonic(),
    }


def _prune_sessions() -> None:
    """Drops idle sessions, then caps total retained sessions."""

    now = time.monotonic()
    expired = [
        key
        for key, state in _sessions.items()
        if now - state.get("last_touched", now) > _SESSION_TTL_SECONDS
    ]
    for key in expired:
        _sessions.pop(key, None)
        _recordings.pop(key, None)

    if len(_sessions) > _MAX_SESSIONS:
        ordered = sorted(_sessions.items(), key=lambda item: item[1].get("last_touched", 0.0))
        for key, _ in ordered[: len(_sessions) - _MAX_SESSIONS]:
            _sessions.pop(key, None)
            _recordings.pop(key, None)


def _session_id_from_context(tool_context: ToolContext | None) -> str | None:
    """Resolves the session this tool call belongs to, or None.

    Resolution is strictly scoped to the invoking context. There is deliberately no
    "pick an active session" fallback: mis-attributing analytics across concurrent
    candidates is worse than recording nothing.
    """

    if tool_context is None:
        return None

    state = getattr(tool_context, "state", None)
    if isinstance(state, dict) or hasattr(state, "get"):
        try:
            session_id = state.get("session_id")
        except Exception:  # pragma: no cover - defensive against exotic state objects
            session_id = None
        if isinstance(session_id, str) and session_id:
            return session_id

    invocation = getattr(tool_context, "_invocation_context", None)
    session = getattr(invocation, "session", None)
    session_id = getattr(session, "id", None)
    if isinstance(session_id, str) and session_id:
        return session_id

    return None


def _get_session_state(session_id: str) -> dict[str, Any]:
    _prune_sessions()
    state = _sessions.get(session_id)
    if state is None:
        state = _new_state()
        _sessions[session_id] = state
    state["last_touched"] = time.monotonic()
    return state


def _record_bucket(session_id: str, bucket: str) -> list[dict[str, Any]]:
    state = _get_session_state(session_id)
    state.setdefault(bucket, [])
    return state[bucket]


def seed_session_context(
    session_id: str,
    *,
    role: str = "general",
    company_style: str = "general",
    difficulty: str = "medium",
    industry: str = "general",
) -> None:
    """Records the interview parameters chosen by the candidate before the call starts.

    These come from the connection handshake, not from the model, so role/company/
    difficulty are always correct rather than whatever the model happened to infer.
    """

    context = _get_session_state(session_id)["context"]
    context["role"] = role or "general"
    context["company_style"] = company_style or "general"
    context["difficulty"] = difficulty or "medium"
    context["industry"] = industry or "general"


def record_candidate_speech(session_id: str, text: str) -> None:
    """Appends a real transcription chunk of the candidate's speech.

    Called by the WebSocket bridge with Gemini's ``input_transcription`` output. This is
    the ground truth used for filler-word detection, rather than the model's paraphrase
    of what it thinks the candidate said.
    """

    cleaned = (text or "").strip()
    if not cleaned:
        return
    state = _get_session_state(session_id)
    state["transcript"].append(cleaned)
    state["pending_transcript"].append(cleaned)

    # Keep the rolling transcript bounded for long sessions.
    while sum(len(chunk) for chunk in state["transcript"]) > _MAX_TRANSCRIPT_CHARS:
        state["transcript"].pop(0)


def take_pending_transcript(session_id: str) -> str:
    """Returns and clears the candidate speech captured since the last scored turn."""

    state = _get_session_state(session_id)
    pending = " ".join(state["pending_transcript"]).strip()
    state["pending_transcript"] = []
    return pending


def get_full_transcript(session_id: str) -> list[str]:
    return list(_get_session_state(session_id)["transcript"])


def clear_session(session_id: str) -> None:
    """Releases all state for a finished session."""

    _sessions.pop(session_id, None)
    _recordings.pop(session_id, None)


def _broadcast(session_id: str, tool_name: str, payload: dict[str, Any]) -> None:
    try:
        send_tool_result_sync(session_id, tool_name, payload)
    except Exception:  # pragma: no cover - UI transport is best effort
        pass


# --------------------------------------------------------------------------------------
# Derived analytics (pure functions over session state)
# --------------------------------------------------------------------------------------


def _heatmap(session_id: str) -> list[dict[str, Any]]:
    feedback = _get_session_state(session_id)["feedback"]
    heatmap: list[dict[str, Any]] = []
    for entry in feedback:
        area_scores = {
            "confidence": entry["confidence"],
            "clarity": entry["clarity"],
            "body_language": entry["body_language"],
            "content": entry["content"],
            "star_score": entry["star_score"],
        }
        weakest = min(area_scores, key=lambda key: area_scores[key])
        heatmap.append(
            {
                "question_number": entry["question_number"],
                "overall": entry["overall"],
                "focus_area": weakest,
                "focus_score": area_scores[weakest],
                "intensity": "high"
                if entry["overall"] >= 85
                else "medium"
                if entry["overall"] >= 70
                else "low",
            }
        )
    return heatmap


def _competency_radar(session_id: str) -> dict[str, int]:
    state = _get_session_state(session_id)
    feedback = state["feedback"]
    if not feedback:
        return {
            "confidence": 0,
            "clarity": 0,
            "body_language": 0,
            "content": 0,
            "star": 0,
            "voice": 0,
            "engagement": 0,
        }

    return {
        "confidence": _safe_mean([item["confidence"] for item in feedback]),
        "clarity": _safe_mean([item["clarity"] for item in feedback]),
        "body_language": _safe_mean([item["body_language"] for item in feedback]),
        "content": _safe_mean([item["content"] for item in feedback]),
        "star": _safe_mean([item["star_score"] for item in feedback]),
        "voice": _safe_mean([item["overall"] for item in state["voice"]]),
        "engagement": _safe_mean([item["engagement_score"] for item in state["engagement"]]),
    }


def _scored_radar(session_id: str) -> dict[str, int]:
    """Radar restricted to competencies that actually have observations.

    ``_competency_radar`` reports 0 for un-observed areas (voice/engagement before any
    such tool has fired). Ranking "weakest area" over those zeros always names an area
    the candidate was never measured on, so the report ranks only scored areas.
    """

    radar = _competency_radar(session_id)
    scored = {key: value for key, value in radar.items() if value > 0}
    return scored or radar


def _milestones_for(session_id: str) -> list[dict[str, str]]:
    state = _get_session_state(session_id)
    feedback = state["feedback"]
    voice = state["voice"]
    star = state["star"]
    engagement = state["engagement"]
    filler_total = sum(item["count"] for item in state["fillers"])
    awards = set(state["milestones"])

    if feedback:
        awards.add("first_answer")
    if voice and _safe_mean([item["overall"] for item in voice]) >= 80:
        awards.add("steady_voice")
    if star and _safe_mean([item["score"] for item in star]) >= 85:
        awards.add("star_storyteller")
    if feedback and state["fillers"] and filler_total <= max(2, len(feedback) * 2):
        awards.add("low_fillers")
    if len(engagement) >= 2 and _safe_mean([item["engagement_score"] for item in engagement[-2:]]) >= 80:
        awards.add("engaged_presence")
    if len(feedback) >= 2 and feedback[-1]["overall"] - feedback[0]["overall"] >= 10:
        awards.add("confidence_gain")

    state["milestones"] = sorted(awards)
    return [{"key": key, **_MILESTONES[key]} for key in state["milestones"] if key in _MILESTONES]


def _industry_specific_coaching(session_id: str) -> list[str]:
    context = _get_session_state(session_id)["context"]
    role = context.get("role", "general")
    company_style = context.get("company_style", "general")
    industry = context.get("industry", "general")

    tips = list(_ROLE_COACHING.get(role, _ROLE_COACHING["general"]))
    tips.extend(_COMPANY_HINTS.get(company_style, _COMPANY_HINTS["general"]))
    tips.extend(_INDUSTRY_COACHING.get(industry, _INDUSTRY_COACHING["general"]))
    return tips[:6]


def _learning_path(session_id: str) -> list[dict[str, str]]:
    radar = _scored_radar(session_id)
    ranked_areas = sorted(radar.items(), key=lambda item: item[1])
    focus_modules = []

    for area, score in ranked_areas[:3]:
        module_name = area.replace("_", " ").title()
        tip_payload = get_improvement_tips(area if area != "star" else "star_method")
        focus_modules.append(
            {
                "area": module_name,
                "priority": "high" if score < 65 else "medium" if score < 80 else "maintain",
                "goal": tip_payload["tips"][0],
                "drill": tip_payload["exercises"][0],
            }
        )

    return focus_modules


def _study_plan(session_id: str) -> list[str]:
    path = _learning_path(session_id)
    return [
        f"{index + 1}. {item['area']}: {item['goal']} Practice drill: {item['drill']}"
        for index, item in enumerate(path)
    ]


def _previous_comparison(session_id: str, average_score: int) -> dict[str, Any] | None:
    context = _get_session_state(session_id)["context"]
    for report in reversed(_archived_reports):
        if report["session_id"] == session_id:
            continue
        if report.get("role") == context.get("role") and report.get("company_style") == context.get(
            "company_style"
        ):
            delta = average_score - report.get("average_score", 0)
            return {
                "previous_session_id": report["session_id"],
                "previous_average_score": report.get("average_score", 0),
                "score_delta": delta,
                "trend": "up" if delta > 0 else "down" if delta < 0 else "flat",
            }
    return None


# --------------------------------------------------------------------------------------
# Server-side API (session_id supplied by the caller, not the model)
# --------------------------------------------------------------------------------------


def build_session_history(session_id: str) -> dict[str, Any]:
    """Aggregated session history. Safe to call from HTTP handlers."""

    state = _get_session_state(session_id)
    feedback = state["feedback"]
    if not feedback:
        return {
            "session_id": session_id,
            "total_questions": 0,
            "scores": [],
            "average_score": 0,
            "latest_score": 0,
            "best_score": 0,
            "improvement": 0,
            "total_filler_words": sum(item["count"] for item in state["fillers"]),
            "history": [],
            "message": "No history yet. Let's begin the interview!",
        }

    scores = [item["overall"] for item in feedback]
    emotion_scores = [item["stress_score"] for item in state["emotion"]]
    engagement_scores = [item["engagement_score"] for item in state["engagement"]]
    total_fillers = sum(item["count"] for item in state["fillers"])

    return {
        "session_id": session_id,
        "total_questions": len(feedback),
        "scores": scores,
        "average_score": _safe_mean(scores),
        "best_score": max(scores),
        "latest_score": scores[-1],
        "improvement": scores[-1] - scores[0] if len(scores) > 1 else 0,
        "total_filler_words": total_fillers,
        "body_language_observations": len(state["body"]),
        "voice_observations": len(state["voice"]),
        "star_analyses": len(state["star"]),
        "fusion_analyses": len(state["fusion"]),
        "history": feedback,
        "emotion_summary": {
            "average_stress": _safe_mean(emotion_scores),
            "latest_emotion": state["emotion"][-1]["emotion_label"] if state["emotion"] else "unknown",
        },
        "engagement_summary": {
            "average_engagement": _safe_mean(engagement_scores),
            "latest_engagement": engagement_scores[-1] if engagement_scores else 0,
        },
        "competency_radar": _competency_radar(session_id),
        "heatmap": _heatmap(session_id),
        "milestones": _milestones_for(session_id),
    }


def build_session_dashboard(session_id: str) -> dict[str, Any]:
    """UI-friendly analytics snapshot. Safe to call from HTTP handlers."""

    history = build_session_history(session_id)
    if history["total_questions"] == 0:
        return {
            "session_id": session_id,
            "trend_points": [],
            "competency_radar": _competency_radar(session_id),
            "heatmap": [],
            "milestones": [],
            "learning_path": [],
            "industry_specific_coaching": _industry_specific_coaching(session_id),
        }

    return {
        "session_id": session_id,
        "trend_points": [
            {"question_number": item["question_number"], "overall": item["overall"]}
            for item in history["history"]
        ],
        "competency_radar": _competency_radar(session_id),
        "heatmap": _heatmap(session_id),
        "milestones": _milestones_for(session_id),
        "learning_path": _learning_path(session_id),
        "industry_specific_coaching": _industry_specific_coaching(session_id),
        "emotion_summary": history.get("emotion_summary", {}),
        "engagement_summary": history.get("engagement_summary", {}),
    }


def build_session_report(session_id: str) -> dict[str, Any]:
    """Builds the end-of-interview report deterministically.

    Exposed to both the model (via ``generate_session_report``) and the HTTP layer, so
    ending a call never depends on the model choosing to call a tool in time.
    """

    history = build_session_history(session_id)
    if history.get("total_questions", 0) == 0:
        return {
            "session_id": session_id,
            "total_questions_answered": 0,
            "average_score": 0,
            "report": "No questions were scored in this session.",
            "performance_tier": "Not enough data",
            "recommendations": [
                "Answer at least three questions for a meaningful coaching report.",
            ],
        }

    context = _get_session_state(session_id)["context"]
    average_score = history["average_score"]
    radar = _competency_radar(session_id)
    scored = _scored_radar(session_id)
    strongest_area = max(scored, key=lambda key: scored[key])
    weakest_area = min(scored, key=lambda key: scored[key])
    comparison = _previous_comparison(session_id, average_score)
    filler_total = history["total_filler_words"]

    performance_tier = (
        "Excellent - Interview Ready"
        if average_score >= 85
        else "Good - Minor Refinements Needed"
        if average_score >= 72
        else "Developing - Focused Practice Recommended"
        if average_score >= 55
        else "Building Foundation - Keep Practicing"
    )

    report = {
        "session_id": session_id,
        "role": context.get("role", "general"),
        "company_style": context.get("company_style", "general"),
        "industry": context.get("industry", "general"),
        "total_questions_answered": history["total_questions"],
        "average_score": average_score,
        "best_score": history["best_score"],
        "score_improvement": history["improvement"],
        "performance_tier": performance_tier,
        "confidence": radar["confidence"],
        "clarity": radar["clarity"],
        "body_language": radar["body_language"],
        "content": radar["content"],
        "star_score": radar["star"],
        "voice_score": radar["voice"],
        "engagement_score": radar["engagement"],
        "strongest_area": strongest_area.replace("_", " ").title(),
        "weakest_area": weakest_area.replace("_", " ").title(),
        "filler_word_summary": {
            "total": filler_total,
            "rating": "Excellent" if filler_total == 0 else "Good" if filler_total <= 5 else "Needs Work",
            "measured_from": "gemini_input_transcription",
        },
        "heatmap": _heatmap(session_id),
        "competency_radar": radar,
        "milestones": _milestones_for(session_id),
        "learning_path": _learning_path(session_id),
        "study_plan": _study_plan(session_id),
        "industry_specific_coaching": _industry_specific_coaching(session_id),
        "comparison_to_previous_session": comparison,
        "strengths": (
            f"Your strongest area was {strongest_area.replace('_', ' ')}."
            " Keep leaning into that when answering tougher questions."
        ),
        "improvements": (
            f"Your biggest gain opportunity is {weakest_area.replace('_', ' ')}."
            " Focus on one tighter, more measurable answer structure next session."
        ),
        "recommendations": [
            f"Prioritize {weakest_area.replace('_', ' ')} in the next practice block.",
            f"Keep using {strongest_area.replace('_', ' ')} as a strength signal in interviews.",
            f"Filler usage total: {filler_total}. Aim to reduce it by 30 percent next session.",
            "Run one timed mock focused on concise, high-impact stories.",
        ],
    }

    _get_session_state(session_id)["reports"].append(report)
    _archived_reports.append(report)
    return report


def count_filler_words(text: str) -> dict[str, Any]:
    """Counts filler phrases in a transcript. Pure function, no session state."""

    text_lower = (text or "").lower()
    detected: dict[str, int] = {}
    # Blank out longer phrases as they are matched so "you know" is not also counted
    # as a bare "know"-adjacent single filler, and "like" inside "sort of like" is
    # attributed once.
    for filler in _FILLER_PATTERNS:
        pattern = rf"\b{re.escape(filler)}\b"
        matches = re.findall(pattern, text_lower)
        if matches:
            detected[filler] = len(matches)
            text_lower = re.sub(pattern, " ", text_lower)

    total_count = sum(detected.values())
    word_count = max(1, len(re.findall(r"\b\w+\b", text or "")))
    filler_rate = round((total_count / word_count) * 100, 1)

    if total_count == 0:
        rating = "excellent"
        tip = "No filler words detected. Keep that calm pace."
    elif total_count <= 2:
        rating = "good"
        tip = "Filler usage is low. Keep pausing before key points."
    elif total_count <= 5:
        rating = "average"
        tip = f"Watch out for {', '.join(detected.keys())}. Replace them with a short pause."
    else:
        rating = "needs_improvement"
        tip = "High filler usage detected. Slow down and let silence do the work."

    return {
        "total_filler_words": total_count,
        "detected_fillers": detected,
        "filler_rate_percent": filler_rate,
        "rating": rating,
        "coaching_tip": tip,
        "word_count": word_count,
    }


def analyze_pending_speech(session_id: str, question_number: int) -> dict[str, Any] | None:
    """Scores filler usage for the candidate's latest answer from the real transcript.

    Returns None when nothing was transcribed since the previous turn.
    """

    transcript = take_pending_transcript(session_id)
    if not transcript:
        return None

    stats = count_filler_words(transcript)
    _record_bucket(session_id, "fillers").append(
        {
            "question_number": question_number,
            "count": stats["total_filler_words"],
            "detected": stats["detected_fillers"],
            "filler_rate_percent": stats["filler_rate_percent"],
            "source": "input_transcription",
            "timestamp": _utc_now(),
        }
    )

    payload = {
        "question_number": question_number,
        "source": "input_transcription",
        **stats,
    }
    _broadcast(session_id, "detect_filler_words", payload)
    return payload


def _select_question(
    session_id: str,
    role: str,
    difficulty: str,
    category: str,
    company_style: str,
) -> dict[str, Any]:
    """Picks a question the candidate has not been asked yet in this session.

    Filters are relaxed one at a time (category, then difficulty, then role) rather than
    collapsing straight to "any general question", so a narrow request still degrades to
    something close to what was asked for.
    """

    state = _get_session_state(session_id)
    asked: list[str] = state["asked_questions"]

    def question_id(item: dict[str, Any]) -> str:
        return hashlib.sha1(item["text"].encode("utf-8")).hexdigest()[:12]

    pool = COMPANY_QUESTIONS.get(company_style, []) + INTERVIEW_QUESTIONS

    def matching(predicate) -> list[dict[str, Any]]:
        return [item for item in pool if predicate(item) and question_id(item) not in asked]

    candidates = (
        matching(
            lambda i: i["difficulty"] == difficulty
            and i["category"] == category
            and i["role"] in {role, "general"}
        )
        or matching(lambda i: i["difficulty"] == difficulty and i["role"] in {role, "general"})
        or matching(lambda i: i["category"] == category and i["role"] in {role, "general"})
        or matching(lambda i: i["role"] in {role, "general"})
        or matching(lambda i: True)
    )

    if not candidates:
        # Every question has been used; start a fresh rotation.
        state["asked_questions"] = []
        candidates = [item for item in pool if item["role"] in {role, "general"}] or pool

    selection = random.choice(candidates)
    state["asked_questions"].append(question_id(selection))
    return selection


COMPANY_QUESTIONS: dict[str, list[dict[str, Any]]] = {
    "amazon": [
        {
            "text": "Tell me about a time you had to deliver with limited resources.",
            "evaluation_criteria": "Ownership, prioritization, and frugality.",
            "difficulty": "medium",
            "category": "behavioral",
            "role": "general",
        },
        {
            "text": "Describe a disagreement with a leader and how you handled it.",
            "evaluation_criteria": "Respectful challenge, evidence, and follow-through.",
            "difficulty": "hard",
            "category": "behavioral",
            "role": "general",
        },
        {
            "text": "Tell me about a decision you made with incomplete data. What did you do to reduce the risk?",
            "evaluation_criteria": "Bias for action, judgment, and how they de-risked the call.",
            "difficulty": "medium",
            "category": "behavioral",
            "role": "general",
        },
        {
            "text": "Describe the highest standard you have ever set for your team. How did you hold the bar?",
            "evaluation_criteria": "Insist on highest standards, follow-through, and measurable quality.",
            "difficulty": "hard",
            "category": "leadership",
            "role": "general",
        },
        {
            "text": "Tell me about a customer problem you personally dug into. What did you find?",
            "evaluation_criteria": "Customer obsession and depth of investigation.",
            "difficulty": "easy",
            "category": "behavioral",
            "role": "general",
        },
    ],
    "google": [
        {
            "text": "Tell me about the hardest technical problem you untangled recently.",
            "evaluation_criteria": "Structured thinking, technical depth, and measurable impact.",
            "difficulty": "hard",
            "category": "technical",
            "role": "software_engineer",
        },
        {
            "text": "Describe a time you improved a process in a scalable way.",
            "evaluation_criteria": "Learning agility, collaboration, and systems impact.",
            "difficulty": "medium",
            "category": "behavioral",
            "role": "general",
        },
        {
            "text": "Walk me through how you would debug a service whose latency doubled overnight.",
            "evaluation_criteria": "Systematic hypothesis testing and use of telemetry.",
            "difficulty": "medium",
            "category": "technical",
            "role": "software_engineer",
        },
        {
            "text": "Tell me about something technical you learned recently and how you applied it.",
            "evaluation_criteria": "Learning agility and practical application.",
            "difficulty": "easy",
            "category": "technical",
            "role": "general",
        },
    ],
    "meta": [
        {
            "text": "Tell me about a time you shipped quickly and accepted a trade-off to learn faster.",
            "evaluation_criteria": "Speed, judgment, and iteration quality.",
            "difficulty": "medium",
            "category": "behavioral",
            "role": "general",
        },
        {
            "text": "Describe the biggest bet you have made on an ambiguous problem.",
            "evaluation_criteria": "Impact focus, conviction, and handling of ambiguity.",
            "difficulty": "hard",
            "category": "behavioral",
            "role": "general",
        },
        {
            "text": "What is a project where you had to influence people who did not report to you?",
            "evaluation_criteria": "Influence without authority and openness.",
            "difficulty": "easy",
            "category": "behavioral",
            "role": "general",
        },
    ],
    "apple": [
        {
            "text": "Tell me about a moment when attention to detail changed the outcome of your work.",
            "evaluation_criteria": "Craft, quality standards, and customer trust.",
            "difficulty": "medium",
            "category": "behavioral",
            "role": "general",
        },
        {
            "text": "Describe a time you refused to ship something. What was the cost and was it worth it?",
            "evaluation_criteria": "Quality bar, conviction, and cross-functional handling.",
            "difficulty": "hard",
            "category": "behavioral",
            "role": "general",
        },
        {
            "text": "What is a small detail in a product you use that you think is exceptional, and why?",
            "evaluation_criteria": "Product taste and articulation of craft.",
            "difficulty": "easy",
            "category": "behavioral",
            "role": "general",
        },
    ],
    "microsoft": [
        {
            "text": "Tell me about a failure that changed how you work.",
            "evaluation_criteria": "Growth mindset, specific behaviour change, and learning.",
            "difficulty": "medium",
            "category": "behavioral",
            "role": "general",
        },
        {
            "text": "Describe a time you partnered across teams to unblock a customer.",
            "evaluation_criteria": "Collaboration and customer success orientation.",
            "difficulty": "easy",
            "category": "behavioral",
            "role": "general",
        },
    ],
    "netflix": [
        {
            "text": "Tell me about a decision you made alone that you would defend to a room of skeptics.",
            "evaluation_criteria": "Independent judgment, candour, and impact.",
            "difficulty": "hard",
            "category": "behavioral",
            "role": "general",
        },
        {
            "text": "Describe feedback you gave that was hard to deliver. How did you frame it?",
            "evaluation_criteria": "Candour, communication, and follow-through.",
            "difficulty": "medium",
            "category": "leadership",
            "role": "general",
        },
    ],
}


# --------------------------------------------------------------------------------------
# Model-facing tools (session_id is injected, never a model argument)
# --------------------------------------------------------------------------------------


def get_interview_question(
    tool_context: ToolContext,
    category: str = "adaptive",
    weak_area: str = "",
) -> dict[str, Any]:
    """Selects the next interview question for this candidate.

    The role, company style, and difficulty come from the candidate's own session setup,
    so you do not need to supply them. Questions already asked in this session are never
    repeated.

    Args:
        category: One of "behavioral", "technical", "situational", "leadership", or
            "adaptive" to let the coach pick based on the role and the weak area.
        weak_area: Optional competency to target, e.g. "star_method" or "confidence".
    """

    session_id = _session_id_from_context(tool_context)
    if not session_id:
        return SESSION_UNAVAILABLE

    context = _get_session_state(session_id)["context"]
    role = context.get("role", "general")
    company_style = context.get("company_style", "general")
    difficulty = context.get("difficulty", "medium")
    industry = context.get("industry", "general")

    if not category or category == "adaptive":
        category = _ROLE_DEFAULT_CATEGORY.get(role, "behavioral")
        if weak_area in {"star_method", "confidence", "clarity"}:
            category = "behavioral"
        elif weak_area in {"content_quality", "software_design"}:
            category = "technical"

    selection = _select_question(session_id, role, difficulty, category, company_style)
    return {
        "question": selection["text"],
        "evaluation_criteria": selection["evaluation_criteria"],
        "role": role,
        "difficulty": difficulty,
        "category": selection["category"],
        "company_style": company_style,
        "industry": industry,
        "focus_area": weak_area or "balanced",
        "coaching_hint": _industry_specific_coaching(session_id)[0],
    }


def save_session_feedback(
    tool_context: ToolContext,
    question_number: int,
    confidence_score: int,
    clarity_score: int,
    body_language_score: int,
    content_score: int,
    star_score: int,
    feedback_summary: str,
    strengths: str,
    improvements: str,
) -> dict[str, Any]:
    """Scores the candidate's most recent answer and updates their live dashboard.

    Filler words are measured server-side from the real transcript, so do not pass a
    filler count. Role, company, and difficulty are taken from the session.

    Args:
        question_number: 1-based index of the question just answered.
        confidence_score: 0-100 judgement of how self-assured the delivery was.
        clarity_score: 0-100 judgement of how clearly the answer was structured.
        body_language_score: 0-100 from the camera; pass 0 if no camera is available.
        content_score: 0-100 judgement of the substance and relevance of the answer.
        star_score: 0-100 judgement of STAR structure.
        feedback_summary: One or two sentences of plain coaching feedback.
        strengths: What the candidate did well in this answer.
        improvements: The single highest-value thing to change next time.
    """

    session_id = _session_id_from_context(tool_context)
    if not session_id:
        return SESSION_UNAVAILABLE

    # Measure fillers from what the candidate actually said, not from a paraphrase.
    filler_payload = analyze_pending_speech(session_id, question_number)
    filler_word_count = filler_payload["total_filler_words"] if filler_payload else 0

    overall = _clamp(
        confidence_score * 0.20
        + clarity_score * 0.20
        + body_language_score * 0.15
        + content_score * 0.25
        + star_score * 0.20
    )

    feedback_bucket = _record_bucket(session_id, "feedback")
    previous_score = feedback_bucket[-1]["overall"] if feedback_bucket else None
    feedback_bucket.append(
        {
            "question_number": question_number,
            "confidence": confidence_score,
            "clarity": clarity_score,
            "body_language": body_language_score,
            "content": content_score,
            "star_score": star_score,
            "filler_word_count": filler_word_count,
            "overall": overall,
            "feedback": feedback_summary,
            "strengths": strengths,
            "improvements": improvements,
            "timestamp": _utc_now(),
        }
    )

    history = build_session_history(session_id)
    milestones = _milestones_for(session_id)
    scored = _scored_radar(session_id)
    weakest_area = min(scored, key=lambda key: scored[key])

    response = {
        "status": "saved",
        "question_number": question_number,
        "overall_score": overall,
        "confidence": confidence_score,
        "clarity": clarity_score,
        "body_language": body_language_score,
        "content": content_score,
        "star_score": star_score,
        "filler_word_count": filler_word_count,
        "trend": _trend_label(overall, previous_score),
        "total_questions_answered": len(feedback_bucket),
        "new_milestones": milestones,
        "weakest_area": weakest_area,
        "dashboard": build_session_dashboard(session_id),
        "history_snapshot": {
            "average_score": history["average_score"],
            "latest_score": history["latest_score"],
        },
    }
    _broadcast(session_id, "save_session_feedback", response)
    return response


def detect_filler_words(tool_context: ToolContext, question_number: int) -> dict[str, Any]:
    """Reports filler-word usage for the candidate's most recent answer.

    The count is measured from the real speech transcript captured by the live audio
    stream, so no transcript argument is needed or accepted.

    Args:
        question_number: 1-based index of the question just answered.
    """

    session_id = _session_id_from_context(tool_context)
    if not session_id:
        return SESSION_UNAVAILABLE

    payload = analyze_pending_speech(session_id, question_number)
    if payload is None:
        return {
            "question_number": question_number,
            "status": "no_speech_captured",
            "message": "No new candidate speech has been transcribed since the last analysis.",
        }
    return payload


def analyze_body_language(
    tool_context: ToolContext,
    question_number: int,
    eye_contact_rating: str,
    posture_rating: str,
    expression_rating: str,
    gesture_rating: str,
    gesture_type: str = "none",
    facial_expression_details: str = "",
    notes: str = "",
) -> dict[str, Any]:
    """Records what you observed in the candidate's camera feed during their answer.

    Only call this when a live camera frame is actually available.

    Args:
        question_number: 1-based index of the question just answered.
        eye_contact_rating: "excellent", "good", or "poor".
        posture_rating: "excellent", "good", or "poor".
        expression_rating: "confident", "engaged", "neutral", or "nervous".
        gesture_rating: "natural", "absent", or "excessive".
        gesture_type: "open_hands", "pointing", "nodding", "fidgeting", or "none".
        facial_expression_details: Short free-text note, e.g. "smiling while recalling".
        notes: Any additional observation worth storing.
    """

    session_id = _session_id_from_context(tool_context)
    if not session_id:
        return SESSION_UNAVAILABLE

    score_map = {"excellent": 95, "good": 78, "poor": 40}
    expression_map = {"confident": 92, "engaged": 86, "neutral": 72, "nervous": 45}
    gesture_map = {"natural": 90, "absent": 65, "excessive": 52}
    gesture_bonus = {"open_hands": 8, "pointing": 4, "nodding": 6, "fidgeting": -12, "none": 0}

    eye_score = score_map.get(eye_contact_rating, 68)
    posture_score = score_map.get(posture_rating, 68)
    expression_score = expression_map.get(expression_rating, 68)
    gesture_score = gesture_map.get(gesture_rating, 68) + gesture_bonus.get(gesture_type, 0)

    lowered_details = (facial_expression_details or "").lower()
    if "smiling" in lowered_details:
        expression_score += 8
    if "frowning" in lowered_details:
        expression_score -= 8

    overall = _clamp(
        eye_score * 0.30 + posture_score * 0.25 + expression_score * 0.25 + gesture_score * 0.20
    )
    _record_bucket(session_id, "body").append(
        {
            "question_number": question_number,
            "eye_contact": eye_contact_rating,
            "posture": posture_rating,
            "expression": expression_rating,
            "gestures": gesture_rating,
            "gesture_type": gesture_type,
            "facial_details": facial_expression_details,
            "overall": overall,
            "notes": notes,
            "timestamp": _utc_now(),
        }
    )

    response = {
        "status": "recorded",
        "question_number": question_number,
        "body_language_score": overall,
        "eye_contact": eye_contact_rating,
        "posture": posture_rating,
        "expression": expression_rating,
        "gestures": gesture_rating,
        "gesture_type": gesture_type,
        "facial_expression_details": facial_expression_details,
    }
    _broadcast(session_id, "analyze_body_language", response)
    return response


def analyze_voice_confidence(
    tool_context: ToolContext,
    question_number: int,
    pace_rating: str,
    volume_rating: str,
    clarity_rating: str,
    pausing_rating: str,
    tone_rating: str = "neutral",
) -> dict[str, Any]:
    """Records your judgement of the candidate's vocal delivery.

    Measured speech rate from the live transcript is blended in automatically.

    Args:
        question_number: 1-based index of the question just answered.
        pace_rating: "good", "too_slow", or "too_fast".
        volume_rating: "strong", "good", or "weak".
        clarity_rating: "very_clear", "clear", or "mumbled".
        pausing_rating: "strategic", "good", "none", or "excessive".
        tone_rating: "enthusiastic", "confident", "neutral", "monotone", or "hesitant".
    """

    session_id = _session_id_from_context(tool_context)
    if not session_id:
        return SESSION_UNAVAILABLE

    pace_map = {"good": 90, "too_slow": 62, "too_fast": 55}
    volume_map = {"strong": 94, "good": 82, "weak": 45}
    clarity_map = {"very_clear": 95, "clear": 82, "mumbled": 40}
    pause_map = {"strategic": 95, "good": 80, "none": 56, "excessive": 48}
    tone_map = {"enthusiastic": 95, "confident": 90, "neutral": 75, "monotone": 52, "hesitant": 44}

    overall = _clamp(
        (
            pace_map.get(pace_rating, 74)
            + volume_map.get(volume_rating, 74)
            + clarity_map.get(clarity_rating, 74)
            + pause_map.get(pausing_rating, 74)
            + tone_map.get(tone_rating, 74)
        )
        / 5
    )

    tips = []
    if pace_rating == "too_fast":
        tips.append("Slow down and land each key point.")
    if volume_rating == "weak":
        tips.append("Project more strongly through your conclusion.")
    if clarity_rating == "mumbled":
        tips.append("Over-enunciate for the first sentence of each answer.")
    if pausing_rating == "none":
        tips.append("Use short pauses instead of racing between thoughts.")
    if tone_rating in {"monotone", "hesitant"}:
        tips.append("Add more conviction when describing your impact.")
    if not tips:
        tips.append("Delivery sounds confident. Keep this pace and tone.")

    _record_bucket(session_id, "voice").append(
        {
            "question_number": question_number,
            "pace": pace_rating,
            "volume": volume_rating,
            "clarity": clarity_rating,
            "pausing": pausing_rating,
            "tone": tone_rating,
            "overall": overall,
            "timestamp": _utc_now(),
        }
    )

    response = {
        "status": "recorded",
        "question_number": question_number,
        "voice_confidence_score": overall,
        "pace": pace_rating,
        "volume": volume_rating,
        "clarity": clarity_rating,
        "pausing": pausing_rating,
        "tone": tone_rating,
        "coaching_tips": tips,
    }
    _broadcast(session_id, "analyze_voice_confidence", response)
    return response


def evaluate_star_method(
    tool_context: ToolContext,
    question_number: int,
    had_situation: bool,
    had_task: bool,
    had_action: bool,
    had_result: bool,
    result_was_quantified: bool,
) -> dict[str, Any]:
    """Evaluates whether the candidate's answer followed the STAR structure.

    Args:
        question_number: 1-based index of the question just answered.
        had_situation: True if they set the scene.
        had_task: True if they stated their specific responsibility.
        had_action: True if they described what they personally did.
        had_result: True if they described the outcome.
        result_was_quantified: True if the outcome included a concrete number or metric.
    """

    session_id = _session_id_from_context(tool_context)
    if not session_id:
        return SESSION_UNAVAILABLE

    components = [had_situation, had_task, had_action, had_result]
    score = sum(25 for component in components if component)
    if result_was_quantified:
        score = min(100, score + 10)

    missing = []
    if not had_situation:
        missing.append("Situation")
    if not had_task:
        missing.append("Task")
    if not had_action:
        missing.append("Action")
    if not had_result:
        missing.append("Result")

    _record_bucket(session_id, "star").append(
        {
            "question_number": question_number,
            "score": score,
            "quantified": result_was_quantified,
            "missing": missing,
            "timestamp": _utc_now(),
        }
    )

    response = {
        "star_score": score,
        "components_present": {
            "situation": had_situation,
            "task": had_task,
            "action": had_action,
            "result": had_result,
        },
        "result_quantified": result_was_quantified,
        "missing_components": missing,
        "coaching_note": "Strong STAR structure."
        if not missing
        else f"Missing: {', '.join(missing)}.",
    }
    _broadcast(session_id, "evaluate_star_method", response)
    return response


def cross_modal_analysis(
    tool_context: ToolContext,
    question_number: int,
    voice_confidence_score: int,
    body_language_score: int,
    content_score: int,
    engagement_score: int = 70,
    facial_sync: str = "aligned",
    vocal_energy: str = "steady",
) -> dict[str, Any]:
    """Fuses the audio and visual signals into a single presence score.

    Args:
        question_number: 1-based index of the question just answered.
        voice_confidence_score: 0-100 vocal delivery score.
        body_language_score: 0-100 non-verbal score.
        content_score: 0-100 substance score.
        engagement_score: 0-100 attentiveness score.
        facial_sync: "aligned" or "mismatched" between expression and words.
        vocal_energy: "energetic", "steady", or "flat".
    """

    session_id = _session_id_from_context(tool_context)
    if not session_id:
        return SESSION_UNAVAILABLE

    alignment_gap = abs(voice_confidence_score - body_language_score)
    alignment_bonus = 6 if alignment_gap <= 8 and facial_sync == "aligned" else 0
    energy_bonus = 4 if vocal_energy in {"steady", "energetic"} else -4
    fusion_score = _clamp(
        voice_confidence_score * 0.30
        + body_language_score * 0.30
        + content_score * 0.25
        + engagement_score * 0.15
        + alignment_bonus
        + energy_bonus
    )

    alignment = "high" if alignment_gap <= 8 else "medium" if alignment_gap <= 18 else "low"
    response = {
        "question_number": question_number,
        "fusion_score": fusion_score,
        "alignment": alignment,
        "facial_sync": facial_sync,
        "vocal_energy": vocal_energy,
        "presence_score": _clamp((voice_confidence_score + body_language_score) / 2),
        "communication_score": _clamp((content_score + engagement_score) / 2),
        "coaching_note": (
            "Your voice and non-verbal cues are reinforcing each other."
            if alignment == "high"
            else "Match your vocal confidence with stronger body language to feel more convincing."
        ),
    }
    _record_bucket(session_id, "fusion").append({**response, "timestamp": _utc_now()})
    _broadcast(session_id, "cross_modal_analysis", response)
    return response


def emotion_recognition(
    tool_context: ToolContext,
    question_number: int,
    vocal_tone: str,
    facial_expression: str,
    eye_contact_rating: str = "good",
    stress_markers: str = "",
) -> dict[str, Any]:
    """Estimates the candidate's confidence and stress from voice and face cues.

    Args:
        question_number: 1-based index of the question just answered.
        vocal_tone: "confident", "enthusiastic", "neutral", "hesitant", or "anxious".
        facial_expression: "calm", "engaged", "neutral", "tense", or "nervous".
        eye_contact_rating: "excellent", "good", or "poor".
        stress_markers: Comma-separated observations, e.g. "jaw_tension,rapid_blinking".
    """

    session_id = _session_id_from_context(tool_context)
    if not session_id:
        return SESSION_UNAVAILABLE

    tone_score = {"confident": 85, "enthusiastic": 88, "neutral": 70, "hesitant": 42, "anxious": 35}
    face_score = {"calm": 85, "engaged": 82, "neutral": 72, "tense": 45, "nervous": 38}
    eye_score = {"excellent": 90, "good": 78, "poor": 46}

    stress_penalty = 0
    if stress_markers:
        marker_count = len([item for item in stress_markers.split(",") if item.strip()])
        stress_penalty += min(20, marker_count * 5)

    confidence_signal = _clamp(
        tone_score.get(vocal_tone, 68) * 0.45
        + face_score.get(facial_expression, 68) * 0.35
        + eye_score.get(eye_contact_rating, 68) * 0.20
    )
    stress_score = _clamp(100 - confidence_signal + stress_penalty)
    emotion_label = (
        "confident"
        if confidence_signal >= 80 and stress_score <= 35
        else "steady"
        if stress_score <= 50
        else "stressed"
    )

    response = {
        "question_number": question_number,
        "emotion_label": emotion_label,
        "confidence_signal": confidence_signal,
        "stress_score": stress_score,
        "vocal_tone": vocal_tone,
        "facial_expression": facial_expression,
        "stress_markers": [item.strip() for item in stress_markers.split(",") if item.strip()],
        "coaching_note": (
            "You sound calm and in control."
            if emotion_label != "stressed"
            else "Reset with a slower first sentence and a deliberate breath before your next answer."
        ),
    }
    _record_bucket(session_id, "emotion").append({**response, "timestamp": _utc_now()})
    _broadcast(session_id, "emotion_recognition", response)
    return response


def engagement_tracking(
    tool_context: ToolContext,
    question_number: int,
    attention_score: int,
    distraction_count: int = 0,
    camera_available: bool = True,
    audio_energy: str = "steady",
) -> dict[str, Any]:
    """Tracks the candidate's attention and presence across the session.

    Args:
        question_number: 1-based index of the question just answered.
        attention_score: 0-100 judgement of how present and focused they appeared.
        distraction_count: Number of times they looked away or lost the thread.
        camera_available: False when running audio-only.
        audio_energy: "energetic", "steady", or "flat".
    """

    session_id = _session_id_from_context(tool_context)
    if not session_id:
        return SESSION_UNAVAILABLE

    distraction_penalty = min(20, distraction_count * 5)
    camera_penalty = 0 if camera_available else 6
    energy_bonus = 4 if audio_energy in {"steady", "energetic"} else -3

    engagement_score = _clamp(
        attention_score - distraction_penalty - camera_penalty + energy_bonus
    )
    response = {
        "question_number": question_number,
        "engagement_score": engagement_score,
        "attention_score": attention_score,
        "distraction_count": distraction_count,
        "camera_available": camera_available,
        "audio_energy": audio_energy,
        "status": "recorded",
    }
    _record_bucket(session_id, "engagement").append({**response, "timestamp": _utc_now()})
    _broadcast(session_id, "engagement_tracking", response)
    return response


def adjust_difficulty_level(tool_context: ToolContext, performance_trend: str) -> dict[str, Any]:
    """Recommends whether to raise or lower question difficulty.

    The current difficulty is read from the session, and the new level is stored back so
    subsequent calls to get_interview_question honour it.

    Args:
        performance_trend: "improving", "steady", or "declining".
    """

    session_id = _session_id_from_context(tool_context)
    if not session_id:
        return SESSION_UNAVAILABLE

    context = _get_session_state(session_id)["context"]
    current_difficulty = context.get("difficulty", "medium")

    history = build_session_history(session_id)
    if history["total_questions"] < 2:
        return {
            "current_difficulty": current_difficulty,
            "new_difficulty": current_difficulty,
            "reason": "Not enough scored answers yet.",
        }

    avg_score = history["average_score"]
    latest_score = history["latest_score"]
    engagement_avg = history.get("engagement_summary", {}).get("average_engagement", 0)
    stress_avg = history.get("emotion_summary", {}).get("average_stress", 0)

    if performance_trend == "improving" and avg_score >= 82 and stress_avg <= 45:
        new_difficulty = "hard"
        reason = "Strong momentum and stable delivery. Increase the challenge."
    elif performance_trend == "declining" and (avg_score < 62 or stress_avg >= 60):
        new_difficulty = "easy"
        reason = "Delivery is strained. Step down briefly to rebuild confidence."
    elif performance_trend == "steady" and avg_score >= 70:
        new_difficulty = "medium" if current_difficulty == "easy" else current_difficulty
        reason = "Performance is stable. Keep the candidate at a productive stretch level."
    else:
        new_difficulty = current_difficulty
        reason = "Keep monitoring one more turn before changing difficulty."

    context["difficulty"] = new_difficulty

    learning_path = _learning_path(session_id)
    weakest_module = learning_path[0]["area"] if learning_path else "Balanced Practice"
    return {
        "current_difficulty": current_difficulty,
        "new_difficulty": new_difficulty,
        "reason": reason,
        "avg_score": avg_score,
        "latest_score": latest_score,
        "engagement_average": engagement_avg,
        "recommended_focus": weakest_module,
    }


def get_session_history(tool_context: ToolContext) -> dict[str, Any]:
    """Returns everything recorded so far for this candidate's session."""

    session_id = _session_id_from_context(tool_context)
    if not session_id:
        return SESSION_UNAVAILABLE
    return build_session_history(session_id)


def get_improvement_tips(weak_area: str) -> dict[str, Any]:
    """Returns targeted drills for a specific competency.

    Args:
        weak_area: e.g. "star_method", "eye_contact", "filler_words", "pace",
            "confidence", "content_quality", "engagement", "multimodal_presence".
    """

    custom_tips = {
        "star_method": {
            "area": "STAR Method",
            "tips": [
                "Name the situation in one sentence, then move quickly to your action.",
                "Spend most of your time on what you did, not what the team did.",
                "Close with numbers or a concrete business outcome whenever possible.",
            ],
            "exercises": [
                "Rewrite one story tonight using STAR headers and practice it twice out loud.",
                "Record a two-minute answer and highlight every sentence that describes your action.",
            ],
        },
        "engagement": {
            "area": "Engagement",
            "tips": [
                "Answer the first sentence with energy so the interviewer feels your intent immediately.",
                "Keep eye contact steady and avoid looking away at the end of answers.",
            ],
            "exercises": [
                "Practice answering three questions while keeping your eyes at camera level.",
                "Use a two-second pause before you begin each answer instead of rushing in.",
            ],
        },
        "multimodal_presence": {
            "area": "Multimodal Presence",
            "tips": [
                "Make sure your face, posture, and voice all signal the same level of confidence.",
                "Use open-hand gestures on key points to reinforce important achievements.",
            ],
            "exercises": [
                "Practice one answer on camera and check whether your non-verbal cues match your words.",
                "Repeat the answer with stronger posture and a more decisive final sentence.",
            ],
        },
        "voice": {
            "area": "Voice",
            "tips": [
                "Land the final word of each sentence instead of trailing off.",
                "Vary your pitch on the numbers that matter most in your result.",
            ],
            "exercises": [
                "Read one answer aloud at half speed, then at normal speed, and keep the slower ending.",
                "Record two minutes and mark every sentence where your volume dropped.",
            ],
        },
        "body_language": {
            "area": "Body Language",
            "tips": [
                "Keep your hands visible and your shoulders square to the camera.",
                "Look at the lens, not at your own video preview, when delivering your result.",
            ],
            "exercises": [
                "Answer one question with a sticky note beside your webcam as an eye-line anchor.",
                "Film thirty seconds and count how many times you touch your face.",
            ],
        },
    }

    if weak_area in custom_tips:
        return custom_tips[weak_area]
    if weak_area in IMPROVEMENT_TIPS:
        return IMPROVEMENT_TIPS[weak_area]
    return {
        "area": weak_area.replace("_", " ").title(),
        "tips": [
            f"Practice one focused repetition on {weak_area.replace('_', ' ')} every day this week."
        ],
        "exercises": ["Do three timed mock answers and score yourself after each one."],
    }


def fetch_grounding_data(topic: str) -> dict[str, Any]:
    """Fetches verified interview coaching knowledge to avoid improvising advice.

    Args:
        topic: One of "star_method", "body_language_tips", "voice_delivery_tips",
            "common_mistakes", or "company_interview_styles".
    """

    if topic in GROUNDING_KNOWLEDGE:
        return GROUNDING_KNOWLEDGE[topic]
    return {
        "title": topic.replace("_", " ").title(),
        "info": "Focus on structured, observable interview behaviors and measurable outcomes.",
        "available_topics": sorted(GROUNDING_KNOWLEDGE.keys()),
    }


def save_session_recording(
    tool_context: ToolContext,
    recording_type: str = "audio",
    duration_seconds: int = 0,
    notes: str = "",
) -> dict[str, Any]:
    """Stores metadata about this practice session in the in-process session store.

    No audio or video is persisted anywhere; only this metadata record is kept, and it is
    discarded when the session ends.

    Args:
        recording_type: "audio" or "video".
        duration_seconds: Length of the session so far.
        notes: Any note worth attaching to the session record.
    """

    session_id = _session_id_from_context(tool_context)
    if not session_id:
        return SESSION_UNAVAILABLE

    timestamp = _utc_now()
    recording_id = f"{session_id}_{recording_type}_{timestamp.replace(':', '-')}"
    _recordings.setdefault(session_id, []).append(
        {
            "recording_id": recording_id,
            "session_id": session_id,
            "recording_type": recording_type,
            "duration_seconds": duration_seconds,
            "notes": notes,
            "timestamp": timestamp,
            "storage": "in_memory_only",
        }
    )
    return {
        "status": "saved",
        "recording_id": recording_id,
        "storage": "in_memory_only",
        "total_recordings": len(_recordings.get(session_id, [])),
    }


def generate_session_report(tool_context: ToolContext) -> dict[str, Any]:
    """Generates the candidate's full end-of-interview coaching report."""

    session_id = _session_id_from_context(tool_context)
    if not session_id:
        return SESSION_UNAVAILABLE

    report = build_session_report(session_id)
    _broadcast(session_id, "generate_session_report", report)
    return report


AGENT_TOOLS = [
    get_interview_question,
    save_session_feedback,
    detect_filler_words,
    analyze_body_language,
    analyze_voice_confidence,
    evaluate_star_method,
    cross_modal_analysis,
    emotion_recognition,
    engagement_tracking,
    get_improvement_tips,
    fetch_grounding_data,
    adjust_difficulty_level,
    get_session_history,
    save_session_recording,
    generate_session_report,
]

__all__ = [
    "AGENT_TOOLS",
    "SESSION_UNAVAILABLE",
    "adjust_difficulty_level",
    "analyze_body_language",
    "analyze_pending_speech",
    "analyze_voice_confidence",
    "build_session_dashboard",
    "build_session_history",
    "build_session_report",
    "clear_session",
    "count_filler_words",
    "cross_modal_analysis",
    "detect_filler_words",
    "emotion_recognition",
    "engagement_tracking",
    "evaluate_star_method",
    "fetch_grounding_data",
    "generate_session_report",
    "get_full_transcript",
    "get_improvement_tips",
    "get_interview_question",
    "get_session_history",
    "record_candidate_speech",
    "save_session_feedback",
    "save_session_recording",
    "seed_session_context",
    "take_pending_transcript",
]
