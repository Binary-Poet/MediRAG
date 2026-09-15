from app.agent.memory import get_history, new_session, upsert_message


def test_session_roundtrip():
    sid = new_session()
    upsert_message(sid, "user", "四君子汤组成")
    upsert_message(sid, "assistant", "人参白术茯苓炙甘草")
    h = get_history(sid)
    assert h[0]["role"] == "user"
    assert h[1]["content"] == "人参白术茯苓炙甘草"


def test_history_capped_at_8():
    sid = new_session()
    for i in range(12):
        upsert_message(sid, "user", f"q{i}")
    assert len(get_history(sid)) == 8
    assert get_history(sid)[-1]["content"] == "q11"


def test_unknown_session_returns_empty():
    assert get_history("no-such-session") == []


def test_sessions_evict_oldest_beyond_max(monkeypatch):
    """会话数上界：超过 MAX_SESSIONS 时逐出最旧（dict 插入序）。"""
    import app.agent.memory as memory
    monkeypatch.setattr(memory, "MAX_SESSIONS", 3)
    monkeypatch.setattr(memory, "_sessions", {})
    for i in range(4):
        memory.upsert_message(f"s{i}", "user", f"q{i}")
    assert len(memory._sessions) == 3
    assert "s0" not in memory._sessions   # 最旧被逐出
    assert "s3" in memory._sessions
