"""
InterviewAce — Root Agent Definition.
Built with Google ADK (Agent Development Kit) using the Gemini Live API Toolkit
for real-time bidirectional voice and video streaming.
"""

import os
from google.adk.agents.llm_agent import Agent
from .prompts import COACH_ACE_INSTRUCTION, AGENT_DESCRIPTION
from .tools import (
    get_interview_question,
    save_session_feedback,
    get_improvement_tips,
    fetch_grounding_data,
    get_session_history,
    save_session_recording,
    generate_session_report,
)

# The root_agent is the required export for ADK
root_agent = Agent(
    name="interview_ace",
    model=os.getenv("AGENT_MODEL", "gemini-2.0-flash"),
    description=AGENT_DESCRIPTION,
    instruction=COACH_ACE_INSTRUCTION,
    tools=[
        get_interview_question,
        save_session_feedback,
        get_improvement_tips,
        fetch_grounding_data,
        get_session_history,
        save_session_recording,
        generate_session_report,
    ],
)
