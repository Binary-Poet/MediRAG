"""retrieve 节点测试：并行检索失败单路降级，不拖垮整轮回答。"""
from unittest.mock import MagicMock

import app.agent.nodes.retrieve as rmod


def test_retrieve_degrades_failed_channel(monkeypatch):
    """vector 路抛异常时降级为空结果，keyword/graph 路正常返回，节点不抛。"""
    boom = MagicMock()
    boom.invoke.side_effect = RuntimeError("embedding api down")
    keyword_ok = MagicMock()
    keyword_ok.invoke.return_value = [{"chunk_id": "k1"}]
    graph_ok = MagicMock()
    graph_ok.invoke.return_value = {"entity": "四君子汤",
                                    "facts": [{"source": "四君子汤", "relation": "组成", "target": "人参"}]}
    monkeypatch.setitem(rmod.TOOLS, "vector_search", boom)
    monkeypatch.setitem(rmod.TOOLS, "keyword_search", keyword_ok)
    monkeypatch.setitem(rmod.TOOLS, "graph_search", graph_ok)

    state = {"intent": "complex", "rewritten_query": "四君子汤组成", "entity_names": ["四君子汤"]}
    out = rmod.retrieve(state)

    assert out["vector_hits"] == []
    assert out["keyword_hits"] == [{"chunk_id": "k1"}]
    assert out["graph_facts"] == [{"source": "四君子汤", "relation": "组成", "target": "人参"}]
    assert out["trace"][0] == {"step": "retrieve", "vector_n": 0, "keyword_n": 1, "graph_n": 1,
                               "entity_n": 1, "entities": ["四君子汤"]}


def test_retrieve_graph_channel_degrades_alone(monkeypatch):
    """graph 路失败不影响向量/关键词两路。"""
    vec_ok = MagicMock()
    vec_ok.invoke.return_value = [{"chunk_id": "v1"}]
    kw_ok = MagicMock()
    kw_ok.invoke.return_value = [{"chunk_id": "w1"}]
    boom = MagicMock()
    boom.invoke.side_effect = RuntimeError("neo4j down")
    monkeypatch.setitem(rmod.TOOLS, "vector_search", vec_ok)
    monkeypatch.setitem(rmod.TOOLS, "keyword_search", kw_ok)
    monkeypatch.setitem(rmod.TOOLS, "graph_search", boom)

    state = {"intent": "complex", "rewritten_query": "q", "entity_names": ["四君子汤"]}
    out = rmod.retrieve(state)

    assert out["vector_hits"] == [{"chunk_id": "v1"}]
    assert out["keyword_hits"] == [{"chunk_id": "w1"}]
    assert out["graph_facts"] == []
    assert out["trace"][0]["graph_n"] == 0
