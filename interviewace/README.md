# InterviewAce — application package

Full project documentation lives in the [repository README](../README.md).
Design details are in [ARCHITECTURE.md](ARCHITECTURE.md); operational and security
guidance is in [SECURITY.md](../SECURITY.md).

## Quick start

```bash
python -m venv venv
source venv/bin/activate          # Windows: .\venv\Scripts\activate
pip install -r requirements.txt

cp .env.example .env              # add your GOOGLE_API_KEY

uvicorn app.main:app --reload --port 8080
```

Open http://localhost:8080 and grant camera and microphone permission.

Run from this directory using `app.main:app`. That is the canonical import path — starting
from inside `app/` makes `app` resolve as a namespace package and can load modules twice
with separate copies of session state.

## Tests

```bash
pytest -q          # 38 tests; ADK is stubbed, so no API key is needed
ruff check .
```

The suite covers session isolation, filler-word measurement, memory bounds, input
validation, token auth, rate limiting, and the WebSocket bridge. It does **not** exercise
the real Gemini Live API — verify that manually against a live key before deploying.

## Layout

| Path | Role |
|------|------|
| `app/main.py` | FastAPI app, WebSocket bridge, session tokens, rate limits |
| `app/runtime_config.py` | Model profiles, input allowlists, limits, secrets |
| `app/ws_manager.py` | Strict session-to-socket routing for tool results |
| `app/interview_coach_agent/agent.py` | ADK agent and the `google_search` sub-agent |
| `app/interview_coach_agent/tools.py` | 15 coaching tools, all `ToolContext`-bound |
| `app/interview_coach_agent/prompts.py` | Coach Ace persona and tool-use rules |
| `app/interview_coach_agent/grounding_data.py` | Question bank and coaching knowledge base |
| `app/static/` | Vanilla JS client |
| `deploy/` | `deploy.sh` and Terraform for Cloud Run |

## Deployment

See [Deploy to Cloud Run](../README.md#️-deploy-to-cloud-run). Secrets are read from Secret
Manager; do not pass `GOOGLE_API_KEY` with `--set-env-vars`.

## Known limitations

- **State is in-process.** Session analytics are held in memory with a one-hour idle TTL,
  and an instance restart drops in-flight sessions. Cloud Run session affinity keeps
  analytics reads on the owning instance.
- **Scores are model judgements.** Only filler words, timings, and counts are measured;
  confidence, clarity, content, STAR, body language, voice, and engagement are the model's
  assessment applied through a fixed rubric.
- **Live API behaviour is not covered by tests.** The suite stubs the ADK.
