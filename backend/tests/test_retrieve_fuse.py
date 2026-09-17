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
    assert PLAN_MATRIX["compare"] == ["vector_search", "keyword_search", "graph_search"]
    assert PLAN_MATRIX["chitchat"] == []


def test_route_returns_safety_for_chitchat():
    assert route(_state(intent="chitchat")) == "safety"
    assert route(_state(intent="relation")) == "retrieve"
    assert route(_state(intent="compare")) == "retrieve"   # 比较意图进检索，不走兜底


def test_retrieve_invokes_tools_per_plan(monkeypatch):
    calls = []

    class FakeTool:
        def __init__(self, name):
            self._name = name
        def invoke(self, kwargs):
            calls.append(self._name)
            return {"fact": self._name}

    monkeypatch.setattr(rmod, "TOOLS", {n: FakeTool(n) for n in ["vector_search", "keyword_search", "graph_search"]})
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

    monkeypatch.setattr(rmod, "TOOLS", {n: FakeTool(n) for n in ["vector_search", "keyword_search", "graph_search"]})
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


def test_fuse_graph_exemption_filters_low_score_evidence(monkeypatch):
    monkeypatch.setattr(fmod, "rrf_fuse", lambda lists, k=60, weights=None: [
        {"chunk_id": "a", "title": "低分噪声", "text": "噪声", "rrf_score": 0.1},
    ])
    monkeypatch.setattr(fmod, "rerank", lambda q, docs, top_n: [{"index": 0, "score": 0.12}])
    monkeypatch.setattr(fmod, "get_settings", lambda: _Cfg())
    st = _state(vector_hits=[{"chunk_id": "a"}],
                graph_facts=[{"source": "四君子汤", "relation": "禁忌", "target": "证候不符不得使用"}])
    upd = fmod.fuse(st)
    assert upd["low_confidence"] is True
    assert upd["evidence"] == []          # 低分噪声被剔除，图谱独立支撑
    assert upd["confidence"] == 0.0


def test_reflect_edge_triggers_once(monkeypatch):
    monkeypatch.setattr(fmod, "get_settings", lambda: _Cfg())
    # 不足 + 未反射 → reflect
    assert reflect_edge(_state(evidence=[], graph_facts=[], reflect_count=0)) == "reflect"
    # 已反射一轮 → safety
    assert reflect_edge(_state(evidence=[], graph_facts=[], reflect_count=1)) == "safety"
    # 置信度低但图谱支持 → safety（豁免）
    assert reflect_edge(_state(low_confidence=True, graph_facts=[{"relation": "组成"}], reflect_count=0)) == "safety"


class _Cfg:
    def __init__(self, **over):
        self.semantic_k = 20
        self.keyword_k = 20
        self.fuse_candidate = 25
        self.final_evidence = 5
        self.rrf_k = 60
        self.rerank_top_n = 5
        self.evidence_min_score = 0.3
        self.graph_hop = 2
        for k, v in over.items():
            setattr(self, k, v)


def test_retrieve_reads_topk_from_settings(monkeypatch):
    calls_kwargs = []

    class FakeTool:
        def __init__(self, name):
            self._name = name
        def invoke(self, kwargs):
            calls_kwargs.append((self._name, dict(kwargs)))
            return {"fact": self._name}

    monkeypatch.setattr(rmod, "TOOLS", {n: FakeTool(n) for n in ["vector_search", "keyword_search", "graph_search"]})
    monkeypatch.setattr(rmod, "get_settings",
                        lambda: _Cfg(semantic_k=7, keyword_k=3))
    rmod.retrieve(_state(intent="concept", entity_names=[], rewritten_query="风寒束表 风热犯表"))
    kw = dict(calls_kwargs)
    assert kw["vector_search"]["top_k"] == 7
    assert kw["keyword_search"]["top_k"] == 3


def test_retrieve_reads_topk_from_inference(monkeypatch):
    calls_kwargs = []

    class FakeTool:
        def __init__(self, name):
            self._name = name
        def invoke(self, kwargs):
            calls_kwargs.append((self._name, dict(kwargs)))
            return {"fact": self._name}

    monkeypatch.setattr(rmod, "TOOLS", {n: FakeTool(n) for n in ["vector_search", "keyword_search", "graph_search"]})
    monkeypatch.setattr(rmod, "get_settings",
                        lambda: _Cfg(semantic_k=7, keyword_k=3))
    rmod.retrieve(_state(intent="concept", entity_names=[], rewritten_query="风寒束表 风热犯表",
                         inference={"semantic_k": 3, "keyword_k": 4}))
    kw = dict(calls_kwargs)
    assert kw["vector_search"]["top_k"] == 3     # inference 覆盖 settings 的 7
    assert kw["keyword_search"]["top_k"] == 4    # inference 覆盖 settings 的 3


def test_fuse_reads_inference_overrides(monkeypatch):
    seen = {}

    def _rrf(lists, k=60, weights=None):
        seen["k"] = k
        return [
            {"chunk_id": "a", "title": "四君子汤", "text": "组成人参白术茯苓炙甘草", "rrf_score": 0.3},
            {"chunk_id": "b", "title": "归脾汤", "text": "益气补血", "rrf_score": 0.2},
        ]

    def _rerank(q, docs, top_n):
        seen["top_n"] = top_n
        return [{"index": 0, "score": 0.9}]

    monkeypatch.setattr(fmod, "rrf_fuse", _rrf)
    monkeypatch.setattr(fmod, "rerank", _rerank)
    monkeypatch.setattr(fmod, "get_settings", lambda: _Cfg())
    st = _state(vector_hits=[{"chunk_id": "a"}], keyword_hits=[{"chunk_id": "b"}],
                inference={"rrf_k": 40, "fuse_candidate": 1})
    upd = fmod.fuse(st)
    assert seen["k"] == 40           # rrf_k 被 inference 覆盖
    assert len(upd["fused"]) == 1    # fuse_candidate=1 截断生效
    assert seen["top_n"] == 5        # final_evidence 未设置 → 回落 rerank_top_n

    st2 = _state(vector_hits=[{"chunk_id": "a"}], keyword_hits=[{"chunk_id": "b"}],
                 inference={"final_evidence": 2})
    fmod.fuse(st2)
    assert seen["top_n"] == 2        # 最终证据数覆盖精排 top_n（Ruling T1-3 打通）


def test_retrieve_concept_with_entities_adds_graph(monkeypatch):
    calls = []

    class FakeTool:
        def __init__(self, name):
            self._name = name
        def invoke(self, kwargs):
            calls.append((self._name, dict(kwargs)))
            return {"fact": self._name}

    monkeypatch.setattr(rmod, "TOOLS", {n: FakeTool(n) for n in ["vector_search", "keyword_search", "graph_search"]})
    monkeypatch.setattr(rmod, "get_settings", lambda: _Cfg(graph_hop=2))
    upd = rmod.retrieve(_state(intent="concept", entity_names=["四君子汤", "归脾汤"],
                               rewritten_query="四君子汤和归脾汤有什么区别"))
    # concept 但有明确实体 → 补开图谱路（此前只 vector+keyword，图谱证据被丢弃）
    assert upd["plan"] == ["vector_search", "keyword_search", "graph_search"]
    g_calls = [c for c in calls if c[0] == "graph_search"]
    assert len(g_calls) == 2                      # 每个实体各查一次
    assert {c[1]["entity"] for c in g_calls} == {"四君子汤", "归脾汤"}


def test_retrieve_graph_hop_from_settings(monkeypatch):
    calls_kwargs = []

    class FakeTool:
        def __init__(self, name):
            self._name = name
        def invoke(self, kwargs):
            calls_kwargs.append((self._name, dict(kwargs)))
            return {"fact": self._name}

    monkeypatch.setattr(rmod, "TOOLS", {n: FakeTool(n) for n in ["vector_search", "keyword_search", "graph_search"]})
    monkeypatch.setattr(rmod, "get_settings", lambda: _Cfg(graph_hop=2))
    rmod.retrieve(_state(intent="complex", entity_names=["心脾两虚"], rewritten_query="心脾两虚的方剂"))
    kw = dict(calls_kwargs)
    assert kw["graph_search"]["hop"] == 2         # 多跳激活：hop 读 settings 而非写死 1


# ===== Task 3（查询分解方案）：子查询扇出 + 命中打标 =====

class _TagTool:
    """记录调用的 Fake 工具：vector/keyword 返回带子查询可辨识的 hit，graph 返回事实。"""

    def __init__(self, name, calls):
        self._name = name
        self._calls = calls

    def invoke(self, kwargs):
        self._calls.append((self._name, dict(kwargs)))
        if self._name == "graph_search":
            return {"entity": kwargs["entity"],
                    "facts": [{"source": kwargs["entity"], "relation": "组成", "target": "X"}]}
        return [{"chunk_id": f"{kwargs['query']}-hit", "text": "..."}]


def test_retrieve_fans_out_per_sub_query(monkeypatch):
    """compare 两个实体 → 向量/关键词各查 2 次（每子查询一次），命中带 sub_query 下标（例 1 回归）。"""
    calls = []
    monkeypatch.setattr(rmod, "TOOLS", {n: _TagTool(n, calls) for n in ["vector_search", "keyword_search", "graph_search"]})
    monkeypatch.setattr(rmod, "get_settings", lambda: _Cfg())
    st = _state(intent="compare", entity_names=["麻黄汤", "桂枝汤"],
                rewritten_query="麻黄汤和桂枝汤的区别",
                sub_queries=[{"query": "麻黄汤 组成 主治", "entities": ["麻黄汤"]},
                             {"query": "桂枝汤 组成 主治", "entities": ["桂枝汤"]}])
    upd = rmod.retrieve(st)
    v_queries = sorted(c[1]["query"] for c in calls if c[0] == "vector_search")
    k_queries = sorted(c[1]["query"] for c in calls if c[0] == "keyword_search")
    assert v_queries == ["桂枝汤 组成 主治", "麻黄汤 组成 主治"]
    assert k_queries == ["桂枝汤 组成 主治", "麻黄汤 组成 主治"]
    # 每条命中带子查询下标，且按下标顺序汇聚
    assert upd["vector_hits"] == [
        {"chunk_id": "麻黄汤 组成 主治-hit", "text": "...", "sub_query": 0},
        {"chunk_id": "桂枝汤 组成 主治-hit", "text": "...", "sub_query": 1}]
    assert upd["trace"][0]["sub_query_n"] == 2


def test_retrieve_sub_queries_fallback_single(monkeypatch):
    """state 无 sub_queries（直接构造/兜底路径）→ 回落单查询，行为等同改造前。"""
    calls = []
    monkeypatch.setattr(rmod, "TOOLS", {n: _TagTool(n, calls) for n in ["vector_search", "keyword_search", "graph_search"]})
    monkeypatch.setattr(rmod, "get_settings", lambda: _Cfg())
    upd = rmod.retrieve(_state(intent="concept", entity_names=[], rewritten_query="风寒束表 风热犯表"))
    assert [c[1]["query"] for c in calls if c[0] == "vector_search"] == ["风寒束表 风热犯表"]
    assert upd["vector_hits"][0]["sub_query"] == 0
    assert upd["trace"][0]["sub_query_n"] == 1


def test_retrieve_graph_entities_union_sub_queries(monkeypatch):
    """图谱实体 = 全局实体 ∪ 子查询实体（保序去重）：子查询独有的实体也进图谱。"""
    calls = []
    monkeypatch.setattr(rmod, "TOOLS", {n: _TagTool(n, calls) for n in ["vector_search", "keyword_search", "graph_search"]})
    monkeypatch.setattr(rmod, "get_settings", lambda: _Cfg())
    rmod.retrieve(_state(intent="compare", entity_names=["麻黄汤"],
                         rewritten_query="麻黄汤和桂枝汤区别",
                         sub_queries=[{"query": "麻黄汤 组成", "entities": ["麻黄汤"]},
                                      {"query": "桂枝汤 组成", "entities": ["桂枝汤"]}]))
    g_entities = sorted(c[1]["entity"] for c in calls if c[0] == "graph_search")
    assert g_entities == ["桂枝汤", "麻黄汤"]            # 桂枝汤仅存在于子查询，也查图谱


def test_retrieve_graph_facts_tagged_with_entity(monkeypatch):
    """图谱事实带来源实体标签（供 compare 分组与相关性过滤）。"""
    calls = []
    monkeypatch.setattr(rmod, "TOOLS", {n: _TagTool(n, calls) for n in ["vector_search", "keyword_search", "graph_search"]})
    monkeypatch.setattr(rmod, "get_settings", lambda: _Cfg())
    upd = rmod.retrieve(_state(intent="complex", entity_names=["麻黄汤"], rewritten_query="麻黄汤组成"))
    assert upd["graph_facts"] == [{"source": "麻黄汤", "relation": "组成", "target": "X", "entity": "麻黄汤"}]