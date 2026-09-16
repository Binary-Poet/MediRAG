"""问答完成写 retrieval_log；feedback API 落库。"""
import pytest
from sqlalchemy import func, select

import app.api.chat as chatmod
import app.db as dbmod
from app.db import session_scope
from app.models.retrieval_log import RetrievalLog
from app.models.feedback import Feedback


@pytest.fixture(autouse=True)
def _db(monkeypatch):
    eng = dbmod._make_engine("sqlite:///:memory:")
    dbmod.Base.metadata.create_all(eng)
    monkeypatch.setattr(dbmod, "_engine", eng)


def test_chat_stream_writes_retrieval_log(client, monkeypatch):
    fake = {"intent": "relation", "plan": ["vector_search"], "vector_hits": [],
            "keyword_hits": [], "graph_facts": [], "fused": [], "evidence": [
                {"chunk_id": "c1", "title": "t", "doc_name": "d", "chapter": "",
                 "page_no": 1, "text": "x", "score": 0.9}],
            "confidence": 0.9, "low_confidence": False, "safety_flag": None,
            "safety_message": "", "prompt": "p", "answer": "a", "trace": [],
            "rewritten_query": "q", "entities": [], "entity_names": [], "reflect_count": 0,
            "session_id": "sess-1", "question": "问", "chat_history": []}
    class FakeGraph:
        def __init__(self):
            self.initial = None
        def stream(self, initial, stream_mode=None):
            self.initial = initial
            yield {"understand": {"trace": [], "intent": fake["intent"]}}
            yield {"context": {"prompt": "p"}}
            yield {"safety": {"safety_flag": None, "safety_message": ""}}
            yield {"fuse": {"evidence": fake["evidence"], "confidence": 0.9,
                            "low_confidence": False,
                            "trace": [{"step": "rerank"}]}}
    g = FakeGraph()
    monkeypatch.setattr(chatmod, "get_agent", lambda: g)
    monkeypatch.setattr("app.api.chat.chat_completion_stream",
                        lambda system, user, temperature=0.3, vendor=None, model=None: iter(["流"]))
    r = client.post("/api/chat/stream",
                    json={"question": "四君子汤由哪些中药组成？", "session_id": "sess-1"})
    assert r.status_code == 200
    with session_scope() as s:
        log = s.execute(select(RetrievalLog)).scalar_one()
        assert log.session_id == "sess-1" and log.intent == "relation"
        assert log.evidence_n == 1
        assert log.is_fallback is False
    # 初始 state 已注入推理配置（保存即生效）
    assert g.initial["inference"]["semantic_k"] == 20   # 默认值注入
    assert g.initial["inference"]["model"] == "deepseek-chat"


def test_fallback_marks_is_fallback(client, monkeypatch):
    class FakeGraph:
        def stream(self, initial, stream_mode=None):
            yield {"understand": {"trace": []}}
            yield {"context": {"prompt": "p"}}
            yield {"safety": {"safety_flag": "low_confidence",
                              "safety_message": "知识库中未检索到可靠依据",
                              "answer": "知识库中未检索到可靠依据"}}
    monkeypatch.setattr(chatmod, "get_agent", lambda: FakeGraph())
    r = client.post("/api/chat/stream", json={"question": "今天北京天气", "session_id": "sess-2"})
    assert r.status_code == 200
    with session_scope() as s:
        log = s.execute(select(RetrievalLog)).scalar_one()
        assert log.session_id == "sess-2"
        assert log.is_fallback is True


def test_feedback_api(client):
    r = client.post("/api/feedback", json={"session_id": "sess-1", "useful": True})
    assert r.status_code == 200
    r = client.post("/api/feedback", json={"session_id": "sess-1", "useful": False})
    assert r.status_code == 200
    with session_scope() as s:
        rows = s.execute(select(Feedback)).scalars().all()
        assert len(rows) == 2
        assert [x.useful for x in rows] == [True, False]
    # 越界 422
    assert client.post("/api/feedback", json={"session_id": "sess-1", "useful": 2}).status_code == 422