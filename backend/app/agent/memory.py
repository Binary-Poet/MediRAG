"""多轮会话记忆：内存 dict（方案 REDIS_MODE=memory；Redis 为 P1）。"""
import uuid

_sessions: dict[str, list[dict]] = {}
_HISTORY_CAP = 8
MAX_SESSIONS = 1000


def new_session() -> str:
    sid = uuid.uuid4().hex
    _sessions[sid] = []
    return sid


def get_history(session_id: str) -> list[dict]:
    return list(_sessions.get(session_id, []))


def upsert_message(session_id: str, role: str, content: str) -> list[dict]:
    if session_id not in _sessions and len(_sessions) >= MAX_SESSIONS:
        _sessions.pop(next(iter(_sessions)))  # 逐出最旧（dict 插入序）
    msgs = _sessions.setdefault(session_id, [])
    msgs.append({"role": role, "content": content})
    if len(msgs) > _HISTORY_CAP:
        _sessions[session_id] = msgs[-_HISTORY_CAP:]
    return list(_sessions[session_id])
