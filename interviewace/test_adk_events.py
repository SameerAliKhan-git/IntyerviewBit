"""Integration tests for the FastAPI app and WebSocket bridge."""

from __future__ import annotations

import importlib
import json
import sys
import types
import unittest
from unittest import mock

try:
    from fastapi.testclient import TestClient
except Exception:  # pragma: no cover - dependency may be absent in thin envs
    TestClient = None

try:
    from starlette.websockets import WebSocketDisconnect
except Exception:  # pragma: no cover
    WebSocketDisconnect = Exception


class FakeEvent:
    def __init__(self, payload):
        self.payload = payload
        self.input_transcription = None

    def model_dump_json(self, **_kwargs):
        return json.dumps(self.payload)


class FakeTranscription:
    def __init__(self, text):
        self.text = text


class FakeAgent:
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)


class FakeAgentTool:
    def __init__(self, agent=None):
        self.agent = agent
        self.__name__ = "interview_research"


class FakeToolContext:
    state: dict


class FakeBlob:
    def __init__(self, mime_type=None, data=None):
        self.mime_type = mime_type
        self.data = data


class FakePart:
    def __init__(self, text=None):
        self.text = text


class FakeContent:
    def __init__(self, parts=None):
        self.parts = parts or []


class FakeAudioTranscriptionConfig:
    pass


class FakeSessionResumptionConfig:
    pass


class FakePrebuiltVoiceConfig:
    def __init__(self, voice_name=None):
        self.voice_name = voice_name


class FakeVoiceConfig:
    def __init__(self, prebuilt_voice_config=None):
        self.prebuilt_voice_config = prebuilt_voice_config


class FakeSpeechConfig:
    def __init__(self, voice_config=None):
        self.voice_config = voice_config


class FakeRunConfig:
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)


class FakeLiveRequestQueue:
    def __init__(self):
        self.items = []
        self.closed = False

    def send_realtime(self, item):
        self.items.append(("realtime", item))

    def send_content(self, item):
        self.items.append(("content", item))

    def close(self):
        self.closed = True


class FakeSessionService:
    def __init__(self):
        self._sessions = {}

    async def get_session(self, app_name, user_id, session_id):
        return self._sessions.get((app_name, user_id, session_id))

    async def create_session(self, app_name, user_id, session_id, state=None):
        record = {"session_id": session_id, "state": state or {}}
        self._sessions[(app_name, user_id, session_id)] = record
        return record


class FakeRunner:
    next_events = [FakeEvent({"content": {"parts": [{"text": "Hello from fake runner"}]}})]

    def __init__(self, app_name=None, agent=None, session_service=None):
        self.app_name = app_name
        self.agent = agent
        self.session_service = session_service

    async def run_live(self, **_kwargs):
        for event in list(self.next_events):
            yield event


def load_main_module():
    fake_google = types.ModuleType("google")
    fake_adk = types.ModuleType("google.adk")
    fake_agents = types.ModuleType("google.adk.agents")
    fake_tools = types.ModuleType("google.adk.tools")
    fake_agent_tool = types.ModuleType("google.adk.tools.agent_tool")
    fake_live_request_queue = types.ModuleType("google.adk.agents.live_request_queue")
    fake_run_config = types.ModuleType("google.adk.agents.run_config")
    fake_runners = types.ModuleType("google.adk.runners")
    fake_sessions = types.ModuleType("google.adk.sessions")
    fake_genai = types.ModuleType("google.genai")
    fake_types = types.ModuleType("google.genai.types")

    fake_agents.Agent = FakeAgent
    fake_tools.google_search = types.SimpleNamespace(__name__="google_search")
    fake_tools.ToolContext = FakeToolContext
    fake_agent_tool.AgentTool = FakeAgentTool
    fake_live_request_queue.LiveRequestQueue = FakeLiveRequestQueue
    fake_run_config.RunConfig = FakeRunConfig
    fake_run_config.StreamingMode = types.SimpleNamespace(BIDI="BIDI")
    fake_runners.Runner = FakeRunner
    fake_sessions.InMemorySessionService = FakeSessionService

    fake_types.Blob = FakeBlob
    fake_types.Content = FakeContent
    fake_types.Part = FakePart
    fake_types.AudioTranscriptionConfig = FakeAudioTranscriptionConfig
    fake_types.SessionResumptionConfig = FakeSessionResumptionConfig
    fake_types.SpeechConfig = FakeSpeechConfig
    fake_types.VoiceConfig = FakeVoiceConfig
    fake_types.PrebuiltVoiceConfig = FakePrebuiltVoiceConfig
    fake_genai.types = fake_types

    for module_name in ("app.main", "app.interview_coach_agent.agent"):
        sys.modules.pop(module_name, None)

    with mock.patch.dict(
        sys.modules,
        {
            "google": fake_google,
            "google.adk": fake_adk,
            "google.adk.agents": fake_agents,
            "google.adk.tools": fake_tools,
            "google.adk.tools.agent_tool": fake_agent_tool,
            "google.adk.agents.live_request_queue": fake_live_request_queue,
            "google.adk.agents.run_config": fake_run_config,
            "google.adk.runners": fake_runners,
            "google.adk.sessions": fake_sessions,
            "google.genai": fake_genai,
            "google.genai.types": fake_types,
        },
        clear=False,
    ):
        import app.main as main_module

        return importlib.reload(main_module)


@unittest.skipIf(TestClient is None, "fastapi TestClient is unavailable in this environment")
class AppIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.main = load_main_module()
        self.main._session_starts_by_ip.clear()
        self.main._active_sessions_by_ip.clear()
        self.main._intro_sent.clear()

    def _ticket(self, client):
        response = client.post("/api/session")
        self.assertEqual(response.status_code, 200)
        return response.json()

    # -- HTTP surface -------------------------------------------------------------

    def test_health_reports_model_mode(self):
        with TestClient(self.main.app) as client:
            health = client.get("/health")
        self.assertEqual(health.status_code, 200)
        self.assertIn("mode", health.json())

    def test_security_headers_are_present(self):
        with TestClient(self.main.app) as client:
            response = client.get("/health")

        csp = response.headers["content-security-policy"]
        self.assertIn("script-src 'self'", csp)
        self.assertIn("frame-ancestors 'none'", csp)
        self.assertEqual(response.headers["x-content-type-options"], "nosniff")
        self.assertEqual(response.headers["x-frame-options"], "DENY")

    def test_debug_endpoint_is_disabled_by_default(self):
        with TestClient(self.main.app) as client:
            self.assertEqual(client.get("/debug").status_code, 404)

    def test_debug_endpoint_never_leaks_key_material(self):
        with mock.patch.object(self.main, "debug_endpoint_enabled", return_value=True):
            with TestClient(self.main.app) as client:
                body = client.get("/debug").json()

        self.assertIn("api_key_configured", body)
        self.assertNotIn("api_key_prefix", body)
        self.assertNotIn("api_key_length", body)

    # -- Session tokens -----------------------------------------------------------

    def test_session_ticket_is_server_generated(self):
        with TestClient(self.main.app) as client:
            ticket = self._ticket(client)

        # Long enough that ids cannot be guessed or enumerated.
        self.assertGreaterEqual(len(ticket["session_id"]), 24)
        self.assertIn(".", ticket["token"])

    def test_analytics_requires_a_valid_token(self):
        with TestClient(self.main.app) as client:
            ticket = self._ticket(client)
            session_id = ticket["session_id"]

            no_token = client.get(f"/api/sessions/{session_id}/analytics")
            bad_token = client.get(f"/api/sessions/{session_id}/analytics?token=1700000000.deadbeef")
            good = client.get(
                f"/api/sessions/{session_id}/analytics?token={ticket['token']}"
            )

        self.assertEqual(no_token.status_code, 403)
        self.assertEqual(bad_token.status_code, 403)
        self.assertEqual(good.status_code, 200)
        self.assertIn("trend_points", good.json())

    def test_token_for_one_session_does_not_unlock_another(self):
        with TestClient(self.main.app) as client:
            first = self._ticket(client)
            second = self._ticket(client)
            response = client.get(
                f"/api/sessions/{second['session_id']}/analytics?token={first['token']}"
            )
        self.assertEqual(response.status_code, 403)

    def test_report_endpoint_is_deterministic(self):
        """Ending a call must not depend on the model calling a tool in time."""

        with TestClient(self.main.app) as client:
            ticket = self._ticket(client)
            response = client.post(
                f"/api/sessions/{ticket['session_id']}/report?token={ticket['token']}"
            )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertIn("performance_tier", body)
        self.assertIn("recommendations", body)

    # -- Rate limiting ------------------------------------------------------------

    def test_new_sessions_are_rate_limited_per_ip(self):
        limit = self.main.LIMITS.new_sessions_per_ip_per_hour
        with TestClient(self.main.app) as client:
            statuses = [client.post("/api/session").status_code for _ in range(limit + 2)]

        self.assertEqual(statuses[0], 200)
        self.assertEqual(statuses[-1], 429)

    def test_live_errors_are_classified_for_retry_decisions(self):
        """Retrying into an exhausted quota just loops; the client needs to know."""

        classify = self.main.classify_live_error

        self.assertEqual(classify("429 RESOURCE_EXHAUSTED: quota exceeded"), "quota")
        self.assertEqual(classify("Rate limit reached for model"), "quota")
        self.assertEqual(classify("403 PERMISSION_DENIED: API key not valid"), "auth")
        self.assertEqual(classify("received 1007 (invalid frame payload data)"), "protocol")
        self.assertEqual(classify("connection reset by peer"), "transient")

    def test_guardrail_bookkeeping_is_pruned(self):
        """Per-IP and per-session records must not accumulate for the process lifetime."""

        with TestClient(self.main.app) as client:
            self._ticket(client)

        self.assertTrue(self.main._session_starts_by_ip)

        # Age every record past its retention window, then trigger a prune.
        window = self.main._RATE_WINDOW_SECONDS
        for entries in self.main._session_starts_by_ip.values():
            for index, value in enumerate(entries):
                entries[index] = value - window - 10
        self.main._intro_sent["stale-session"] = (
            self.main.time.monotonic() - self.main.LIMITS.max_session_seconds * 2 - 10
        )

        self.main._prune_guardrail_state()

        self.assertEqual(self.main._session_starts_by_ip, {})
        self.assertNotIn("stale-session", self.main._intro_sent)

    # -- WebSocket ----------------------------------------------------------------

    def test_websocket_rejects_an_unsigned_session(self):
        with TestClient(self.main.app) as client:
            with self.assertRaises(WebSocketDisconnect):
                with client.websocket_connect("/ws/forged-session?token=nope") as websocket:
                    websocket.receive_text()

    def test_websocket_streams_runner_events(self):
        FakeRunner.next_events = [FakeEvent({"content": {"parts": [{"text": "Interview question"}]}})]

        with TestClient(self.main.app) as client:
            ticket = self._ticket(client)
            url = f"/ws/{ticket['session_id']}?token={ticket['token']}&voice=Kore"
            with client.websocket_connect(url) as websocket:
                messages = [json.loads(websocket.receive_text()) for _ in range(2)]

        types_seen = {msg.get("type") for msg in messages}
        self.assertIn("live_ready", types_seen)
        content = [msg for msg in messages if msg.get("content")]
        self.assertEqual(content[0]["content"]["parts"][0]["text"], "Interview question")

    def test_websocket_normalizes_an_unknown_voice(self):
        captured = {}
        original = self.main.build_run_config

        def spy(voice):
            captured["voice"] = voice
            return original(voice)

        with mock.patch.object(self.main, "build_run_config", spy):
            with TestClient(self.main.app) as client:
                ticket = self._ticket(client)
                url = f"/ws/{ticket['session_id']}?token={ticket['token']}&voice=NotARealVoice"
                with client.websocket_connect(url) as websocket:
                    websocket.receive_text()

        self.assertEqual(captured["voice"], "Kore")

    def test_intro_is_sent_once_per_session(self):
        """A reconnect must not restart the interview with a second greeting."""

        with TestClient(self.main.app) as client:
            ticket = self._ticket(client)
            url = f"/ws/{ticket['session_id']}?token={ticket['token']}"

            for _ in range(2):
                with client.websocket_connect(url) as websocket:
                    websocket.receive_text()

        self.assertEqual(len(self.main._intro_sent), 1)
        self.assertIn(ticket["session_id"], self.main._intro_sent)

    def test_input_transcription_is_recorded_for_filler_analysis(self):
        FakeRunner.next_events = [FakeEvent({"turnComplete": True})]
        FakeRunner.next_events[0].input_transcription = FakeTranscription(
            "Um, so basically I led it."
        )

        with TestClient(self.main.app) as client:
            ticket = self._ticket(client)
            url = f"/ws/{ticket['session_id']}?token={ticket['token']}"
            with client.websocket_connect(url) as websocket:
                websocket.receive_text()
                websocket.receive_text()

        # Read state through the exact module instance the app is bound to. Importing
        # `app.interview_coach_agent.tools` afresh here can resolve to a second copy with
        # its own state, because mock.patch.dict restores sys.modules when
        # load_main_module returns. The function's globals are that module's namespace.
        tools_namespace = self.main.record_candidate_speech.__globals__

        transcript = tools_namespace["get_full_transcript"](ticket["session_id"])
        self.assertTrue(any("basically" in chunk for chunk in transcript))

        FakeRunner.next_events = [
            FakeEvent({"content": {"parts": [{"text": "Hello from fake runner"}]}})
        ]


if __name__ == "__main__":
    unittest.main()
