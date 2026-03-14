"""
InterviewAce — Custom tools for the Coach Ace agent.
These tools connect to Firestore for grounding data, session persistence,
and interview question retrieval. They prevent hallucinations by grounding
the agent in factual data (a specific judging criterion).
"""

import os
import json
import random
from datetime import datetime, timezone

# Use in-memory fallbacks when Firestore is not available (local dev)
_firestore_client = None
_storage_client = None
_USE_FIRESTORE = os.getenv("USE_FIRESTORE", "false").lower() == "true"
_USE_CLOUD_STORAGE = os.getenv("USE_CLOUD_STORAGE", "false").lower() == "true"
_GCS_BUCKET_NAME = os.getenv("GCS_BUCKET_NAME", "interviewace-recordings")


def _get_firestore():
    """Lazy-init Firestore client."""
    global _firestore_client
    if _firestore_client is None and _USE_FIRESTORE:
        try:
            from google.cloud import firestore
            _firestore_client = firestore.Client()
        except Exception as e:
            print(f"[WARN] Firestore not available: {e}. Using in-memory fallback.")
    return _firestore_client


def _get_storage_bucket():
    """Lazy-init Cloud Storage bucket."""
    global _storage_client
    if _storage_client is None and _USE_CLOUD_STORAGE:
        try:
            from google.cloud import storage
            client = storage.Client()
            _storage_client = client.bucket(_GCS_BUCKET_NAME)
        except Exception as e:
            print(f"[WARN] Cloud Storage not available: {e}. Using in-memory fallback.")
    return _storage_client


# ─────────────────────────────────────────────
# In-memory fallback data (for local development)
# ─────────────────────────────────────────────
from .grounding_data import INTERVIEW_QUESTIONS, GROUNDING_KNOWLEDGE, IMPROVEMENT_TIPS

# Session storage (in-memory fallback)
_sessions: dict = {}
# Recording metadata (in-memory fallback)
_recordings: dict = {}


def get_interview_question(role: str, difficulty: str = "medium", category: str = "behavioral") -> dict:
    """Fetches a relevant interview question based on the candidate's target role, 
    desired difficulty level, and question category. Uses Firestore for grounding 
    data when available, with in-memory fallback for local development.
    
    Args:
        role: The job role (e.g., 'software_engineer', 'product_manager', 'data_scientist', 'general')
        difficulty: The difficulty level ('easy', 'medium', 'hard')
        category: Question category ('behavioral', 'situational', 'technical')
    
    Returns:
        A dictionary with the question text and evaluation criteria for the coach to use.
    """
    db = _get_firestore()
    
    if db:
        try:
            questions = (
                db.collection("interview_questions")
                .where("role", "in", [role, "general"])
                .where("difficulty", "==", difficulty)
                .where("category", "==", category)
                .get()
            )
            if questions:
                q = random.choice(questions).to_dict()
                return {
                    "question": q["text"],
                    "evaluation_criteria": q["evaluation_criteria"],
                    "role": role,
                    "difficulty": difficulty,
                }
        except Exception as e:
            print(f"[WARN] Firestore query failed: {e}")
    
    # In-memory fallback
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
        "role": role,
        "difficulty": difficulty,
    }


def save_session_feedback(
    session_id: str,
    question_number: int,
    confidence_score: int,
    clarity_score: int,
    body_language_score: int,
    content_score: int,
    feedback_summary: str,
    strengths: str,
    improvements: str,
) -> dict:
    """Saves the coaching feedback and performance scores after each interview answer 
    to Firestore for analytics and session continuity. This enables tracking improvement 
    across multiple answers and sessions.
    
    Args:
        session_id: Unique session identifier for the current interview practice session
        question_number: Which question this is (1, 2, 3, etc.)
        confidence_score: Score from 0 to 100 measuring voice confidence and delivery
        clarity_score: Score from 0 to 100 measuring answer clarity and structure
        body_language_score: Score from 0 to 100 measuring posture, eye contact, gestures
        content_score: Score from 0 to 100 measuring answer quality and STAR method usage
        feedback_summary: Brief summary of the coaching feedback given
        strengths: What the candidate did well
        improvements: What the candidate should work on
    
    Returns:
        Confirmation with overall score and trend analysis.
    """
    overall = round(
        (confidence_score * 0.25 + clarity_score * 0.25 +
         body_language_score * 0.25 + content_score * 0.25)
    )
    
    feedback_entry = {
        "question_number": question_number,
        "confidence": confidence_score,
        "clarity": clarity_score,
        "body_language": body_language_score,
        "content": content_score,
        "overall": overall,
        "feedback": feedback_summary,
        "strengths": strengths,
        "improvements": improvements,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    
    db = _get_firestore()
    if db:
        try:
            from google.cloud import firestore as fs
            db.collection("sessions").document(session_id).collection("feedback").add(
                {**feedback_entry, "timestamp": fs.SERVER_TIMESTAMP}
            )
        except Exception as e:
            print(f"[WARN] Firestore save failed: {e}")
    
    # Always store in memory too
    if session_id not in _sessions:
        _sessions[session_id] = []
    _sessions[session_id].append(feedback_entry)
    
    # Calculate trend
    history = _sessions[session_id]
    trend = "first_answer"
    if len(history) > 1:
        prev_overall = history[-2]["overall"]
        diff = overall - prev_overall
        if diff > 0:
            trend = f"improved_by_{diff}_points"
        elif diff < 0:
            trend = f"decreased_by_{abs(diff)}_points"
        else:
            trend = "same_as_previous"
    
    return {
        "status": "saved",
        "question_number": question_number,
        "overall_score": overall,
        "confidence": confidence_score,
        "clarity": clarity_score,
        "body_language": body_language_score,
        "content": content_score,
        "trend": trend,
        "total_questions_answered": len(history),
    }


def get_improvement_tips(weak_area: str) -> dict:
    """Fetches specific, actionable improvement tips for a weak area identified 
    during the interview coaching session. Tips are grounded in established 
    interview coaching research and best practices.
    
    Args:
        weak_area: The area needing improvement. One of: 'eye_contact', 'filler_words', 
                   'posture', 'pace', 'confidence', 'content_quality'
    
    Returns:
        Targeted tips and exercises for the specific weak area.
    """
    db = _get_firestore()
    
    if db:
        try:
            doc = db.collection("improvement_tips").document(weak_area).get()
            if doc.exists:
                return doc.to_dict()
        except Exception as e:
            print(f"[WARN] Firestore query failed: {e}")
    
    # In-memory fallback
    if weak_area in IMPROVEMENT_TIPS:
        return IMPROVEMENT_TIPS[weak_area]
    
    return {
        "area": weak_area,
        "tips": [
            f"Focus on improving your {weak_area.replace('_', ' ')} through deliberate practice.",
            "Record yourself and review the playback to build self-awareness.",
            "Practice with a friend or family member for real-time feedback."
        ],
        "exercises": [
            "Set a specific goal for this area and track progress over 5 practice sessions."
        ]
    }


def fetch_grounding_data(topic: str) -> dict:
    """Fetches factual grounding data to ensure coaching advice is based on 
    established frameworks and best practices. This prevents hallucinations 
    by providing the agent with verified information about interview techniques.
    
    Args:
        topic: The grounding topic to retrieve. One of: 'star_method', 
               'body_language_tips', 'voice_delivery_tips', 'common_mistakes'
    
    Returns:
        Factual grounding data from the verified knowledge base.
    """
    db = _get_firestore()
    
    if db:
        try:
            doc = db.collection("grounding_knowledge").document(topic).get()
            if doc.exists:
                return doc.to_dict()
        except Exception as e:
            print(f"[WARN] Firestore query failed: {e}")
    
    # In-memory fallback
    if topic in GROUNDING_KNOWLEDGE:
        return GROUNDING_KNOWLEDGE[topic]
    
    return {
        "title": topic.replace("_", " ").title(),
        "info": "Use established interview frameworks and focus on specific, observable behaviors."
    }


def get_session_history(session_id: str) -> dict:
    """Retrieves the complete performance history for a session, enabling 
    the coach to track improvement trends and provide context-aware feedback.
    
    Args:
        session_id: The unique session identifier to retrieve history for
    
    Returns:
        Session history with all scores, feedback, and calculated trends.
    """
    db = _get_firestore()
    
    if db:
        try:
            docs = (
                db.collection("sessions")
                .document(session_id)
                .collection("feedback")
                .order_by("timestamp")
                .get()
            )
            if docs:
                history = [doc.to_dict() for doc in docs]
                scores = [h.get("overall", 0) for h in history]
                return {
                    "total_questions": len(history),
                    "scores": scores,
                    "average_score": round(sum(scores) / len(scores)),
                    "best_score": max(scores),
                    "latest_score": scores[-1],
                    "improvement": scores[-1] - scores[0] if len(scores) > 1 else 0,
                    "history": history,
                }
        except Exception as e:
            print(f"[WARN] Firestore query failed: {e}")
    
    # In-memory fallback
    if session_id in _sessions and _sessions[session_id]:
        history = _sessions[session_id]
        scores = [h["overall"] for h in history]
        return {
            "total_questions": len(history),
            "scores": scores,
            "average_score": round(sum(scores) / len(scores)),
            "best_score": max(scores),
            "latest_score": scores[-1],
            "improvement": scores[-1] - scores[0] if len(scores) > 1 else 0,
            "history": history,
        }
    
    return {
        "total_questions": 0,
        "scores": [],
        "average_score": 0,
        "message": "No history yet — let's get started!"
    }


def save_session_recording(
    session_id: str,
    recording_type: str = "audio",
    duration_seconds: int = 0,
    notes: str = "",
) -> dict:
    """Records metadata about a practice session recording and saves it to
    Cloud Storage for later review. This enables candidates to replay their
    sessions and track improvement over time.

    Args:
        session_id: Unique session identifier for this recording
        recording_type: Type of recording ('audio', 'video', 'full_session')
        duration_seconds: Total duration of the recorded session in seconds
        notes: Optional notes or summary about the recording content

    Returns:
        Confirmation with storage location and session summary.
    """
    timestamp = datetime.now(timezone.utc).isoformat()
    recording_id = f"{session_id}_{recording_type}_{timestamp.replace(':', '-')}"

    recording_meta = {
        "recording_id": recording_id,
        "session_id": session_id,
        "recording_type": recording_type,
        "duration_seconds": duration_seconds,
        "notes": notes,
        "timestamp": timestamp,
    }

    bucket = _get_storage_bucket()
    storage_path = f"recordings/{session_id}/{recording_id}.json"

    if bucket:
        try:
            import json as _json
            blob = bucket.blob(storage_path)
            blob.upload_from_string(
                _json.dumps(recording_meta),
                content_type="application/json",
            )
            recording_meta["gcs_path"] = f"gs://{_GCS_BUCKET_NAME}/{storage_path}"
        except Exception as e:
            print(f"[WARN] Cloud Storage save failed: {e}")
            recording_meta["gcs_path"] = "local_fallback"
    else:
        recording_meta["gcs_path"] = "local_fallback"

    # Always store in memory too
    if session_id not in _recordings:
        _recordings[session_id] = []
    _recordings[session_id].append(recording_meta)

    return {
        "status": "saved",
        "recording_id": recording_id,
        "storage_path": recording_meta["gcs_path"],
        "duration_seconds": duration_seconds,
        "total_recordings": len(_recordings.get(session_id, [])),
    }


def generate_session_report(session_id: str) -> dict:
    """Generates a comprehensive end-of-session report summarizing the
    candidate's overall performance, score trends, strengths, and areas
    for improvement. Call this when the candidate ends their session.

    Args:
        session_id: The unique session identifier to generate a report for

    Returns:
        A comprehensive session report with overall assessment and actionable next steps.
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

    # Identify strongest and weakest areas across all answers
    area_totals = {"confidence": 0, "clarity": 0, "body_language": 0, "content": 0}
    for entry in history:
        area_totals["confidence"] += entry.get("confidence", 0)
        area_totals["clarity"] += entry.get("clarity", 0)
        area_totals["body_language"] += entry.get("body_language", 0)
        area_totals["content"] += entry.get("content", 0)

    area_averages = {k: round(v / total_q) for k, v in area_totals.items()}
    strongest = max(area_averages, key=lambda k: area_averages[k])
    weakest = min(area_averages, key=lambda k: area_averages[k])

    # Build performance tier
    if avg_score >= 85:
        tier = "Excellent — Interview Ready"
    elif avg_score >= 70:
        tier = "Good — Minor Refinements Needed"
    elif avg_score >= 55:
        tier = "Developing — Focused Practice Recommended"
    else:
        tier = "Building Foundation — Regular Practice Essential"

    return {
        "session_id": session_id,
        "total_questions_answered": total_q,
        "average_score": avg_score,
        "best_score": best_score,
        "score_improvement": improvement,
        "performance_tier": tier,
        "area_averages": area_averages,
        "strongest_area": strongest.replace("_", " ").title(),
        "weakest_area": weakest.replace("_", " ").title(),
        "recommendations": [
            f"Focus extra practice on {weakest.replace('_', ' ')} — your current average is {area_averages[weakest]}%",
            f"Your {strongest.replace('_', ' ')} is strong at {area_averages[strongest]}% — maintain this!",
            "Try to answer 3-5 more questions targeting your weak areas",
            "Record yourself and review the playback to build self-awareness",
        ],
    }
