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


class FakeEvent:
    def __init__(self, payload):
        self.payload = payload

    def model_dump_json(self, **_kwargs):
        return json.dumps(self.payload)


class FakeAgent:
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)


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

    async def create_session(self, app_name, user_id, session_id):
        self._sessions[(app_name, user_id, session_id)] = {"session_id": session_id}
        return self._sessions[(app_name, user_id, session_id)]


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
    fake_live_request_queue = types.ModuleType("google.adk.agents.live_request_queue")
    fake_run_config = types.ModuleType("google.adk.agents.run_config")
    fake_runners = types.ModuleType("google.adk.runners")
    fake_sessions = types.ModuleType("google.adk.sessions")
    fake_genai = types.ModuleType("google.genai")
    fake_types = types.ModuleType("google.genai.types")

    fake_agents.Agent = FakeAgent
    fake_tools.google_search = types.SimpleNamespace(__name__="google_search")
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
        self.main.get_session_history("integration-session")

    def test_health_and_analytics_endpoints(self):
        self.main.get_session_dashboard("integration-session")
        with TestClient(self.main.app) as client:
            health = client.get("/health")
            analytics = client.get("/api/sessions/integration-session/analytics")

        self.assertEqual(health.status_code, 200)
        self.assertIn("mode", health.json())
        self.assertEqual(analytics.status_code, 200)
        self.assertIn("trend_points", analytics.json())

    def test_websocket_streams_runner_events(self):
        FakeRunner.next_events = [FakeEvent({"content": {"parts": [{"text": "Interview question"}]}})]

        with TestClient(self.main.app) as client:
            with client.websocket_connect("/ws/u1/s1?voice=Kore") as websocket:
                websocket.send_text(json.dumps({"type": "text", "text": "hello"}))
                payload = json.loads(websocket.receive_text())

        self.assertEqual(payload["content"]["parts"][0]["text"], "Interview question")


if __name__ == "__main__":
    unittest.main()
