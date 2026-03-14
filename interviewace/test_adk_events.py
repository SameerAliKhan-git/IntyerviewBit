"""Print full raw JSON of first 15 ADK events to understand the structure."""
import asyncio
import json
import os
import pathlib
import sys

from dotenv import load_dotenv
load_dotenv(pathlib.Path('app/.env'))

sys.path.insert(0, 'app')

from google.adk.agents import Agent
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.adk.agents.live_request_queue import LiveRequestQueue
from google.adk.agents.run_config import RunConfig, StreamingMode
from google.genai import types

agent = Agent(
    name='test',
    model='gemini-2.5-flash-native-audio-preview-12-2025',
    instruction='Say hello.',
    tools=[]
)

session_service = InMemorySessionService()
runner = Runner(app_name='test', agent=agent, session_service=session_service)

async def test_adk():
    await session_service.create_session(app_name='test', user_id='u1', session_id='s1')
    q = LiveRequestQueue()
    run_config = RunConfig(
        streaming_mode=StreamingMode.BIDI,
        response_modalities=['AUDIO'],
        input_audio_transcription=types.AudioTranscriptionConfig(),
        output_audio_transcription=types.AudioTranscriptionConfig(),
        speech_config=types.SpeechConfig(
            voice_config=types.VoiceConfig(
                prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name='Kore')
            )
        )
    )

    content = types.Content(parts=[types.Part(text='Hello')])
    q.send_content(content)

    event_count = 0
    async for event in runner.run_live(
        user_id='u1', session_id='s1',
        live_request_queue=q, run_config=run_config
    ):
        event_json = event.model_dump_json(exclude_none=True, by_alias=True)
        parsed = json.loads(event_json)

        # Print sanitized (truncate audio data)
        sanitized = {}
        for k, v in parsed.items():
            if k == 'content' and isinstance(v, dict):
                parts_copy = []
                for p in v.get('parts', []):
                    p2 = dict(p)
                    if 'inlineData' in p2:
                        p2['inlineData'] = {'mimeType': p2['inlineData'].get('mimeType', '?'), 'data': f'<{len(p2["inlineData"].get("data",""))} chars>'}
                    parts_copy.append(p2)
                sanitized[k] = {'role': v.get('role'), 'parts': parts_copy}
            else:
                sanitized[k] = v

        print(f'\n=== EVENT {event_count} ===')
        print(json.dumps(sanitized, indent=2)[:2000])

        event_count += 1
        if event_count >= 12:
            q.close()
            print('\n--- Done ---')
            break

asyncio.run(test_adk())
