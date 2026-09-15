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
