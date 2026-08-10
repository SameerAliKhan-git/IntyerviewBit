"""Registry mapping a session to its live WebSocket.

Tools run synchronously inside the ADK executor, off the event loop that owns the
socket, so pushing a UI update has to be scheduled back onto the owning loop.

Routing is strict: a payload for an unknown session is dropped. An earlier version
fell back to "the first active socket", which delivered one candidate's scores into
another candidate's browser as soon as two people used the app at once.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from fastapi import WebSocket

logger = logging.getLogger(__name__)

# session_id -> (WebSocket, owning event loop)
_active_websockets: dict[str, tuple[WebSocket, asyncio.AbstractEventLoop]] = {}


def register_ws(session_id: str, ws: WebSocket) -> None:
    loop = asyncio.get_running_loop()
    _active_websockets[session_id] = (ws, loop)


def unregister_ws(session_id: str, ws: WebSocket | None = None) -> None:
    """Removes a session's socket.

    When ``ws`` is supplied the entry is only removed if it still refers to that exact
    socket, so a superseded connection tearing down late cannot unregister the
    connection that replaced it.
    """

    existing = _active_websockets.get(session_id)
    if existing is None:
        return
    if ws is not None and existing[0] is not ws:
        return
    _active_websockets.pop(session_id, None)


def is_registered(session_id: str) -> bool:
    return session_id in _active_websockets


def active_session_count() -> int:
    return len(_active_websockets)


def send_tool_result_sync(session_id: str, tool_name: str, response_data: dict[str, Any]) -> None:
    """Pushes a tool result to the browser that owns ``session_id``."""

    entry = _active_websockets.get(session_id)
    if entry is None:
        logger.debug("Dropping %s result for inactive session %s", tool_name, session_id)
        return

    ws, loop = entry
    payload = json.dumps(
        {"customToolResponse": {"name": tool_name, "response": response_data}}
    )

    async def _send() -> None:
        try:
            await ws.send_text(payload)
        except Exception as exc:  # pragma: no cover - socket may close mid-send
            logger.debug("Unable to push %s to session %s: %s", tool_name, session_id, exc)

    if loop.is_closed():
        return
    try:
        asyncio.run_coroutine_threadsafe(_send(), loop)
    except RuntimeError as exc:  # pragma: no cover - loop shutting down
        logger.debug("Event loop unavailable for session %s: %s", session_id, exc)
