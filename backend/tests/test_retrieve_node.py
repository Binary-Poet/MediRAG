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
                               "sub_query_n": 1, "path_template": None}


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


# ===== Task 6（查询分解方案）：定向路径模板选路 =====

class _PathTool:
    """记录调用；graph_path_search 返回带共现计数的事实，graph_search 返回单实体事实。"""

    def __init__(self, name, calls):
        self._name = name
        self._calls = calls

    def invoke(self, kwargs):
        self._calls.append((self._name, dict(kwargs)))
        if self._name == "graph_path_search":
            return {"template": kwargs["template"], "facts": [
                {"source": "心血虚", "relation": "主治", "target": "归脾汤", "hit": 3,
                 "path_template": kwargs["template"]}]}
        if self._name == "graph_search":
            return {"entity": kwargs["entity"],
                    "facts": [{"source": kwargs["entity"], "relation": "组成", "target": "X"}]}
        return []


def _patch_tools(monkeypatch, calls):
    monkeypatch.setattr(rmod, "TOOLS", {
        n: _PathTool(n, calls)
        for n in ["vector_search", "keyword_search", "graph_search", "graph_path_search"]})


def test_retrieve_uses_symptom_template_for_multi_symptom(monkeypatch):
    """三个症状实体 + complex → 走 症状→证候→方剂 定向模板，不走无向邻居（例 2 回归）。"""
    calls = []
    _patch_tools(monkeypatch, calls)
    out = rmod.retrieve({
        "intent": "complex", "rewritten_query": "胸痛心悸失眠",
        "question": "胸痛、心悸、失眠同时出现，可能是什么证型？该用什么方剂？",
        "entity_names": ["胸痛", "心悸", "失眠"],
        "entities": [{"name": "胸痛", "type": "症状"}, {"name": "心悸", "type": "症状"},
                     {"name": "失眠", "type": "症状"}]})
    path_calls = [c for c in calls if c[0] == "graph_path_search"]
    assert len(path_calls) == 1
    assert path_calls[0][1] == {"template": "symptom_to_formula", "names": ["胸痛", "心悸", "失眠"]}
    assert not [c for c in calls if c[0] == "graph_search"]        # 不走无向邻居
    # 模板事实端点不是查询实体，锚定过滤不得误杀
    assert out["graph_facts"][0]["hit"] == 3
    assert out["trace"][0]["path_template"] == "symptom_to_formula"


def test_retrieve_uses_formula_mechanism_on_mechanism_question(monkeypatch):
    """方剂实体 + 机制词（配伍）→ 组成/功效机制链（例 3 回归，relation 意图也生效）。"""
    calls = []
    _patch_tools(monkeypatch, calls)
    out = rmod.retrieve({
        "intent": "relation", "rewritten_query": "麻黄汤配伍",
        "question": "为什么麻黄汤能治太阳伤寒？它的配伍如何体现解表发汗？",
        "entity_names": ["麻黄汤"],
        "entities": [{"name": "麻黄汤", "type": "方剂"}]})
    path_calls = [c for c in calls if c[0] == "graph_path_search"]
    assert path_calls[0][1] == {"template": "formula_mechanism", "names": ["麻黄汤"]}
    assert out["trace"][0]["path_template"] == "formula_mechanism"


def test_retrieve_falls_back_to_neighbors_for_mixed_types(monkeypatch):
    """实体类型混杂（无单一模板适用）→ 回落无向邻居逐实体查询，path_template 为空。"""
    calls = []
    _patch_tools(monkeypatch, calls)
    out = rmod.retrieve({
        "intent": "complex", "rewritten_query": "q", "question": "q",
        "entity_names": ["四君子汤", "人参"],
        "entities": [{"name": "四君子汤", "type": "方剂"}, {"name": "人参", "type": "中药"}]})
    assert not [c for c in calls if c[0] == "graph_path_search"]
    assert sorted(c[1]["entity"] for c in calls if c[0] == "graph_search") == ["人参", "四君子汤"]
    assert out["trace"][0]["path_template"] is None
