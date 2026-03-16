"""InterviewAce analytics and coaching tools."""

from __future__ import annotations

import os
import random
import re
from datetime import datetime, timezone
from statistics import mean
from typing import Any

try:
    from ..ws_manager import send_tool_result_sync
except ImportError:  # pragma: no cover - supports running from app/ directly
    try:
        from app.ws_manager import send_tool_result_sync
    except ImportError:  # pragma: no cover
        from ws_manager import send_tool_result_sync

from .grounding_data import GROUNDING_KNOWLEDGE, IMPROVEMENT_TIPS, INTERVIEW_QUESTIONS

_USE_FIRESTORE = os.getenv("USE_FIRESTORE", "false").lower() == "true"
_firestore_client = None

_sessions: dict[str, dict[str, Any]] = {}
_recordings: dict[str, list[dict[str, Any]]] = {}
_archived_reports: list[dict[str, Any]] = []

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
    "general": [
        "Stay concise and practical, then back up your story with evidence.",
    ],
}

_FILLER_PATTERNS = [
    "um",
    "uh",
    "like",
    "you know",
    "basically",
    "literally",
    "right",
    "so yeah",
    "kind of",
    "sort of",
    "i mean",
    "actually",
]

_MILESTONES = {
    "first_answer": {"badge": "First Rep", "description": "Completed the first scored answer."},
    "steady_voice": {"badge": "Voice Control", "description": "Sustained an average voice score of 80+."},
    "star_storyteller": {"badge": "STAR Storyteller", "description": "Averaged 85+ on STAR structure."},
    "low_fillers": {"badge": "Clear Speaker", "description": "Kept filler usage under control across the session."},
    "engaged_presence": {"badge": "Locked In", "description": "Maintained 80+ engagement across the latest turns."},
    "confidence_gain": {"badge": "Momentum", "description": "Improved overall performance by 10+ points."},
}


def _get_firestore():
    global _firestore_client
    if _firestore_client is None and _USE_FIRESTORE:
        try:
            from google.cloud import firestore

            _firestore_client = firestore.Client()
        except Exception as exc:  # pragma: no cover - best effort only
            print(f"[WARN] Firestore not available: {exc}")
    return _firestore_client


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _clamp(value: float, minimum: int = 0, maximum: int = 100) -> int:
    return max(minimum, min(maximum, round(value)))


def _safe_mean(values: list[int | float]) -> int:
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


def _resolve_session_id(session_id: str) -> str:
    if session_id == "default" or session_id not in _sessions:
        try:
            import sys
            if "app.ws_manager" in sys.modules:
                from app.ws_manager import _active_websockets
                if _active_websockets:
                    return next(iter(_active_websockets.keys()))
        except Exception:
            pass
    return session_id


def _get_session_state(session_id: str) -> dict[str, Any]:
    session_id = _resolve_session_id(session_id)
    existing = _sessions.get(session_id)
    if isinstance(existing, list):
        _sessions[session_id] = {
            "feedback": existing,
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
        }

    if session_id not in _sessions:
        _sessions[session_id] = {
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
        }
    return _sessions[session_id]


def _record_bucket(session_id: str, bucket: str) -> list[dict[str, Any]]:
    state = _get_session_state(session_id)
    state.setdefault(bucket, [])
    return state[bucket]


def _set_context(
    session_id: str,
    *,
    role: str | None = None,
    company_style: str | None = None,
    difficulty: str | None = None,
    industry: str | None = None,
) -> None:
    context = _get_session_state(session_id)["context"]
    if role:
        context["role"] = role
    if company_style:
        context["company_style"] = company_style
    if difficulty:
        context["difficulty"] = difficulty
    if industry:
        context["industry"] = industry


def _broadcast(session_id: str, tool_name: str, payload: dict[str, Any]) -> None:
    try:
        send_tool_result_sync(session_id, tool_name, payload)
    except Exception:  # pragma: no cover - UI transport is best effort
        pass


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
        weakest = min(area_scores, key=area_scores.get)
        heatmap.append(
            {
                "question_number": entry["question_number"],
                "overall": entry["overall"],
                "focus_area": weakest,
                "focus_score": area_scores[weakest],
                "intensity": "high" if entry["overall"] >= 85 else "medium" if entry["overall"] >= 70 else "low",
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
    if filler_total <= max(2, len(feedback) * 2) and feedback:
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
    radar = _competency_radar(session_id)
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
        if report.get("role") == context.get("role") and report.get("company_style") == context.get("company_style"):
            delta = average_score - report.get("average_score", 0)
            return {
                "previous_session_id": report["session_id"],
                "previous_average_score": report.get("average_score", 0),
                "score_delta": delta,
                "trend": "up" if delta > 0 else "down" if delta < 0 else "flat",
            }
    return None


def get_session_dashboard(session_id: str) -> dict[str, Any]:
    """Returns a UI-friendly analytics snapshot for the live dashboard."""

    history = get_session_history(session_id)
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


def get_interview_question(
    role: str,
    difficulty: str = "medium",
    category: str = "behavioral",
    company_style: str = "general",
    industry: str = "general",
    weak_area: str = "",
    session_id: str = "default",
) -> dict[str, Any]:
    """Selects an adaptive interview question for the candidate."""

    _set_context(
        session_id,
        role=role or "general",
        company_style=company_style or "general",
        difficulty=difficulty or "medium",
        industry=industry or "general",
    )

    if not category or category == "adaptive":
        category = _ROLE_DEFAULT_CATEGORY.get(role, "behavioral")
        if weak_area in {"star_method", "confidence", "clarity"}:
            category = "behavioral"
        elif weak_area in {"content_quality", "software_design"}:
            category = "technical"

    company_questions = {
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
        ],
        "meta": [
            {
                "text": "Tell me about a time you shipped quickly and accepted a trade-off to learn faster.",
                "evaluation_criteria": "Speed, judgment, and iteration quality.",
                "difficulty": "medium",
                "category": "behavioral",
                "role": "general",
            }
        ],
        "apple": [
            {
                "text": "Tell me about a moment when attention to detail changed the outcome of your work.",
                "evaluation_criteria": "Craft, quality standards, and customer trust.",
                "difficulty": "medium",
                "category": "behavioral",
                "role": "general",
            }
        ],
    }

    pool = [
        item
        for item in company_questions.get(company_style, [])
        if item["difficulty"] == difficulty
        and item["category"] == category
        and item["role"] in {role, "general"}
    ]
    if not pool:
        pool = [
            item
            for item in INTERVIEW_QUESTIONS
            if item["difficulty"] == difficulty
            and item["category"] == category
            and item["role"] in {role, "general"}
        ]
    if not pool:
        pool = [item for item in INTERVIEW_QUESTIONS if item["role"] == "general"]

    selection = random.choice(pool)
    return {
        "question": selection["text"],
        "evaluation_criteria": selection["evaluation_criteria"],
        "role": role,
        "difficulty": difficulty,
        "category": category,
        "company_style": company_style,
        "industry": industry,
        "focus_area": weak_area or "balanced",
        "coaching_hint": _industry_specific_coaching(session_id)[0],
    }


def save_session_feedback(
    session_id: str,
    question_number: int,
    confidence_score: int,
    clarity_score: int,
    body_language_score: int,
    content_score: int,
    star_score: int,
    filler_word_count: int,
    feedback_summary: str,
    strengths: str,
    improvements: str,
    role: str = "general",
    company_style: str = "general",
    difficulty: str = "medium",
    industry: str = "general",
) -> dict[str, Any]:
    """Saves a scored answer and returns a trend-aware payload."""

    _set_context(
        session_id,
        role=role,
        company_style=company_style,
        difficulty=difficulty,
        industry=industry,
    )

    overall = _clamp(
        confidence_score * 0.20
        + clarity_score * 0.20
        + body_language_score * 0.15
        + content_score * 0.25
        + star_score * 0.20
    )

    feedback_bucket = _record_bucket(session_id, "feedback")
    previous_score = feedback_bucket[-1]["overall"] if feedback_bucket else None
    entry = {
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
    feedback_bucket.append(entry)

    history = get_session_history(session_id)
    milestones = _milestones_for(session_id)
    radar = _competency_radar(session_id)
    weakest_area = min(radar, key=radar.get)

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
        "dashboard": get_session_dashboard(session_id),
        "history_snapshot": {
            "average_score": history["average_score"],
            "latest_score": history["latest_score"],
        },
    }
    _broadcast(session_id, "save_session_feedback", response)
    return response


def detect_filler_words(session_id: str, transcribed_text: str, question_number: int) -> dict[str, Any]:
    """Detects filler phrases in the transcribed answer."""

    text_lower = transcribed_text.lower()
    detected: dict[str, int] = {}

    for filler in _FILLER_PATTERNS:
        count = len(re.findall(rf"\b{re.escape(filler)}\b", text_lower))
        if count:
            detected[filler] = count

    total_count = sum(detected.values())
    word_count = max(1, len(re.findall(r"\b\w+\b", transcribed_text)))
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

    _record_bucket(session_id, "fillers").append(
        {
            "question_number": question_number,
            "count": total_count,
            "detected": detected,
            "filler_rate_percent": filler_rate,
        }
    )

    response = {
        "question_number": question_number,
        "total_filler_words": total_count,
        "detected_fillers": detected,
        "filler_rate_percent": filler_rate,
        "rating": rating,
        "coaching_tip": tip,
    }
    _broadcast(session_id, "detect_filler_words", response)
    return response


def analyze_body_language(
    session_id: str,
    question_number: int,
    eye_contact_rating: str,
    posture_rating: str,
    expression_rating: str,
    gesture_rating: str,
    gesture_type: str = "none",
    facial_expression_details: str = "",
    notes: str = "",
) -> dict[str, Any]:
    """Scores body language observations from the camera stream."""

    score_map = {"excellent": 95, "good": 78, "poor": 40}
    expression_map = {"confident": 92, "engaged": 86, "neutral": 72, "nervous": 45}
    gesture_map = {"natural": 90, "absent": 65, "excessive": 52}
    gesture_bonus = {"open_hands": 8, "pointing": 4, "nodding": 6, "fidgeting": -12, "none": 0}

    eye_score = score_map.get(eye_contact_rating, 68)
    posture_score = score_map.get(posture_rating, 68)
    expression_score = expression_map.get(expression_rating, 68)
    gesture_score = gesture_map.get(gesture_rating, 68) + gesture_bonus.get(gesture_type, 0)

    lowered_details = facial_expression_details.lower()
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
    session_id: str,
    question_number: int,
    pace_rating: str,
    volume_rating: str,
    clarity_rating: str,
    pausing_rating: str,
    tone_rating: str = "neutral",
    pause_duration_avg: float = 0.0,
) -> dict[str, Any]:
    """Scores the candidate's vocal delivery."""

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
    if pause_duration_avg > 2.0:
        overall = _clamp(overall - 10)
    elif 0 < pause_duration_avg < 0.5:
        overall = _clamp(overall - 5)

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
            "pause_avg": pause_duration_avg,
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
    session_id: str,
    question_number: int,
    had_situation: bool,
    had_task: bool,
    had_action: bool,
    had_result: bool,
    result_was_quantified: bool,
) -> dict[str, Any]:
    """Evaluates whether the answer followed STAR."""

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
        "coaching_note": "Strong STAR structure." if not missing else f"Missing: {', '.join(missing)}.",
    }
    _broadcast(session_id, "evaluate_star_method", response)
    return response


def cross_modal_analysis(
    session_id: str,
    question_number: int,
    voice_confidence_score: int,
    body_language_score: int,
    content_score: int,
    engagement_score: int = 70,
    facial_sync: str = "aligned",
    vocal_energy: str = "steady",
) -> dict[str, Any]:
    """Fuses audio and visual coaching signals into a single presence score."""

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
    session_id: str,
    question_number: int,
    vocal_tone: str,
    facial_expression: str,
    eye_contact_rating: str = "good",
    stress_markers: str = "",
    speech_rate_wpm: int = 140,
) -> dict[str, Any]:
    """Estimates confidence and stress from voice and face cues."""

    tone_score = {"confident": 85, "enthusiastic": 88, "neutral": 70, "hesitant": 42, "anxious": 35}
    face_score = {"calm": 85, "engaged": 82, "neutral": 72, "tense": 45, "nervous": 38}
    eye_score = {"excellent": 90, "good": 78, "poor": 46}

    stress_penalty = 0
    if stress_markers:
        stress_penalty += min(20, len([item for item in stress_markers.split(",") if item.strip()]) * 5)
    if speech_rate_wpm > 175:
        stress_penalty += 10
    if speech_rate_wpm < 100:
        stress_penalty += 5

    confidence_signal = _clamp(
        tone_score.get(vocal_tone, 68) * 0.45
        + face_score.get(facial_expression, 68) * 0.35
        + eye_score.get(eye_contact_rating, 68) * 0.20
    )
    stress_score = _clamp(100 - confidence_signal + stress_penalty)
    emotion_label = "confident" if confidence_signal >= 80 and stress_score <= 35 else "steady" if stress_score <= 50 else "stressed"

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
    session_id: str,
    question_number: int,
    attention_score: int,
    distraction_count: int = 0,
    response_latency_ms: int = 0,
    camera_available: bool = True,
    audio_energy: str = "steady",
) -> dict[str, Any]:
    """Tracks attention and presence across the session."""

    latency_penalty = 0
    if response_latency_ms > 4500:
        latency_penalty = 12
    elif response_latency_ms > 2500:
        latency_penalty = 6

    distraction_penalty = min(20, distraction_count * 5)
    camera_penalty = 0 if camera_available else 6
    energy_bonus = 4 if audio_energy in {"steady", "energetic"} else -3

    engagement_score = _clamp(attention_score - latency_penalty - distraction_penalty - camera_penalty + energy_bonus)
    response = {
        "question_number": question_number,
        "engagement_score": engagement_score,
        "attention_score": attention_score,
        "distraction_count": distraction_count,
        "response_latency_ms": response_latency_ms,
        "camera_available": camera_available,
        "audio_energy": audio_energy,
        "status": "recorded",
    }
    _record_bucket(session_id, "engagement").append({**response, "timestamp": _utc_now()})
    _broadcast(session_id, "engagement_tracking", response)
    return response


def adjust_difficulty_level(session_id: str, current_difficulty: str, performance_trend: str) -> dict[str, Any]:
    """Adjusts question difficulty using recent performance and engagement."""

    history = get_session_history(session_id)
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

    if performance_trend == "improving" and avg_score >= 82 and engagement_avg >= 75 and stress_avg <= 45:
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

    learning_path = _learning_path(session_id)
    weakest_module = learning_path[0]["area"] if learning_path else "Balanced Practice"
    return {
        "current_difficulty": current_difficulty,
        "new_difficulty": new_difficulty,
        "reason": reason,
        "avg_score": avg_score,
        "latest_score": latest_score,
        "recommended_focus": weakest_module,
    }


def get_session_history(session_id: str) -> dict[str, Any]:
    """Returns the aggregated session history."""

    state = _get_session_state(session_id)
    feedback = state["feedback"]
    if not feedback:
        return {
            "total_questions": 0,
            "scores": [],
            "average_score": 0,
            "message": "No history yet. Let's begin the interview!",
        }

    scores = [item["overall"] for item in feedback]
    emotion_scores = [item["stress_score"] for item in state["emotion"]]
    engagement_scores = [item["engagement_score"] for item in state["engagement"]]
    total_fillers = sum(item["count"] for item in state["fillers"])

    return {
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


def get_improvement_tips(weak_area: str) -> dict[str, Any]:
    """Returns targeted coaching for a weak area."""

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
    }

    if weak_area in custom_tips:
        return custom_tips[weak_area]
    if weak_area in IMPROVEMENT_TIPS:
        return IMPROVEMENT_TIPS[weak_area]
    return {
        "area": weak_area.replace("_", " ").title(),
        "tips": [f"Practice one focused repetition on {weak_area.replace('_', ' ')} every day this week."],
        "exercises": ["Do three timed mock answers and score yourself after each one."],
    }


def fetch_grounding_data(topic: str) -> dict[str, Any]:
    """Fetches grounded knowledge to reduce hallucinated advice."""

    if topic in GROUNDING_KNOWLEDGE:
        return GROUNDING_KNOWLEDGE[topic]
    return {
        "title": topic.replace("_", " ").title(),
        "info": "Focus on structured, observable interview behaviors and measurable outcomes.",
    }


def save_session_recording(
    session_id: str,
    recording_type: str = "audio",
    duration_seconds: int = 0,
    notes: str = "",
) -> dict[str, Any]:
    """Stores session recording metadata."""

    timestamp = _utc_now()
    recording_id = f"{session_id}_{recording_type}_{timestamp.replace(':', '-')}"
    metadata = {
        "recording_id": recording_id,
        "session_id": session_id,
        "recording_type": recording_type,
        "duration_seconds": duration_seconds,
        "notes": notes,
        "timestamp": timestamp,
        "storage_path": "local_fallback",
    }
    _recordings.setdefault(session_id, []).append(metadata)
    return {
        "status": "saved",
        "recording_id": recording_id,
        "total_recordings": len(_recordings.get(session_id, [])),
    }


def generate_session_report(session_id: str) -> dict[str, Any]:
    """Generates a summary report for the full practice session."""

    history = get_session_history(session_id)
    if history.get("total_questions", 0) == 0:
        return {
            "report": "No questions were answered in this session.",
            "recommendations": ["Answer at least three questions for a meaningful coaching report."],
        }

    context = _get_session_state(session_id)["context"]
    average_score = history["average_score"]
    radar = _competency_radar(session_id)
    strongest_area = max(radar, key=radar.get)
    weakest_area = min(radar, key=radar.get)
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
            f" Keep leaning into that when answering tougher questions."
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
    _broadcast(session_id, "generate_session_report", report)
    return report


__all__ = [
    "_recordings",
    "_sessions",
    "adjust_difficulty_level",
    "analyze_body_language",
    "analyze_voice_confidence",
    "cross_modal_analysis",
    "detect_filler_words",
    "emotion_recognition",
    "engagement_tracking",
    "evaluate_star_method",
    "fetch_grounding_data",
    "generate_session_report",
    "get_improvement_tips",
    "get_interview_question",
    "get_session_dashboard",
    "get_session_history",
    "save_session_feedback",
    "save_session_recording",
]
