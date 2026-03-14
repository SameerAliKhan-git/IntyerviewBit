"""
InterviewAce - All Tool Definitions (3 Tiers).
Tier 1: Body Language AI, Emotion Detection, STAR Coach, Filler Word Detector
Tier 2: Company-specific mode, Resume analysis, Voice confidence
Tier 3: Session history, Difficulty scaling, Persona selection
"""

import os
import json
import random
from datetime import datetime, timezone

_USE_FIRESTORE = os.getenv("USE_FIRESTORE", "false").lower() == "true"
_firestore_client = None

def _get_firestore():
    global _firestore_client
    if _firestore_client is None and _USE_FIRESTORE:
        try:
            from google.cloud import firestore
            _firestore_client = firestore.Client()
        except Exception as e:
            print(f"[WARN] Firestore not available: {e}")
    return _firestore_client

from .grounding_data import INTERVIEW_QUESTIONS, GROUNDING_KNOWLEDGE, IMPROVEMENT_TIPS

# In-memory session store
_sessions: dict = {}
_recordings: dict = {}

# ─────────────────────────────────────────────────────
# TIER 1: CORE INTERVIEW TOOLS
# ─────────────────────────────────────────────────────

def get_interview_question(
    role: str,
    difficulty: str = "medium",
    category: str = "behavioral",
    company_style: str = "general",
) -> dict:
    """Fetches a relevant interview question based on the candidate's target role,
    difficulty level, question category, and company interview style.

    Args:
        role: The job role e.g. 'software_engineer', 'product_manager', 'data_scientist', 'general'
        difficulty: 'easy', 'medium', or 'hard'
        category: 'behavioral', 'situational', 'technical', or 'leadership'
        company_style: Interview style e.g. 'google', 'amazon', 'meta', 'apple', 'general'

    Returns:
        A dictionary with the question text, evaluation criteria, and coaching tips.
    """
    # Company-specific question sets (Tier 2)
    company_questions = {
        "amazon": [
            {"text": "Tell me about a time you had to work with limited resources to deliver a project.",
             "evaluation_criteria": "STAR structure, ownership, resourcefulness", "difficulty": "medium",
             "category": "behavioral", "role": "general", "lp": "Frugality"},
            {"text": "Describe a situation where you disagreed with your manager and how you handled it.",
             "evaluation_criteria": "conflict resolution, backbone vs. respect", "difficulty": "medium",
             "category": "behavioral", "role": "general", "lp": "Have Backbone; Disagree and Commit"},
            {"text": "Tell me about a time you delivered a project with a very tight deadline.",
             "evaluation_criteria": "prioritization, delivery, trade-offs", "difficulty": "hard",
             "category": "behavioral", "role": "general", "lp": "Deliver Results"},
            {"text": "Describe how you have used data to make a critical decision.",
             "evaluation_criteria": "analytical thinking, data-driven mindset", "difficulty": "hard",
             "category": "technical", "role": "general", "lp": "Are Right, A Lot"},
        ],
        "google": [
            {"text": "Tell me about your most technically challenging project.",
             "evaluation_criteria": "technical depth, impact, scale", "difficulty": "hard",
             "category": "technical", "role": "software_engineer"},
            {"text": "How do you approach a problem you have never seen before?",
             "evaluation_criteria": "structured thinking, first principles", "difficulty": "medium",
             "category": "behavioral", "role": "general"},
            {"text": "Describe a time when you improved a process significantly.",
             "evaluation_criteria": "initiative, measurable impact, collaboration", "difficulty": "medium",
             "category": "behavioral", "role": "general"},
            {"text": "Tell me about a time you influenced without authority.",
             "evaluation_criteria": "leadership, communication, persuasion", "difficulty": "hard",
             "category": "leadership", "role": "general"},
        ],
        "meta": [
            {"text": "Tell me about a project where you had to move fast and make trade-offs.",
             "evaluation_criteria": "speed vs. quality trade-offs, pragmatism", "difficulty": "medium",
             "category": "behavioral", "role": "general"},
            {"text": "How have you contributed to building team culture?",
             "evaluation_criteria": "culture add, collaboration, communication", "difficulty": "medium",
             "category": "behavioral", "role": "general"},
            {"text": "Describe a time you shipped something imperfect but critical to learn fast.",
             "evaluation_criteria": "bias for action, learning from failure", "difficulty": "hard",
             "category": "behavioral", "role": "general"},
        ],
        "apple": [
            {"text": "How do you obsess over the details in your work?",
             "evaluation_criteria": "attention to quality, standard of excellence", "difficulty": "medium",
             "category": "behavioral", "role": "general"},
            {"text": "Tell me about a product decision you championed that others doubted.",
             "evaluation_criteria": "conviction, user empathy, courage", "difficulty": "hard",
             "category": "leadership", "role": "general"},
            {"text": "How do you balance innovation and reliability in your work?",
             "evaluation_criteria": "engineering excellence, user trust", "difficulty": "hard",
             "category": "technical", "role": "general"},
        ],
    }

    # Try company-specific first
    if company_style and company_style in company_questions:
        pool = company_questions[company_style]
        matching = [q for q in pool if q.get("difficulty") == difficulty]
        if matching:
            q = random.choice(matching)
            return {
                "question": q["text"],
                "evaluation_criteria": q["evaluation_criteria"],
                "role": role, "difficulty": difficulty,
                "company_style": company_style,
                "leadership_principle": q.get("lp", ""),
                "hint": f"This is a {company_style.upper()} style question. Look for: {q['evaluation_criteria']}"
            }

    # Fall back to general question bank
    matching = [
        q for q in INTERVIEW_QUESTIONS
        if (q["role"] == role or q["role"] == "general")
        and q["difficulty"] == difficulty
        and q["category"] == category
    ]
    if not matching:
        matching = [q for q in INTERVIEW_QUESTIONS if q["role"] == "general"]

    q = random.choice(matching)
    return {
        "question": q["text"],
        "evaluation_criteria": q["evaluation_criteria"],
        "role": role, "difficulty": difficulty,
        "company_style": company_style,
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
) -> dict:
    """Saves comprehensive coaching feedback and performance scores after each answer.

    Args:
        session_id: Unique session identifier
        question_number: Which question this is (1, 2, 3...)
        confidence_score: 0-100, voice confidence and assertiveness
        clarity_score: 0-100, answer clarity and articulation
        body_language_score: 0-100, posture, eye contact, and presence from camera
        content_score: 0-100, answer quality and relevance
        star_score: 0-100, how well the STAR method was followed (Situation, Task, Action, Result)
        filler_word_count: Number of filler words detected (um, uh, like, etc.)
        feedback_summary: Brief coaching note
        strengths: What the candidate did well
        improvements: Specific improvement advice

    Returns:
        Confirmation with overall score and performance trend.
    """
    overall = round(
        confidence_score * 0.20 + clarity_score * 0.20 +
        body_language_score * 0.15 + content_score * 0.25 + star_score * 0.20
    )

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
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    if session_id not in _sessions:
        _sessions[session_id] = []
    _sessions[session_id].append(entry)

    history = _sessions[session_id]
    trend = "first_answer"
    if len(history) > 1:
        diff = overall - history[-2]["overall"]
        trend = f"improved_by_{diff}_points" if diff > 0 else (
            f"decreased_by_{abs(diff)}_points" if diff < 0 else "same_as_previous"
        )

    return {
        "status": "saved",
        "question_number": question_number,
        "overall_score": overall,
        "confidence": confidence_score,
        "clarity": clarity_score,
        "body_language": body_language_score,
        "content": content_score,
        "star_score": star_score,
        "filler_word_count": filler_word_count,
        "trend": trend,
        "total_questions_answered": len(history),
    }


# ─────────────────────────────────────────────────────
# TIER 1: FILLER WORD DETECTOR
# ─────────────────────────────────────────────────────

def detect_filler_words(
    session_id: str,
    transcribed_text: str,
    question_number: int,
) -> dict:
    """Analyzes the candidate's speech for filler words and speech patterns.
    Call this after EVERY answer to track overuse of filler language.

    Args:
        session_id: Unique session identifier
        transcribed_text: What the candidate said (from your observation of their speech)
        question_number: Which question this was for

    Returns:
        Filler word analysis with count, list of detected fillers, and coaching tip.
    """
    fillers = ["um", "uh", "like", "you know", "basically", "literally",
               "right", "so yeah", "kind of", "sort of", "i mean", "actually"]

    text_lower = transcribed_text.lower()
    detected = {}

    for filler in fillers:
        count = text_lower.count(f" {filler} ") + text_lower.count(f" {filler},")
        if text_lower.startswith(f"{filler} "):
            count += 1
        if count > 0:
            detected[filler] = count

    total_count = sum(detected.values())
    word_count = len(transcribed_text.split())
    filler_rate = round((total_count / max(word_count, 1)) * 100, 1)

    if total_count == 0:
        rating = "excellent"
        tip = "No filler words detected. Excellent speech clarity!"
    elif total_count <= 2:
        rating = "good"
        tip = "Very few filler words. Minor awareness needed."
    elif total_count <= 5:
        rating = "average"
        tip = f"Watch out for: {', '.join(detected.keys())}. Try pausing silently instead of filling."
    else:
        rating = "needs_improvement"
        tip = f"High filler word usage ({total_count} detected). Practice deliberate pausing."

    # Store cumulative
    key = f"{session_id}_fillers"
    if key not in _sessions:
        _sessions[key] = []
    _sessions[key].append({"q": question_number, "count": total_count, "detected": detected})

    return {
        "total_filler_words": total_count,
        "detected_fillers": detected,
        "filler_rate_percent": filler_rate,
        "rating": rating,
        "coaching_tip": tip,
        "question_number": question_number,
    }


# ─────────────────────────────────────────────────────
# TIER 1: BODY LANGUAGE ANALYZER (FROM CAMERA)
# ─────────────────────────────────────────────────────

def analyze_body_language(
    session_id: str,
    question_number: int,
    eye_contact_rating: str,
    posture_rating: str,
    expression_rating: str,
    gesture_rating: str,
    notes: str = "",
) -> dict:
    """Records body language analysis from camera observations.
    Call this every 2-3 questions to track non-verbal communication.

    Args:
        session_id: Unique session identifier
        question_number: Which question number this observation is for
        eye_contact_rating: 'excellent', 'good', 'poor' - how well they maintain eye contact with the camera
        posture_rating: 'excellent', 'good', 'poor' - sitting up straight, shoulders back
        expression_rating: 'confident', 'neutral', 'nervous', 'engaged' - primary facial expression
        gesture_rating: 'natural', 'excessive', 'absent' - hand and head gestures
        notes: Any specific observations from the camera

    Returns:
        Body language score and coaching notes.
    """
    score_map = {"excellent": 95, "good": 75, "poor": 40}
    expression_map = {"confident": 90, "engaged": 85, "neutral": 70, "nervous": 45}
    gesture_map = {"natural": 90, "absent": 65, "excessive": 55}

    eye_score = score_map.get(eye_contact_rating, 70)
    posture_score = score_map.get(posture_rating, 70)
    expression_score = expression_map.get(expression_rating, 70)
    gesture_score = gesture_map.get(gesture_rating, 70)

    overall = round((eye_score * 0.35 + posture_score * 0.30 +
                     expression_score * 0.25 + gesture_score * 0.10))

    entry = {
        "question_number": question_number,
        "eye_contact": eye_contact_rating,
        "posture": posture_rating,
        "expression": expression_rating,
        "gestures": gesture_rating,
        "overall": overall,
        "notes": notes,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    key = f"{session_id}_body"
    if key not in _sessions:
        _sessions[key] = []
    _sessions[key].append(entry)

    return {
        "body_language_score": overall,
        "eye_contact": eye_contact_rating,
        "posture": posture_rating,
        "expression": expression_rating,
        "gestures": gesture_rating,
        "status": "recorded",
    }


# ─────────────────────────────────────────────────────
# TIER 2: VOICE CONFIDENCE ANALYZER
# ─────────────────────────────────────────────────────

def analyze_voice_confidence(
    session_id: str,
    question_number: int,
    pace_rating: str,
    volume_rating: str,
    clarity_rating: str,
    pausing_rating: str,
) -> dict:
    """Analyzes voice delivery confidence separately from content quality.
    Call after each answer to build a comprehensive voice profile.

    Args:
        session_id: Session identifier
        question_number: Which question
        pace_rating: 'too_fast', 'good', 'too_slow'
        volume_rating: 'strong', 'good', 'weak'
        clarity_rating: 'very_clear', 'clear', 'mumbled'
        pausing_rating: 'strategic', 'good', 'none', 'excessive'

    Returns:
        Voice confidence score and coaching guidance.
    """
    pace_map = {"good": 90, "too_slow": 60, "too_fast": 55}
    volume_map = {"strong": 95, "good": 80, "weak": 45}
    clarity_map = {"very_clear": 95, "clear": 80, "mumbled": 40}
    pause_map = {"strategic": 95, "good": 80, "none": 55, "excessive": 50}

    scores = [
        pace_map.get(pace_rating, 75),
        volume_map.get(volume_rating, 75),
        clarity_map.get(clarity_rating, 75),
        pause_map.get(pausing_rating, 75),
    ]
    overall = round(sum(scores) / len(scores))

    tips = []
    if pace_rating == "too_fast":
        tips.append("Slow down — take a breath between sentences.")
    if pace_rating == "too_slow":
        tips.append("Increase your speaking pace to maintain energy.")
    if volume_rating == "weak":
        tips.append("Project your voice with more confidence.")
    if clarity_rating == "mumbled":
        tips.append("Open your mouth wider and enunciate each word.")
    if pausing_rating == "none":
        tips.append("Use deliberate pauses — they signal confidence, not weakness.")

    key = f"{session_id}_voice"
    if key not in _sessions:
        _sessions[key] = []
    _sessions[key].append({
        "question_number": question_number,
        "pace": pace_rating, "volume": volume_rating,
        "clarity": clarity_rating, "pausing": pausing_rating,
        "overall": overall,
    })

    return {
        "voice_confidence_score": overall,
        "pace": pace_rating,
        "volume": volume_rating,
        "clarity": clarity_rating,
        "pausing": pausing_rating,
        "coaching_tips": tips,
        "status": "recorded",
    }


# ─────────────────────────────────────────────────────
# TIER 2: STAR METHOD COACH
# ─────────────────────────────────────────────────────

def evaluate_star_method(
    session_id: str,
    question_number: int,
    had_situation: bool,
    had_task: bool,
    had_action: bool,
    had_result: bool,
    result_was_quantified: bool,
) -> dict:
    """Evaluates whether the candidate's answer followed the STAR method structure.
    Call after each behavioral/situational answer.

    Args:
        session_id: Session identifier
        question_number: Which question was answered
        had_situation: Did they describe the Situation/context?
        had_task: Did they explain their Task/role?
        had_action: Did they describe their specific Actions?
        had_result: Did they share the Result/outcome?
        result_was_quantified: Did they use numbers/metrics in their result?

    Returns:
        STAR score and specific guidance on which components were missing.
    """
    components = [had_situation, had_task, had_action, had_result]
    base_score = sum(25 for c in components if c)
    if result_was_quantified:
        base_score = min(100, base_score + 10)

    missing = []
    if not had_situation:
        missing.append("Situation (context/background)")
    if not had_task:
        missing.append("Task (your specific role)")
    if not had_action:
        missing.append("Action (what YOU did step-by-step)")
    if not had_result:
        missing.append("Result (measurable outcome)")

    key = f"{session_id}_star"
    if key not in _sessions:
        _sessions[key] = []
    _sessions[key].append({
        "question_number": question_number,
        "score": base_score,
        "quantified": result_was_quantified,
        "missing": missing,
    })

    return {
        "star_score": base_score,
        "components_present": {
            "situation": had_situation, "task": had_task,
            "action": had_action, "result": had_result,
        },
        "result_quantified": result_was_quantified,
        "missing_components": missing,
        "coaching_note": (
            "Strong STAR structure!" if not missing else
            f"Missing: {', '.join(missing)}. Always include all four parts."
        ),
    }


# ─────────────────────────────────────────────────────
# TIER 3: SESSION HISTORY & REPORTING
# ─────────────────────────────────────────────────────

def get_session_history(session_id: str) -> dict:
    """Retrieves complete performance history for the current session.

    Args:
        session_id: The unique session identifier

    Returns:
        Full history with scores, trends, and analysis.
    """
    if session_id in _sessions and _sessions[session_id]:
        history = _sessions[session_id]
        scores = [h["overall"] for h in history]
        filler_data = _sessions.get(f"{session_id}_fillers", [])
        body_data = _sessions.get(f"{session_id}_body", [])
        voice_data = _sessions.get(f"{session_id}_voice", [])
        star_data = _sessions.get(f"{session_id}_star", [])

        total_fillers = sum(f.get("count", 0) for f in filler_data)

        return {
            "total_questions": len(history),
            "scores": scores,
            "average_score": round(sum(scores) / len(scores)),
            "best_score": max(scores),
            "latest_score": scores[-1],
            "improvement": scores[-1] - scores[0] if len(scores) > 1 else 0,
            "total_filler_words": total_fillers,
            "body_language_observations": len(body_data),
            "star_analyses": len(star_data),
            "history": history,
        }

    return {
        "total_questions": 0, "scores": [], "average_score": 0,
        "message": "No history yet. Let's begin the interview!"
    }


def get_improvement_tips(weak_area: str) -> dict:
    """Fetches targeted improvement tips for a specific weak area.

    Args:
        weak_area: One of 'eye_contact', 'filler_words', 'posture', 'pace',
                   'confidence', 'content_quality', 'star_method'

    Returns:
        Targeted coaching tips and exercises.
    """
    tips_extra = {
        "star_method": {
            "area": "STAR method structure",
            "tips": [
                "Always start with 'In my role at [Company], I was faced with...' to set Situation.",
                "Explicitly state your personal Task: 'My responsibility was...'",
                "Use 'I specifically did...' to make Actions concrete and personal.",
                "End EVERY answer with a quantified result: 'This resulted in X% improvement.'",
            ],
            "exercises": [
                "Write out 5 stories in STAR format before your interview.",
                "Record yourself answering and verify all 4 parts are present.",
            ]
        },
        "filler_words": {
            "area": "Filler Word Reduction",
            "tips": [
                "Replace 'um/uh' with a silent pause — it sounds MORE confident, not less.",
                "If you forget what to say, say 'Let me think about that for a moment' instead.",
                "Slow your speaking pace — fillers often come from speaking too fast.",
            ],
            "exercises": [
                "Record 2 mins of yourself speaking. Count your fillers. Aim to reduce by 50% each session.",
                "Read books aloud for 10 minutes per day to build verbal fluency.",
            ]
        }
    }

    if weak_area in tips_extra:
        return tips_extra[weak_area]
    if weak_area in IMPROVEMENT_TIPS:
        return IMPROVEMENT_TIPS[weak_area]

    return {
        "area": weak_area,
        "tips": [f"Focus on deliberate practice in {weak_area.replace('_', ' ')}."],
        "exercises": ["Set a specific goal and track progress over 5 sessions."]
    }


def fetch_grounding_data(topic: str) -> dict:
    """Fetches verified interview coaching knowledge to prevent hallucinations.

    Args:
        topic: One of 'star_method', 'body_language_tips', 'voice_delivery_tips', 'common_mistakes'

    Returns:
        Factual grounding data from the verified knowledge base.
    """
    if topic in GROUNDING_KNOWLEDGE:
        return GROUNDING_KNOWLEDGE[topic]
    return {
        "title": topic.replace("_", " ").title(),
        "info": "Use established interview frameworks and focus on specific, observable behaviors."
    }


def save_session_recording(
    session_id: str,
    recording_type: str = "audio",
    duration_seconds: int = 0,
    notes: str = "",
) -> dict:
    """Records metadata about a practice session for later review.

    Args:
        session_id: Unique session identifier
        recording_type: Type of recording ('audio', 'video', 'full_session')
        duration_seconds: Total session duration
        notes: Session notes/summary

    Returns:
        Confirmation and storage details.
    """
    timestamp = datetime.now(timezone.utc).isoformat()
    recording_id = f"{session_id}_{recording_type}_{timestamp.replace(':', '-')}"
    meta = {
        "recording_id": recording_id,
        "session_id": session_id,
        "recording_type": recording_type,
        "duration_seconds": duration_seconds,
        "notes": notes,
        "timestamp": timestamp,
        "gcs_path": "local_fallback",
    }
    if session_id not in _recordings:
        _recordings[session_id] = []
    _recordings[session_id].append(meta)
    return {"status": "saved", "recording_id": recording_id, "total_recordings": len(_recordings.get(session_id, []))}


def generate_session_report(session_id: str) -> dict:
    """Generates a comprehensive end-of-session performance report.
    Call this when the candidate wants to end the interview.

    Args:
        session_id: The unique session identifier

    Returns:
        Full performance report with all metrics across all 3 tiers.
    """
    history_data = get_session_history(session_id)
    if history_data.get("total_questions", 0) == 0:
        return {
            "report": "No questions were answered in this session.",
            "recommendations": ["Try answering at least 3 questions for meaningful feedback."],
        }

    history = history_data.get("history", [])
    total_q = history_data["total_questions"]
    avg_score = history_data.get("average_score", 0)
    best_score = history_data.get("best_score", 0)
    improvement = history_data.get("improvement", 0)
    total_fillers = history_data.get("total_filler_words", 0)

    # Area averages
    areas = {"confidence": 0, "clarity": 0, "body_language": 0, "content": 0, "star_score": 0}
    for entry in history:
        for k in areas:
            areas[k] += entry.get(k, 0)
    area_avgs = {k: round(v / total_q) for k, v in areas.items()}

    strongest = max(area_avgs, key=lambda k: area_avgs[k])
    weakest = min(area_avgs, key=lambda k: area_avgs[k])

    tier = (
        "Excellent — Interview Ready" if avg_score >= 85 else
        "Good — Minor Refinements Needed" if avg_score >= 70 else
        "Developing — Focused Practice Recommended" if avg_score >= 55 else
        "Building Foundation — Regular Practice Essential"
    )

    filler_rating = (
        "Excellent" if total_fillers == 0 else
        "Good" if total_fillers <= 5 else
        "Average" if total_fillers <= 15 else
        "Needs Work"
    )

    return {
        "session_id": session_id,
        "total_questions_answered": total_q,
        "average_score": avg_score,
        "best_score": best_score,
        "score_improvement": improvement,
        "performance_tier": tier,
        "area_averages": area_avgs,
        "strongest_area": strongest.replace("_", " ").title(),
        "weakest_area": weakest.replace("_", " ").title(),
        "filler_word_summary": {
            "total": total_fillers,
            "rating": filler_rating,
        },
        "recommendations": [
            f"Focus on: {weakest.replace('_', ' ').title()} — currently {area_avgs[weakest]}%",
            f"Your strongest skill: {strongest.replace('_', ' ').title()} at {area_avgs[strongest]}%",
            f"Filler words: {total_fillers} total — {filler_rating}",
            "Practice 3-5 more sessions to reach interview-ready level.",
        ],
    }
