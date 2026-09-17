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
    # 命中带子查询下标（查询分解方案：单查询回落 → 恒为 0）
    assert out["keyword_hits"] == [{"chunk_id": "k1", "sub_query": 0}]
    assert out["graph_facts"] == [{"source": "四君子汤", "relation": "组成", "target": "人参",
                                   "entity": "四君子汤"}]
    assert out["trace"][0] == {"step": "retrieve", "vector_n": 0, "keyword_n": 1, "graph_n": 1,
                               "graph_dropped_n": 0, "entity_n": 1, "entities": ["四君子汤"],
                               "sub_query_n": 1}


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

    assert out["vector_hits"] == [{"chunk_id": "v1", "sub_query": 0}]
    assert out["keyword_hits"] == [{"chunk_id": "w1", "sub_query": 0}]
    assert out["graph_facts"] == []
    assert out["trace"][0]["graph_n"] == 0


def test_retrieve_drops_unanchored_graph_facts(monkeypatch):
    """图谱事实锚定过滤：保留 1 跳与锚定其邻域的第二跳，剔除旁支（防 2 跳噪声走高置信豁免）。"""
    vec = MagicMock()
    vec.invoke.return_value = []
    kw = MagicMock()
    kw.invoke.return_value = []
    graph = MagicMock()
    graph.invoke.return_value = {"entity": "胸痛", "facts": [
        {"source": "胸痛", "relation": "表现", "target": "心血虚"},        # 1 跳：保留
        {"source": "心血虚", "relation": "主治", "target": "归脾汤"},      # 锚定第二跳：保留
        {"source": "风寒", "relation": "表现", "target": "太阳表证"},      # 旁支：剔除
    ]}
    monkeypatch.setitem(rmod.TOOLS, "vector_search", vec)
    monkeypatch.setitem(rmod.TOOLS, "keyword_search", kw)
    monkeypatch.setitem(rmod.TOOLS, "graph_search", graph)

    out = rmod.retrieve({"intent": "complex", "rewritten_query": "胸痛心悸失眠",
                         "entity_names": ["胸痛"], "sub_queries": [
                             {"query": "胸痛 心悸 失眠", "entities": ["胸痛"]}]})

    kept = [(f["source"], f["relation"], f["target"]) for f in out["graph_facts"]]
    assert kept == [("胸痛", "表现", "心血虚"), ("心血虚", "主治", "归脾汤")]
    assert out["trace"][0]["graph_n"] == 2
    assert out["trace"][0]["graph_dropped_n"] == 1
