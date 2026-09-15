from unittest.mock import MagicMock

import app.api.chat as chatmod
from app.agent.memory import get_history, upsert_message


def _patch_agent(client, monkeypatch, *, safety="ok", answer=None, safety_message=""):
    """monkeypatch get_agent 返回一个假编译图：invoke/stream 返回统一 final state。"""
    final = {
        "question": "四君子汤由哪些中药组成？", "session_id": "", "chat_history": [],
        "rewritten_query": "四君子汤组成", "entities": [], "entity_names": ["四君子汤"],
        "intent": "relation", "plan": ["vector_search", "graph_search"],
        "vector_hits": [], "keyword_hits": [], "graph_facts": [
            {"source": "四君子汤", "relation": "组成", "target": "人参", "source_type": "方剂", "target_type": "中药"}],
        "fused": [], "evidence": [{"chunk_id": "a", "title": "四君子汤", "doc_name": "中药方剂学基础",
                                   "chapter": "第1节", "page_no": 1, "text": "组成", "score": 0.9}],
        "confidence": 0.9, "low_confidence": False, "reflect_count": 0,
        "safety_flag": safety, "safety_message": safety_message, "prompt": "P",
        "answer": answer or "", "trace": [
            {"step": "understand", "rewritten": "四君子汤组成"},
            {"step": "retrieve", "vector_n": 1, "graph_n": 1},
            {"step": "rerank", "evidence_n": 1, "confidence": 0.9, "status": "证据充分，正常生成"}],
    }
    fake_graph = MagicMock()
    fake_graph.stream.return_value = [  # (node_name, update_dict) 对，与 stream_mode="updates" 一致
        ("understand", {"rewritten_query": "四君子汤组成", "trace": [{"step": "understand"}]}),
        ("retrieve", {"vector_hits": [], "graph_facts": final["graph_facts"], "trace": [{"step": "retrieve", "vector_n": 0, "graph_n": 1}]}),
        ("fuse", {"evidence": final["evidence"], "confidence": 0.9,
                   "trace": [{"step": "fuse", "candidate_n": 1}, {"step": "rerank", "evidence_n": 1, "confidence": 0.9, "status": "证据充分，正常生成"}]}),
        ("safety", {"safety_flag": safety}),
        ("context", {"prompt": "P"}),
    ]
    monkeypatch.setattr(chatmod, "get_agent", lambda: fake_graph)
    monkeypatch.setattr(chatmod, "chat_completion_stream", lambda system, user, temperature=0.3: iter(["四君子汤由人参、白术、茯苓、炙甘草组成 [1]"]))
    return fake_graph


def test_stream_emits_expected_events(client, monkeypatch):
    fake = _patch_agent(client, monkeypatch)
    with client.stream("POST", "/api/chat/stream", json={"question": "四君子汤由哪些中药组成？"}) as resp:
        assert resp.status_code == 200
        raw = "".join(resp.iter_text())
    # 事件顺序：step...、token、references、safety、done
    assert "event: step" in raw
    assert "event: token" in raw
    assert "event: references" in raw
    assert "event: done" in raw
    assert "组成" in raw


def test_stream_low_confidence_emits_safety_and_fallback_text(client, monkeypatch):
    _patch_agent(client, monkeypatch, safety="low_confidence",
                 safety_message="知识库中未检索到可靠依据。", answer="知识库中未检索到可靠依据。")
    with client.stream("POST", "/api/chat/stream", json={"question": "今天天气"}) as resp:
        raw = "".join(resp.iter_text())
    assert '"type": "low_confidence"' in raw
    assert "知识库中未检索到可靠依据" in raw


def test_stream_empty_question_rejected(client):
    resp = client.post("/api/chat/stream", json={"question": ""})
    assert resp.status_code == 422


def test_stream_generation_error_emits_error_event(client, monkeypatch):
    _patch_agent(client, monkeypatch)

    def _boom(system, user, temperature=0.3):
        raise RuntimeError("LLM 网络故障")
        yield  # pragma: no cover

    monkeypatch.setattr(chatmod, "chat_completion_stream", _boom)
    with client.stream("POST", "/api/chat/stream", json={"question": "四君子汤组成"}) as resp:
        assert resp.status_code == 200
        raw = "".join(resp.iter_text())
    assert "event: error" in raw
    assert "LLM 网络故障" in raw
