import app.agent.nodes.fuse as fmod
import app.agent.nodes.retrieve as rmod
from app.agent.nodes.route import PLAN_MATRIX, route
from app.agent.nodes.fuse import fuse, reflect_edge, REFLECT_MAX


def _state(**over):
    base = {
        "question": "q", "session_id": "s", "chat_history": [], "rewritten_query": "q",
        "entities": [], "entity_names": [], "intent": "complex", "plan": [],
        "vector_hits": [], "keyword_hits": [], "graph_facts": [], "trace": [],
        "fused": [], "evidence": [], "confidence": 0.0, "low_confidence": False,
        "reflect_count": 0, "safety_flag": None, "safety_message": "", "prompt": "",
        "answer": "",
    }
    base.update(over)
    return base


def test_plan_matrix_routing():
    assert PLAN_MATRIX["relation"] == ["vector_search", "graph_search"]
    assert PLAN_MATRIX["concept"] == ["vector_search", "keyword_search"]
    assert PLAN_MATRIX["complex"] == ["vector_search", "keyword_search", "graph_search"]
    assert PLAN_MATRIX["chitchat"] == []


def test_route_returns_safety_for_chitchat():
    assert route(_state(intent="chitchat")) == "safety"
    assert route(_state(intent="relation")) == "retrieve"


def test_retrieve_invokes_tools_per_plan(monkeypatch):
    calls = []

    class FakeTool:
        def __init__(self, name):
            self._name = name
        def invoke(self, kwargs):
            calls.append(self._name)
            return {"fact": self._name}

    rmod.TOOLS = {n: FakeTool(n) for n in ["vector_search", "keyword_search", "graph_search"]}
    upd = rmod.retrieve(_state(intent="complex", entity_names=["四君子汤"], rewritten_query="四君子汤组成"))
    assert upd["plan"] == ["vector_search", "keyword_search", "graph_search"]
    assert calls == ["vector_search", "keyword_search", "graph_search"]
    assert upd["trace"][0]["step"] == "retrieve"


def test_retrieve_skips_graph_without_entities(monkeypatch):
    calls = []

    class FakeTool:
        def __init__(self, name):
            self._name = name
        def invoke(self, kwargs):
            calls.append(self._name)
            return {"fact": self._name}

    rmod.TOOLS = {n: FakeTool(n) for n in ["vector_search", "keyword_search", "graph_search"]}
    rmod.retrieve(_state(intent="concept", entity_names=[], rewritten_query="风寒束表与风热犯表的区别"))
    assert "graph_search" not in calls        # 无实体 → 跳过图谱
    assert calls == ["vector_search", "keyword_search"]


def test_fuse_rrf_and_rerank(monkeypatch):
    monkeypatch.setattr(fmod, "rrf_fuse", lambda lists, k=60, weights=None: [
        {"chunk_id": "a", "title": "四君子汤", "text": "组成人参白术茯苓炙甘草", "rrf_score": 0.3},
        {"chunk_id": "b", "title": "归脾汤", "text": "益气补血", "rrf_score": 0.2},
    ])
    monkeypatch.setattr(fmod, "rerank", lambda q, docs, top_n: [{"index": 0, "score": 0.9}, {"index": 1, "score": 0.4}])
    monkeypatch.setattr(fmod, "get_settings", lambda: _Cfg())
    st = _state(vector_hits=[{"chunk_id": "a"}], keyword_hits=[{"chunk_id": "b"}])
    upd = fmod.fuse(st)
    assert upd["evidence"][0]["chunk_id"] == "a"
    assert upd["evidence"][0]["score"] == 0.9
    assert upd["confidence"] == 0.9
    assert upd["low_confidence"] is False
    assert [e["step"] for e in upd["trace"]] == ["fuse", "rerank"]


def test_reflect_edge_triggers_once(monkeypatch):
    monkeypatch.setattr(fmod, "get_settings", lambda: _Cfg())
    # 不足 + 未反射 → reflect
    assert reflect_edge(_state(evidence=[], graph_facts=[], reflect_count=0)) == "reflect"
    # 已反射一轮 → safety
    assert reflect_edge(_state(evidence=[], graph_facts=[], reflect_count=1)) == "safety"
    # 置信度低但图谱支持 → safety（豁免）
    assert reflect_edge(_state(low_confidence=True, graph_facts=[{"relation": "组成"}], reflect_count=0)) == "safety"


class _Cfg:
    semantic_k = 20; keyword_k = 20; fuse_candidate = 25; final_evidence = 5
    rrf_k = 60; rerank_top_n = 5; evidence_min_score = 0.3