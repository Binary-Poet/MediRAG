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
        self.coverage_min_score = 0.6
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


# ===== Task 4（查询分解方案）：按子查询对齐精排 =====

def _rrf_single(lists, k=60, weights=None):
    """固定返回单条候选（忽略入参），用于隔离精排行为。"""
    return [{"chunk_id": "a", "title": "党参", "text": "补中益气", "rrf_score": 0.3}]


def test_fuse_reranks_per_sub_query_and_takes_max(monkeypatch):
    """2 个子查询 → 精排各调一次；证据分取各子查询 max（例 4 回归：不再被整句压分）。"""
    seen = []

    def _rerank(q, docs, top_n):
        seen.append(q)
        return [{"index": 0, "score": 0.2 if "人参" in q else 0.8}]

    monkeypatch.setattr(fmod, "rrf_fuse", _rrf_single)
    monkeypatch.setattr(fmod, "rerank", _rerank)
    monkeypatch.setattr(fmod, "get_settings", lambda: _Cfg())
    st = _state(rewritten_query="人参、党参、西洋参补气有什么区别",
                sub_queries=[{"query": "人参 补气 证型", "entities": ["人参"]},
                             {"query": "党参 补气 证型", "entities": ["党参"]}],
                vector_hits=[{"chunk_id": "a", "sub_query": 0}],
                keyword_hits=[{"chunk_id": "a", "sub_query": 1}])
    upd = fmod.fuse(st)
    assert seen == ["人参 补气 证型", "党参 补气 证型"]      # 每个子查询各打分一次
    assert upd["evidence"][0]["score"] == 0.8               # 取 max
    assert upd["evidence"][0]["matched_queries"] == [0, 1]  # 命中来源子查询


def test_fuse_groups_hits_by_sub_query_before_rrf(monkeypatch):
    """子查询各自的向量/关键词先各自 RRF，候选按 chunk_id 合并去重。"""
    seen_lists = []

    def _rrf(lists, k=60, weights=None):
        seen_lists.append([[d["chunk_id"] for d in lst] for lst in lists])
        return [{"chunk_id": lst[0]["chunk_id"], "title": "t", "text": "x", "rrf_score": 0.5}
                for lst in lists if lst]

    monkeypatch.setattr(fmod, "rrf_fuse", _rrf)
    monkeypatch.setattr(fmod, "rerank", lambda q, docs, top_n: [{"index": 0, "score": 0.9}])
    monkeypatch.setattr(fmod, "get_settings", lambda: _Cfg())
    st = _state(rewritten_query="a 与 b 的区别",
                sub_queries=[{"query": "qa", "entities": ["a"]}, {"query": "qb", "entities": ["b"]}],
                vector_hits=[{"chunk_id": "v0", "sub_query": 0}, {"chunk_id": "v1", "sub_query": 1}],
                keyword_hits=[{"chunk_id": "k1", "sub_query": 1}])
    upd = fmod.fuse(st)
    assert seen_lists == [[["v0"], []], [["v1"], ["k1"]]]   # 按子查询分组：子查询0无关键词命中
    assert [c["chunk_id"] for c in upd["fused"]] == ["v0", "v1", "k1"]


def test_fuse_untagged_hits_fall_back_to_single_query(monkeypatch):
    """无子查询/无标签（老路径）→ 行为等同改造前：单查询精排。"""
    seen = []

    def _rerank(q, docs, top_n):
        seen.append(q)
        return [{"index": 0, "score": 0.9}, {"index": 1, "score": 0.4}]

    monkeypatch.setattr(fmod, "rrf_fuse", lambda lists, k=60, weights=None: [
        {"chunk_id": "a", "title": "四君子汤", "text": "组成人参白术茯苓炙甘草", "rrf_score": 0.3},
        {"chunk_id": "b", "title": "归脾汤", "text": "益气补血", "rrf_score": 0.2},
    ])
    monkeypatch.setattr(fmod, "rerank", _rerank)
    monkeypatch.setattr(fmod, "get_settings", lambda: _Cfg())
    upd = fmod.fuse(_state(rewritten_query="四君子汤组成",
                           vector_hits=[{"chunk_id": "a"}], keyword_hits=[{"chunk_id": "b"}]))
    assert seen == ["四君子汤组成"]                          # 只调一次精排
    assert [e["chunk_id"] for e in upd["evidence"]] == ["a", "b"]


# ===== 覆盖度（部分实体无依据）=====

def _three_way(**over):
    """人参/党参/西洋参三联比较：演示库里只有人参有依据的复现状态。"""
    st = dict(intent="compare", rewritten_query="人参、党参、西洋参补气有什么区别",
              sub_queries=[{"query": "人参 补气 证型", "entities": ["人参"]},
                           {"query": "党参 补气 证型", "entities": ["党参"]},
                           {"query": "西洋参 补气 证型", "entities": ["西洋参"]}],
              vector_hits=[{"chunk_id": "a", "sub_query": 0}],
              keyword_hits=[{"chunk_id": "a", "sub_query": 0}])
    st.update(over)
    return _state(**st)


def _status(upd):
    return next(e for e in upd["trace"] if e["step"] == "rerank")


def test_fuse_compare_partial_coverage_marks_missing_entities(monkeypatch):
    """compare 只有一方有依据：置信度照旧是全局 max，但状态必须降级（例 4 回归）。

    实测「人参、党参、西洋参」只有人参查到依据，confidence 却 0.9626、显示「证据充分」，
    用户会以为三方都比过了。覆盖度与置信度正交：不调小置信度以免误触拒答。
    """
    monkeypatch.setattr(fmod, "rrf_fuse", _rrf_single)
    monkeypatch.setattr(fmod, "rerank",
                        lambda q, docs, top_n: [{"index": 0, "score": 0.96 if "人参" in q else 0.15}])
    monkeypatch.setattr(fmod, "get_settings", lambda: _Cfg())
    upd = fmod.fuse(_three_way())

    assert upd["confidence"] == 0.96                        # 全局 max 不变
    assert upd["low_confidence"] is False                   # 不因覆盖不足触发拒答
    assert upd["sub_query_covered"] == [True, False, False]
    assert _status(upd)["covered_n"] == 1 and _status(upd)["sub_query_n"] == 3
    assert _status(upd)["status"] == "部分实体无依据（1/3）"
    # 每个子查询都命中了全部候选：matched_queries 恒为 [0,1,2]，毫无区分度。
    # 覆盖度若改由 matched_queries 推导会得到 3/3——正是要避免的假信号。
    assert upd["evidence"][0]["matched_queries"] == [0, 1, 2]


def test_fuse_compare_full_coverage_keeps_status(monkeypatch):
    """三方都有过阈证据 → 状态不变，不得无谓降级。"""
    monkeypatch.setattr(fmod, "rrf_fuse", _rrf_single)
    monkeypatch.setattr(fmod, "rerank", lambda q, docs, top_n: [{"index": 0, "score": 0.9}])
    monkeypatch.setattr(fmod, "get_settings", lambda: _Cfg())
    upd = fmod.fuse(_three_way())

    assert upd["sub_query_covered"] == [True, True, True]
    assert _status(upd)["status"] == "证据充分，正常生成"


def test_fuse_partial_coverage_only_applies_to_compare(monkeypatch):
    """非 compare（complex 多子查询）不降级：那是「一个问题的多个方面」，不是待对比的实体。"""
    monkeypatch.setattr(fmod, "rrf_fuse", _rrf_single)
    monkeypatch.setattr(fmod, "rerank",
                        lambda q, docs, top_n: [{"index": 0, "score": 0.9 if "人参" in q else 0.15}])
    monkeypatch.setattr(fmod, "get_settings", lambda: _Cfg())
    upd = fmod.fuse(_three_way(intent="complex"))

    assert upd["sub_query_covered"] == [True, False, False]  # 覆盖度照样记录
    assert _status(upd)["status"] == "证据充分，正常生成"      # 但不影响状态


def test_fuse_coverage_uses_its_own_threshold_not_reject_threshold(monkeypatch):
    """覆盖度阈值必须严于拒答阈值：实测库里没内容的子查询也能蹭到 0.37~0.44 分。

    0.45 分既高于拒答阈值 0.3（不拒答）、又低于覆盖阈值 0.6（该实体没有依据）——
    两者若共用一个阈值，这类「近义蹭分」会被当成有依据，正是要防的假信号。
    """
    monkeypatch.setattr(fmod, "rrf_fuse", _rrf_single)
    monkeypatch.setattr(fmod, "rerank",
                        lambda q, docs, top_n: [{"index": 0, "score": 0.95 if "人参" in q else 0.45}])
    monkeypatch.setattr(fmod, "get_settings", lambda: _Cfg())
    upd = fmod.fuse(_three_way())

    assert upd["low_confidence"] is False                     # 0.95 远高于拒答阈值
    assert upd["confidence"] == 0.95
    assert upd["sub_query_covered"] == [True, False, False]   # 0.45 < 0.6 → 无依据
    assert upd["sub_query_scores"] == [0.95, 0.45, 0.45]
    assert _status(upd)["status"] == "部分实体无依据（1/3）"


def test_fuse_coverage_all_false_when_below_threshold(monkeypatch):
    """全部子查询都低于阈值 → covered 全 False，但状态走「知识库未匹配」而非「部分」分支。"""
    monkeypatch.setattr(fmod, "rrf_fuse", _rrf_single)
    monkeypatch.setattr(fmod, "rerank", lambda q, docs, top_n: [{"index": 0, "score": 0.15}])
    monkeypatch.setattr(fmod, "get_settings", lambda: _Cfg())
    upd = fmod.fuse(_three_way())

    assert upd["sub_query_covered"] == [False, False, False]
    assert upd["low_confidence"] is True
    assert _status(upd)["status"] == "知识库未匹配"