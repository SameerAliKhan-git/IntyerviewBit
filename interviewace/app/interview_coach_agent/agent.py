"""InterviewAce root agent definition."""

from __future__ import annotations

from google.adk.agents import Agent
from google.adk.tools import google_search

try:
    from ..runtime_config import get_default_agent_model
except ImportError:  # pragma: no cover - supports running from app/ directly
    from runtime_config import get_default_agent_model

from .prompts import AGENT_DESCRIPTION, COACH_ACE_INSTRUCTION
from .tools import (
    adjust_difficulty_level,
    analyze_body_language,
    analyze_voice_confidence,
    cross_modal_analysis,
    detect_filler_words,
    emotion_recognition,
    engagement_tracking,
    evaluate_star_method,
    fetch_grounding_data,
    generate_session_report,
    get_improvement_tips,
    get_interview_question,
    get_session_history,
    save_session_feedback,
    save_session_recording,
)


root_agent = Agent(
    name="interview_ace",
    model=get_default_agent_model(),
    description=AGENT_DESCRIPTION,
    instruction=COACH_ACE_INSTRUCTION,
    tools=[
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
        google_search,
    ],
)
