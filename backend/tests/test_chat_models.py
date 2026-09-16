"""会话持久化模型：建表 + JSON payload 往返（MySQL 原生 JSON 与 sqlite 均须可用）。"""
import pytest

import app.db as dbmod
from app.db import session_scope
from app.models.chat import ChatMessage, ChatSession


@pytest.fixture(autouse=True)
def _db(monkeypatch):
    eng = dbmod._make_engine("sqlite:///:memory:")
    dbmod.init_db(eng)
    monkeypatch.setattr(dbmod, "_engine", eng)


def test_session_and_message_roundtrip():
    with session_scope() as s:
        s.add(ChatSession(id="s1", user_id=1, title="四君子汤由哪些中药组成？"))
        s.add(ChatMessage(session_id="s1", seq=1, role="user", content="四君子汤由哪些中药组成？"))
        s.add(ChatMessage(session_id="s1", seq=2, role="assistant", content="人参、白术、茯苓、炙甘草",
                          payload={"trace": [{"step": "understand"}], "references": [],
                                   "graph_facts": [{"source": "四君子汤", "relation": "组成",
                                                    "target": "人参"}],
                                   "safety": None}))
    with session_scope() as s:
        row = s.get(ChatSession, "s1")
        assert row.user_id == 1
        assert row.favorite is False
        msgs = s.query(ChatMessage).filter_by(session_id="s1").order_by(ChatMessage.seq).all()
    assert [m.role for m in msgs] == ["user", "assistant"]
    assert msgs[1].payload["graph_facts"][0]["target"] == "人参"
    assert msgs[0].payload is None
