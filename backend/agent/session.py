"""In-memory conversation session store. Each session holds message history."""

import time
from typing import List, Dict

_sessions: Dict[str, dict] = {}
SESSION_TTL = 3600  # seconds


def get_history(session_id: str) -> List[dict]:
    if session_id not in _sessions:
        return []
    _sessions[session_id]["last_active"] = time.time()
    return list(_sessions[session_id]["history"])


def save_history(session_id: str, history: List[dict]):
    _sessions[session_id] = {"history": history[-40:], "last_active": time.time()}


def clear(session_id: str):
    _sessions.pop(session_id, None)


def purge_expired():
    now = time.time()
    expired = [sid for sid, d in _sessions.items() if now - d["last_active"] > SESSION_TTL]
    for sid in expired:
        del _sessions[sid]
