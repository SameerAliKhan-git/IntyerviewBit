"""InterviewAce root agent definition."""

from __future__ import annotations

import logging

from google.adk.agents import Agent
from google.adk.tools import google_search
from google.adk.tools.agent_tool import AgentTool

try:
    from ..runtime_config import (
        get_default_agent_model,
        get_search_model,
        search_grounding_enabled,
    )
except ImportError:  # pragma: no cover - supports running from app/ directly
    from runtime_config import (  # type: ignore
        get_default_agent_model,
        get_search_model,
        search_grounding_enabled,
    )

from .prompts import AGENT_DESCRIPTION, COACH_ACE_INSTRUCTION, SEARCH_AGENT_INSTRUCTION
from .tools import AGENT_TOOLS

logger = logging.getLogger(__name__)


def _build_tools() -> list:
    """Assembles the agent's toolset.

    ADK only permits one built-in tool per agent, and it cannot be combined with custom
    function tools on the same agent. ``google_search`` is therefore isolated in a
    dedicated sub-agent and surfaced to Coach Ace through ``AgentTool``, which is the
    supported way to mix a built-in tool with function tools.
    """

    tools = list(AGENT_TOOLS)

    if not search_grounding_enabled():
        logger.info("Search grounding disabled via ENABLE_SEARCH_GROUNDING.")
        return tools

    research_agent = Agent(
        name="interview_research",
        model=get_search_model(),
        description=(
            "Looks up current, verifiable facts about a company's interview process "
            "using Google Search."
        ),
        instruction=SEARCH_AGENT_INSTRUCTION,
        tools=[google_search],
    )
    tools.append(AgentTool(agent=research_agent))
    return tools


root_agent = Agent(
    name="interview_ace",
    model=get_default_agent_model(),
    description=AGENT_DESCRIPTION,
    instruction=COACH_ACE_INSTRUCTION,
    tools=_build_tools(),
)
