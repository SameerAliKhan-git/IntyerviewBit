"""
InterviewAce - Root Agent Definition (3 Tiers Enabled).
"""

import os
from google.adk.agents import Agent
from .prompts import COACH_ACE_INSTRUCTION, AGENT_DESCRIPTION
from .tools import (
    save_session_feedback,
    detect_filler_words,
    analyze_body_language,
    analyze_voice_confidence,
    evaluate_star_method,
    get_improvement_tips,
    fetch_grounding_data,
    get_session_history,
    save_session_recording,
    generate_session_report,
)

root_agent = Agent(
    name="interview_ace",
    model=os.getenv("AGENT_MODEL", "gemini-2.5-flash"),
    description=AGENT_DESCRIPTION,
    instruction=COACH_ACE_INSTRUCTION,
    tools=[
        # Tier 1 - Core + Filler + Body Language + STAR
        save_session_feedback,
        detect_filler_words,
        analyze_body_language,
        evaluate_star_method,
        # Tier 2 - Voice + Company-specific
        analyze_voice_confidence,
        get_improvement_tips,
        fetch_grounding_data,
        # Tier 3 - History & Reporting
        get_session_history,
        save_session_recording,
        generate_session_report,
    ],
)
