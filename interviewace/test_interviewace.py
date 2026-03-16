"""Unit tests for InterviewAce analytics tools and agent wiring."""

from __future__ import annotations

import importlib
import os
import sys
import types
import unittest
from unittest.mock import patch


FAKE_WS_MODULE = types.ModuleType("app.ws_manager")
FAKE_WS_MODULE.send_tool_result_sync = lambda *args, **kwargs: None
FAKE_WS_MODULE.register_ws = lambda *args, **kwargs: None
FAKE_WS_MODULE.unregister_ws = lambda *args, **kwargs: None
sys.modules.setdefault("app.ws_manager", FAKE_WS_MODULE)
sys.modules.setdefault("ws_manager", FAKE_WS_MODULE)

from app.interview_coach_agent import tools  # noqa: E402
from app.interview_coach_agent.grounding_data import GROUNDING_KNOWLEDGE  # noqa: E402
from app.runtime_config import get_default_agent_model, get_model_profile  # noqa: E402


class ToolTests(unittest.TestCase):
    def setUp(self):
        tools._sessions.clear()
        tools._recordings.clear()

    def test_save_feedback_builds_dashboard_snapshot(self):
        result = tools.save_session_feedback(
            session_id="session-a",
            question_number=1,
            confidence_score=84,
            clarity_score=82,
            body_language_score=80,
            content_score=88,
            star_score=78,
            filler_word_count=2,
            feedback_summary="Solid answer",
            strengths="Clear ownership",
            improvements="Quantify the result",
            role="software_engineer",
            company_style="google",
            difficulty="medium",
        )

        self.assertEqual(result["status"], "saved")
        self.assertIn("dashboard", result)
        self.assertEqual(result["dashboard"]["trend_points"][0]["overall"], result["overall_score"])
        self.assertIn(result["weakest_area"], {"voice", "engagement"})

    def test_filler_detection_counts_punctuation_wrapped_phrases(self):
        result = tools.detect_filler_words(
            "session-a",
            "Um, I was, like, basically trying to explain the result, you know?",
            1,
        )

        self.assertEqual(result["total_filler_words"], 4)
        self.assertEqual(result["detected_fillers"]["um"], 1)
        self.assertEqual(result["detected_fillers"]["you know"], 1)

    def test_multimodal_tools_feed_history_and_report(self):
        tools.save_session_feedback(
            session_id="session-a",
            question_number=1,
            confidence_score=76,
            clarity_score=72,
            body_language_score=70,
            content_score=80,
            star_score=74,
            filler_word_count=3,
            feedback_summary="Good start",
            strengths="Strong example",
            improvements="More concise result",
            role="product_manager",
            company_style="amazon",
            difficulty="medium",
        )
        tools.analyze_voice_confidence("session-a", 1, "good", "strong", "clear", "good", "confident", 1.2)
        tools.analyze_body_language("session-a", 1, "good", "good", "engaged", "natural", "open_hands", "smiling")
        fusion = tools.cross_modal_analysis("session-a", 1, 86, 84, 80, 82, "aligned", "steady")
        emotion = tools.emotion_recognition("session-a", 1, "confident", "calm", "good", "jaw_tension", 152)
        engagement = tools.engagement_tracking("session-a", 1, 88, 1, 900, True, "steady")
        report = tools.generate_session_report("session-a")

        self.assertGreaterEqual(fusion["fusion_score"], 80)
        self.assertIn(emotion["emotion_label"], {"confident", "steady"})
        self.assertGreaterEqual(engagement["engagement_score"], 80)
        self.assertIn("learning_path", report)
        self.assertIn("heatmap", report)
        self.assertIn("industry_specific_coaching", report)

    def test_adjust_difficulty_uses_recent_session_signals(self):
        for question_number, overall in ((1, 82), (2, 89)):
            tools.save_session_feedback(
                session_id="session-a",
                question_number=question_number,
                confidence_score=overall,
                clarity_score=overall,
                body_language_score=overall,
                content_score=overall,
                star_score=overall,
                filler_word_count=1,
                feedback_summary="Great",
                strengths="Strong",
                improvements="None",
                role="software_engineer",
                company_style="google",
                difficulty="medium",
            )
            tools.engagement_tracking("session-a", question_number, 88, 0, 500, True, "energetic")
            tools.emotion_recognition("session-a", question_number, "confident", "calm", "excellent", "", 140)

        result = tools.adjust_difficulty_level("session-a", "medium", "improving")
        self.assertEqual(result["new_difficulty"], "hard")
        self.assertIn("recommended_focus", result)

    def test_grounding_data_contains_expanded_company_styles(self):
        companies = GROUNDING_KNOWLEDGE["company_interview_styles"]
        self.assertIn("google", companies)
        self.assertIn("amazon", companies)
        self.assertIn("stripe", companies)


class RuntimeConfigTests(unittest.TestCase):
    def test_default_model_prefers_vertex_native_audio(self):
        with patch.dict(os.environ, {"GOOGLE_GENAI_USE_VERTEXAI": "true"}, clear=False):
            self.assertEqual(get_default_agent_model(), "gemini-live-2.5-flash-native-audio")

    def test_model_profile_distinguishes_audio_and_text_modes(self):
        audio_profile = get_model_profile("gemini-2.5-flash-native-audio-preview-12-2025")
        text_profile = get_model_profile("gemini-2.0-flash-exp")

        self.assertTrue(audio_profile.supports_audio_output)
        self.assertFalse(text_profile.supports_audio_output)


class AgentWiringTests(unittest.TestCase):
    def test_agent_exposes_new_multimodal_tools(self):
        fake_google = types.ModuleType("google")
        fake_adk = types.ModuleType("google.adk")
        fake_agents = types.ModuleType("google.adk.agents")
        fake_tools = types.ModuleType("google.adk.tools")

        class FakeAgent:
            def __init__(self, **kwargs):
                self.__dict__.update(kwargs)

        fake_agents.Agent = FakeAgent
        fake_tools.google_search = types.SimpleNamespace(__name__="google_search")

        with patch.dict(
            sys.modules,
            {
                "google": fake_google,
                "google.adk": fake_adk,
                "google.adk.agents": fake_agents,
                "google.adk.tools": fake_tools,
            },
            clear=False,
        ):
            import app.interview_coach_agent.agent as agent_module

            importlib.reload(agent_module)
            tool_names = [getattr(tool, "__name__", "") for tool in agent_module.root_agent.tools]

        self.assertIn("cross_modal_analysis", tool_names)
        self.assertIn("emotion_recognition", tool_names)
        self.assertIn("engagement_tracking", tool_names)
        self.assertIn("get_interview_question", tool_names)


if __name__ == "__main__":
    unittest.main()
