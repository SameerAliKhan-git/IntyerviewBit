"""Unit tests for InterviewAce analytics tools and agent wiring."""

from __future__ import annotations

import inspect
import os
import unittest
from unittest.mock import patch

# The real ws_manager is used deliberately rather than a stub: with no sockets
# registered its broadcast is a no-op, and stubbing it into sys.modules here used to
# leak a partial module into every later test file in the same process.
from app.interview_coach_agent import tools  # noqa: E402
from app.interview_coach_agent.grounding_data import GROUNDING_KNOWLEDGE  # noqa: E402
from app.runtime_config import (  # noqa: E402
    get_default_agent_model,
    get_model_profile,
    normalize_company,
    normalize_difficulty,
    normalize_role,
    normalize_voice,
)


class FakeToolContext:
    """Stands in for ADK's ToolContext, which carries the session state dict."""

    def __init__(self, session_id: str | None):
        self.state = {"session_id": session_id} if session_id else {}


def context_for(session_id: str) -> FakeToolContext:
    return FakeToolContext(session_id)


class SessionBindingTests(unittest.TestCase):
    """The single most important invariant: analytics never cross sessions."""

    def setUp(self):
        tools._sessions.clear()
        tools._recordings.clear()

    def test_tools_refuse_to_record_without_a_bound_session(self):
        result = tools.save_session_feedback(
            FakeToolContext(None),
            question_number=1,
            confidence_score=80,
            clarity_score=80,
            body_language_score=80,
            content_score=80,
            star_score=80,
            feedback_summary="x",
            strengths="x",
            improvements="x",
        )

        self.assertEqual(result["error"], "session_unavailable")
        self.assertEqual(tools._sessions, {})

    def test_two_sessions_keep_separate_analytics(self):
        for session_id, value in (("session-a", 90), ("session-b", 40)):
            tools.save_session_feedback(
                context_for(session_id),
                question_number=1,
                confidence_score=value,
                clarity_score=value,
                body_language_score=value,
                content_score=value,
                star_score=value,
                feedback_summary="s",
                strengths="s",
                improvements="s",
            )

        history_a = tools.build_session_history("session-a")
        history_b = tools.build_session_history("session-b")

        self.assertEqual(history_a["total_questions"], 1)
        self.assertEqual(history_b["total_questions"], 1)
        self.assertEqual(history_a["latest_score"], 90)
        self.assertEqual(history_b["latest_score"], 40)

    def test_unknown_session_does_not_borrow_an_active_one(self):
        tools.save_session_feedback(
            context_for("session-a"),
            question_number=1,
            confidence_score=90,
            clarity_score=90,
            body_language_score=90,
            content_score=90,
            star_score=90,
            feedback_summary="s",
            strengths="s",
            improvements="s",
        )

        # A tool call carrying no session must not be attributed to session-a.
        tools.detect_filler_words(FakeToolContext(None), question_number=2)
        self.assertEqual(tools.build_session_history("session-a")["total_questions"], 1)


class FillerDetectionTests(unittest.TestCase):
    def setUp(self):
        tools._sessions.clear()

    def test_counts_punctuation_wrapped_phrases(self):
        stats = tools.count_filler_words(
            "Um, I was, like, basically trying to explain the result, you know?"
        )
        self.assertEqual(stats["total_filler_words"], 4)
        self.assertEqual(stats["detected_fillers"]["um"], 1)
        self.assertEqual(stats["detected_fillers"]["you know"], 1)

    def test_multiword_fillers_are_not_double_counted(self):
        stats = tools.count_filler_words("I mean, you know, it was sort of fine.")
        # "i mean", "you know", "sort of" -> 3, and no extra hit from overlapping words.
        self.assertEqual(stats["total_filler_words"], 3)

    def test_fillers_come_from_the_real_transcript_not_the_model(self):
        tools.record_candidate_speech("session-a", "Um, so basically I led the migration.")
        result = tools.detect_filler_words(context_for("session-a"), question_number=1)

        self.assertEqual(result["source"], "input_transcription")
        self.assertEqual(result["total_filler_words"], 2)

    def test_transcript_is_consumed_once_per_turn(self):
        tools.record_candidate_speech("session-a", "Um, yes.")
        first = tools.detect_filler_words(context_for("session-a"), question_number=1)
        second = tools.detect_filler_words(context_for("session-a"), question_number=1)

        self.assertEqual(first["total_filler_words"], 1)
        self.assertEqual(second["status"], "no_speech_captured")

    def test_feedback_uses_measured_filler_count(self):
        tools.record_candidate_speech("session-a", "Um, uh, like, you know, I basically did it.")
        result = tools.save_session_feedback(
            context_for("session-a"),
            question_number=1,
            confidence_score=70,
            clarity_score=70,
            body_language_score=70,
            content_score=70,
            star_score=70,
            feedback_summary="s",
            strengths="s",
            improvements="s",
        )
        self.assertEqual(result["filler_word_count"], 5)


class ToolTests(unittest.TestCase):
    def setUp(self):
        tools._sessions.clear()
        tools._recordings.clear()

    def test_save_feedback_builds_dashboard_snapshot(self):
        tools.seed_session_context("session-a", role="software_engineer", company_style="google")
        result = tools.save_session_feedback(
            context_for("session-a"),
            question_number=1,
            confidence_score=84,
            clarity_score=82,
            body_language_score=80,
            content_score=88,
            star_score=78,
            feedback_summary="Solid answer",
            strengths="Clear ownership",
            improvements="Quantify the result",
        )

        self.assertEqual(result["status"], "saved")
        self.assertEqual(result["dashboard"]["trend_points"][0]["overall"], result["overall_score"])

    def test_weakest_area_ignores_unmeasured_competencies(self):
        """Voice and engagement start at 0; ranking must not name an unmeasured area."""

        result = tools.save_session_feedback(
            context_for("session-a"),
            question_number=1,
            confidence_score=90,
            clarity_score=60,
            body_language_score=85,
            content_score=88,
            star_score=80,
            feedback_summary="s",
            strengths="s",
            improvements="s",
        )
        self.assertEqual(result["weakest_area"], "clarity")

    def test_multimodal_tools_feed_history_and_report(self):
        tools.seed_session_context("session-a", role="product_manager", company_style="amazon")
        tools.save_session_feedback(
            context_for("session-a"),
            question_number=1,
            confidence_score=76,
            clarity_score=72,
            body_language_score=70,
            content_score=80,
            star_score=74,
            feedback_summary="Good start",
            strengths="Strong example",
            improvements="More concise result",
        )
        tools.analyze_voice_confidence(
            context_for("session-a"), 1, "good", "strong", "clear", "good", "confident"
        )
        tools.analyze_body_language(
            context_for("session-a"), 1, "good", "good", "engaged", "natural", "open_hands", "smiling"
        )
        fusion = tools.cross_modal_analysis(context_for("session-a"), 1, 86, 84, 80, 82)
        emotion = tools.emotion_recognition(
            context_for("session-a"), 1, "confident", "calm", "good", "jaw_tension"
        )
        engagement = tools.engagement_tracking(context_for("session-a"), 1, 88, 1, True, "steady")
        report = tools.build_session_report("session-a")

        self.assertGreaterEqual(fusion["fusion_score"], 80)
        self.assertIn(emotion["emotion_label"], {"confident", "steady"})
        self.assertGreaterEqual(engagement["engagement_score"], 80)
        self.assertIn("learning_path", report)
        self.assertIn("heatmap", report)
        self.assertEqual(report["role"], "product_manager")

    def test_report_is_safe_when_nothing_was_scored(self):
        report = tools.build_session_report("empty-session")
        self.assertEqual(report["total_questions_answered"], 0)
        self.assertEqual(report["average_score"], 0)
        self.assertIn("recommendations", report)

    def test_adjust_difficulty_uses_session_signals_and_persists(self):
        tools.seed_session_context("session-a", role="software_engineer", difficulty="medium")
        for question_number, overall in ((1, 82), (2, 89)):
            tools.save_session_feedback(
                context_for("session-a"),
                question_number=question_number,
                confidence_score=overall,
                clarity_score=overall,
                body_language_score=overall,
                content_score=overall,
                star_score=overall,
                feedback_summary="Great",
                strengths="Strong",
                improvements="None",
            )
            tools.engagement_tracking(context_for("session-a"), question_number, 88, 0, True, "energetic")
            tools.emotion_recognition(
                context_for("session-a"), question_number, "confident", "calm", "excellent", ""
            )

        result = tools.adjust_difficulty_level(context_for("session-a"), "improving")
        self.assertEqual(result["new_difficulty"], "hard")
        # The decision must stick, otherwise the next question ignores it.
        self.assertEqual(tools._get_session_state("session-a")["context"]["difficulty"], "hard")

    def test_questions_are_not_repeated_within_a_session(self):
        tools.seed_session_context("session-a", role="general", difficulty="medium")
        seen = set()
        for _ in range(8):
            question = tools.get_interview_question(context_for("session-a"))
            self.assertNotIn(question["question"], seen)
            seen.add(question["question"])

    def test_question_uses_session_context_not_model_arguments(self):
        tools.seed_session_context(
            "session-a", role="data_scientist", company_style="meta", difficulty="hard"
        )
        question = tools.get_interview_question(context_for("session-a"))
        self.assertEqual(question["role"], "data_scientist")
        self.assertEqual(question["company_style"], "meta")
        self.assertEqual(question["difficulty"], "hard")

    def test_grounding_data_contains_expanded_company_styles(self):
        companies = GROUNDING_KNOWLEDGE["company_interview_styles"]
        self.assertIn("google", companies)
        self.assertIn("amazon", companies)
        self.assertIn("stripe", companies)


class MemoryBoundTests(unittest.TestCase):
    def setUp(self):
        tools._sessions.clear()

    def test_idle_sessions_are_evicted(self):
        tools.record_candidate_speech("old-session", "hello")
        self.assertIn("old-session", tools._sessions)

        # Age the session past its TTL and touch the store.
        tools._sessions["old-session"]["last_touched"] -= tools._SESSION_TTL_SECONDS + 10
        tools._get_session_state("new-session")

        self.assertNotIn("old-session", tools._sessions)

    def test_session_count_is_capped(self):
        with patch.object(tools, "_MAX_SESSIONS", 10):
            for index in range(25):
                tools._get_session_state(f"session-{index}")
        self.assertLessEqual(len(tools._sessions), 11)

    def test_clear_session_releases_state(self):
        tools.record_candidate_speech("session-a", "hello")
        tools.clear_session("session-a")
        self.assertNotIn("session-a", tools._sessions)


class RuntimeConfigTests(unittest.TestCase):
    def test_default_model_prefers_vertex_native_audio(self):
        with patch.dict(os.environ, {"GOOGLE_GENAI_USE_VERTEXAI": "true"}, clear=False):
            os.environ.pop("AGENT_MODEL", None)
            self.assertEqual(get_default_agent_model(), "gemini-live-2.5-flash-native-audio")

    def test_model_profile_distinguishes_audio_and_text_modes(self):
        audio_profile = get_model_profile("gemini-2.5-flash-native-audio-preview-12-2025")
        text_profile = get_model_profile("gemini-2.0-flash-exp")

        self.assertTrue(audio_profile.supports_audio_output)
        self.assertFalse(text_profile.supports_audio_output)

    def test_unknown_inputs_fall_back_to_safe_defaults(self):
        """An unvalidated voice makes the Live API close the socket with a 1007."""

        self.assertEqual(normalize_voice("Kore"), "Kore")
        self.assertEqual(normalize_voice("../../etc/passwd"), "Kore")
        self.assertEqual(normalize_voice(None), "Kore")
        self.assertEqual(normalize_role("bogus"), "general")
        self.assertEqual(normalize_company("bogus"), "general")
        self.assertEqual(normalize_difficulty("impossible"), "medium")


class AgentWiringTests(unittest.TestCase):
    def test_every_stateful_tool_takes_a_tool_context(self):
        """Any stateful tool missing tool_context would take session_id from the model."""

        exempt = {"get_improvement_tips", "fetch_grounding_data"}
        for tool in tools.AGENT_TOOLS:
            if tool.__name__ in exempt:
                continue
            params = list(inspect.signature(tool).parameters)
            self.assertEqual(
                params[0], "tool_context", f"{tool.__name__} must accept tool_context first"
            )
            self.assertNotIn(
                "session_id", params, f"{tool.__name__} must not accept a model-supplied session_id"
            )

    def test_agent_tool_list_is_complete(self):
        tool_names = {tool.__name__ for tool in tools.AGENT_TOOLS}
        for expected in (
            "get_interview_question",
            "save_session_feedback",
            "cross_modal_analysis",
            "emotion_recognition",
            "engagement_tracking",
            "generate_session_report",
        ):
            self.assertIn(expected, tool_names)


if __name__ == "__main__":
    unittest.main()
