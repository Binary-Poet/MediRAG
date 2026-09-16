"""多轮会话记忆读库（原进程内 dict 实现已由 chat_message 表取代）。

原 test_sessions_evict_oldest_beyond_max 随 MAX_SESSIONS 逐出逻辑一并删除：
会话数上界由「按用户列举」取代，隔离性改由 test_chat_sessions_service.py 的
test_ownership_isolation 覆盖。
"""
import pytest

import app.db as dbmod
from app.agent.memory import get_history
from app.services import chat_session as cs


@pytest.fixture(autouse=True)
def _db(monkeypatch):
    eng = dbmod._make_engine("sqlite:///:memory:")
    dbmod.init_db(eng)
    monkeypatch.setattr(dbmod, "_engine", eng)


def test_session_roundtrip():
    sid = cs.create_session(1, "四君子汤组成")
    cs.append_message(sid, "user", "四君子汤组成")
    cs.append_message(sid, "assistant", "人参白术茯苓炙甘草")
    h = get_history(sid)
    assert h[0]["role"] == "user"
    assert h[1]["content"] == "人参白术茯苓炙甘草"


def test_history_capped_at_8():
    sid = cs.create_session(1, "问")
    for i in range(12):
        cs.append_message(sid, "user", f"q{i}")
    assert len(get_history(sid)) == 8
    assert get_history(sid)[-1]["content"] == "q11"


def test_unknown_session_returns_empty():
    assert get_history("no-such-session") == []
