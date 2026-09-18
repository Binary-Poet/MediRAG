"""7 个验收边界用例的端到端回归（全 mock：LLM / 检索工具 / 图谱客户端均不触网）。

跑的是**真实图 + 真实节点**（understand → retrieve → fuse → reflect → safety → context），
只把三处外部依赖换成 fake：understand 的 LLM 输出、retrieve 的四路 Tool、fuse 的 rerank。
这样断言的不是「某个函数返回值」，而是「这类问题在图里实际走了哪条编排、查了哪几路、
证据怎么进 Prompt」——正是 PLAN_MATRIX 只管「开哪几路」时缺的那一层。

fake rerank 按「子查询词是否出现在文档文本中」打分：子查询 i 只给它自己那批命中打高分。
旧行为（整句对比问题当唯一 query）下两个实体都拿不到高分，故本文件对「双方证据都在
最终 evidence 里」的断言同时是「按子查询对齐精排」的回归证据。
"""
import json

import app.agent.nodes.fuse as fmod
import app.agent.nodes.reflect as remod
import app.agent.nodes.retrieve as rmod
import app.agent.nodes.safety as smod
import app.agent.nodes.understand as umod
import app.agent.workflow as wmod

# ===== fake 外部依赖 =====

ENTITY_FACTS = {
    "麻黄汤": [("麻黄汤", "组成", "麻黄"), ("麻黄汤", "组成", "桂枝"), ("麻黄汤", "主治", "太阳伤寒表实证")],
    "桂枝汤": [("桂枝汤", "组成", "桂枝"), ("桂枝汤", "组成", "芍药"), ("桂枝汤", "主治", "太阳中风表虚证")],
    "逍遥散": [("逍遥散", "组成", "柴胡"), ("逍遥散", "主治", "肝郁血虚脾弱证")],
    "加味逍遥散": [("加味逍遥散", "组成", "牡丹皮"), ("加味逍遥散", "组成", "栀子")],
    "太阳表证": [("太阳表证", "主治", "麻黄汤")],
    "少阳证": [("少阳证", "主治", "小柴胡汤")],
    "人参": [("人参", "功效", "大补元气")],
    "党参": [("党参", "功效", "补中益气")],
    "西洋参": [("西洋参", "功效", "补气养阴")],
}

PATH_FACTS = {
    # 症状→证候→方剂：证候按共现计数排序（hit 降序）
    "symptom_to_formula": [
        {"source": "心血虚", "relation": "主治", "target": "归脾汤", "hit": 3,
         "path_template": "symptom_to_formula"},
        {"source": "心气虚", "relation": "主治", "target": "养心汤", "hit": 2,
         "path_template": "symptom_to_formula"},
    ],
    "syndrome_to_formula": [
        {"source": "太阳少阳合病", "relation": "主治", "target": "柴胡桂枝汤", "hit": 2,
         "path_template": "syndrome_to_formula"},
    ],
    # 方剂→组成→中药→功效：机制链，hop 允许 3
    "formula_mechanism": [
        {"source": "麻黄汤", "relation": "组成", "target": "麻黄",
         "path_template": "formula_mechanism"},
        {"source": "麻黄", "relation": "功效", "target": "发汗解表", "eff_source": True,
         "path_template": "formula_mechanism"},
    ],
}


class _FakeTool:
    """四路检索 Tool 的 fake：调用留痕，返回带 query 文本的假切片 / 查表图谱事实。"""

    def __init__(self, name, calls):
        self._name = name
        self._calls = calls

    def invoke(self, kwargs):
        self._calls.append((self._name, dict(kwargs)))
        if self._name == "vector_search":
            q = kwargs["query"]
            return [{"chunk_id": f"v:{q}", "title": q, "text": f"{q} 的文献原文",
                     "doc_name": "伤寒论", "chapter": "辨太阳病脉证并治", "page_no": 12}]
        if self._name == "keyword_search":
            q = kwargs["query"]
            return [{"chunk_id": f"k:{q}", "title": q, "text": f"{q} 的关键词命中",
                     "doc_name": "伤寒论", "chapter": "辨太阳病脉证并治", "page_no": 13}]
        if self._name == "graph_path_search":
            return {"template": kwargs["template"], "facts": list(PATH_FACTS.get(kwargs["template"], []))}
        if self._name == "graph_search":
            return {"entity": kwargs["entity"],
                    "facts": [{"source": s, "relation": r, "target": t}
                              for s, r, t in ENTITY_FACTS.get(kwargs["entity"], [])]}
        raise AssertionError(f"未知 Tool：{self._name}")


def _fake_rerank(query, docs, top_n=None):
    """按「query 是否出现在文档文本里」打分：子查询 i 的高分只落在子查询 i 的命中上。"""
    out = []
    for i, d in enumerate(docs):
        out.append({"index": i, "score": 0.9 if query in d else 0.2})
    return sorted(out, key=lambda r: -r["score"])[: (top_n or len(out))]


class _EmptyGraph:
    def all_entities(self):
        return []


def _run(monkeypatch, question, llm_out, empty_tools=False):
    """真实图跑一轮：understand 输出指定 JSON，其余外部依赖 fake，返回 (最终 state, 工具调用)。

    reflect 的 LLM 也一并掐掉（抛错 → 回落原查询）：证据不足时图会走进反思轮，
    不 mock 就会真的出网。empty_tools=True 模拟三路检索全空（置信度兜底路径）。
    """
    calls: list = []
    monkeypatch.setattr(umod, "get_graph", lambda: _EmptyGraph())
    monkeypatch.setattr(umod, "chat_completion", lambda *a, **k: llm_out)
    monkeypatch.setattr(rmod, "TOOLS", {n: _FakeTool(n, calls)
                                        for n in ["vector_search", "keyword_search",
                                                  "graph_search", "graph_path_search"]})
    if empty_tools:
        monkeypatch.setattr(rmod, "_guard", lambda fn, default: default)
    monkeypatch.setattr(fmod, "rerank", _fake_rerank)
    monkeypatch.setattr(remod, "chat_completion",
                        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("llm down")))
    final = wmod.build_agent().compile().invoke({
        "question": question, "session_id": "s", "chat_history": [], "rewritten_query": "",
        "sub_queries": [], "entities": [], "entity_names": [], "intent": "", "plan": [],
        "vector_hits": [], "keyword_hits": [], "graph_facts": [], "fused": [], "evidence": [],
        "confidence": 0.0, "low_confidence": True, "reflect_count": 0, "safety_flag": None,
        "safety_message": "", "prompt": "", "answer": "", "trace": [],
    })
    return final, calls


def _tools(calls):
    return [c[0] for c in calls]


def _step(final, step):
    return next(t for t in final["trace"] if t["step"] == step)


# ===== 例 1：比较两个方剂（拆分 + 分组 + 双方图谱事实齐） =====

def test_case1_compare_two_formulas(monkeypatch):
    q = "麻黄汤和桂枝汤在主治和配伍上有什么区别？"
    llm = json.dumps({
        "rewritten_query": "麻黄汤 桂枝汤 主治 配伍 区别",
        "sub_queries": [{"query": "麻黄汤 组成 主治", "entities": ["麻黄汤"]},
                        {"query": "桂枝汤 组成 主治", "entities": ["桂枝汤"]}],
        "entities": [{"name": "麻黄汤", "type": "方剂"}, {"name": "桂枝汤", "type": "方剂"}],
        "intent": "compare"}, ensure_ascii=False)
    final, calls = _run(monkeypatch, q, llm)

    assert final["intent"] == "compare"
    assert len(final["sub_queries"]) == 2
    # 两路都按子查询扇出（不是拿整句问一次）
    assert _tools(calls).count("vector_search") == 2 and _tools(calls).count("keyword_search") == 2
    # 双方图谱事实都进了 state（图谱实体取全局并集）
    assert sorted(c[1]["entity"] for c in calls if c[0] == "graph_search") == ["桂枝汤", "麻黄汤"]
    facts = {(f["source"], f["relation"], f["target"]) for f in final["graph_facts"]}
    assert ("麻黄汤", "主治", "太阳伤寒表实证") in facts
    assert ("桂枝汤", "主治", "太阳中风表虚证") in facts
    # 证据按实体分组进 Prompt，且双方各自的证据都在（对齐精排生效）
    assert "【麻黄汤】" in final["prompt"] and "【桂枝汤】" in final["prompt"]
    assert "麻黄汤 组成 主治 的文献原文" in final["prompt"]
    assert "桂枝汤 组成 主治 的文献原文" in final["prompt"]
    assert final["safety_flag"] == "ok"


# ===== 例 2：多症状 → 证型 → 方剂（定向模板 + 共现排序） =====

def test_case2_multi_symptom_template(monkeypatch):
    q = "胸痛、心悸、失眠同时出现，可能是什么证型？该用什么方剂？"
    llm = json.dumps({
        "rewritten_query": "胸痛 心悸 失眠 证型 方剂",
        "sub_queries": [{"query": "胸痛 心悸 失眠 证型 方剂", "entities": ["胸痛", "心悸", "失眠"]}],
        "entities": [{"name": "胸痛", "type": "症状"}, {"name": "心悸", "type": "症状"},
                     {"name": "失眠", "type": "症状"}],
        "intent": "complex"}, ensure_ascii=False)
    final, calls = _run(monkeypatch, q, llm)

    path_calls = [c for c in calls if c[0] == "graph_path_search"]
    assert path_calls == [("graph_path_search", {"template": "symptom_to_formula",
                                                 "names": ["胸痛", "心悸", "失眠"]})]
    assert not [c for c in calls if c[0] == "graph_search"]     # 不再走无向泛遍历
    assert _step(final, "retrieve")["path_template"] == "symptom_to_formula"
    # 证候按共现计数降序（hit 是图谱侧排序依据，链式推理的关键信号）
    assert [f["hit"] for f in final["graph_facts"]] == [3, 2]
    assert "心血虚 --主治--> 归脾汤" in final["prompt"]


# ===== 例 3：因果/机制（方剂→组成→中药→功效链） =====

def test_case3_mechanism_chain(monkeypatch):
    q = "为什么麻黄汤能治太阳伤寒？它的配伍如何体现解表发汗？"
    llm = json.dumps({
        "rewritten_query": "麻黄汤 配伍 机制 解表发汗",
        "sub_queries": [{"query": "麻黄汤 配伍 功效 机制", "entities": ["麻黄汤"]}],
        "entities": [{"name": "麻黄汤", "type": "方剂"}],
        "intent": "complex"}, ensure_ascii=False)
    final, calls = _run(monkeypatch, q, llm)

    assert [c for c in calls if c[0] == "graph_path_search"] == [
        ("graph_path_search", {"template": "formula_mechanism", "names": ["麻黄汤"]})]
    # 组成事实 + 展开出的中药功效事实：机制链的两段都在
    facts = {(f["source"], f["relation"], f["target"]) for f in final["graph_facts"]}
    assert ("麻黄汤", "组成", "麻黄") in facts
    assert ("麻黄", "功效", "发汗解表") in facts
    assert _step(final, "retrieve")["path_template"] == "formula_mechanism"


# ===== 例 4：三方对比（拆 3 个子查询 + 每方证据都不被压分） =====

def test_case4_three_way_comparison(monkeypatch):
    q = "人参、党参、西洋参在补气方面有什么区别？"
    llm = json.dumps({
        "rewritten_query": "人参 党参 西洋参 补气 区别",
        "sub_queries": [{"query": "人参 补气 功效", "entities": ["人参"]},
                        {"query": "党参 补气 功效", "entities": ["党参"]},
                        {"query": "西洋参 补气 功效", "entities": ["西洋参"]}],
        "entities": [{"name": "人参", "type": "中药"}, {"name": "党参", "type": "中药"},
                     {"name": "西洋参", "type": "中药"}],
        "intent": "compare"}, ensure_ascii=False)
    final, calls = _run(monkeypatch, q, llm)

    assert len(final["sub_queries"]) == 3
    assert _tools(calls).count("vector_search") == 3
    ev_sub = {h for h in (e["matched_queries"] for e in final["evidence"]) for h in h}
    assert ev_sub == {0, 1, 2}                       # 三方证据都进了最终 evidence
    assert final["confidence"] >= 0.9                # 且都拿到本子查询的高分，未被整句 query 压分
    for name in ("人参 补气 功效", "党参 补气 功效", "西洋参 补气 功效"):
        assert f"{name} 的文献原文" in final["prompt"]
    assert final["prompt"].index("【人参】") < final["prompt"].index("【党参】") \
        < final["prompt"].index("【西洋参】")


# ===== 例 5：合病（多证候 → 方剂） =====

def test_case5_compound_syndrome(monkeypatch):
    q = "如果患者既有太阳表证又有少阳证，用什么方剂？"
    llm = json.dumps({
        "rewritten_query": "太阳表证 少阳证 合病 方剂",
        "sub_queries": [{"query": "太阳表证 少阳证 方剂", "entities": ["太阳表证", "少阳证"]}],
        "entities": [{"name": "太阳表证", "type": "证候"}, {"name": "少阳证", "type": "证候"}],
        "intent": "complex"}, ensure_ascii=False)
    final, calls = _run(monkeypatch, q, llm)

    assert [c for c in calls if c[0] == "graph_path_search"] == [
        ("graph_path_search", {"template": "syndrome_to_formula", "names": ["太阳表证", "少阳证"]})]
    assert any(f["target"] == "柴胡桂枝汤" for f in final["graph_facts"])
    assert final["safety_flag"] == "ok"


# ===== 例 6：衍生方（同例 1 形态 + 「加了什么药」需双方图谱事实） =====

def test_case6_derivative_formula(monkeypatch):
    q = "逍遥散和加味逍遥散有什么区别？加了什么药？"
    llm = json.dumps({
        "rewritten_query": "逍遥散 加味逍遥散 组成 区别",
        "sub_queries": [{"query": "逍遥散 组成 主治", "entities": ["逍遥散"]},
                        {"query": "加味逍遥散 组成 区别", "entities": ["加味逍遥散"]}],
        "entities": [{"name": "逍遥散", "type": "方剂"}, {"name": "加味逍遥散", "type": "方剂"}],
        "intent": "compare"}, ensure_ascii=False)
    final, calls = _run(monkeypatch, q, llm)

    assert final["intent"] == "compare" and len(final["sub_queries"]) == 2
    facts = {(f["source"], f["relation"], f["target"]) for f in final["graph_facts"]}
    assert ("加味逍遥散", "组成", "牡丹皮") in facts and ("加味逍遥散", "组成", "栀子") in facts
    assert "【逍遥散】" in final["prompt"] and "【加味逍遥散】" in final["prompt"]


# ===== 例 7：降级路径 =====

def test_case7a_invalid_intent_keeps_output_and_maps_compare(monkeypatch):
    """LLM 输出 intent="comparison"（非法）→ 映射 compare，改写/实体/子查询保留，照常检索。"""
    q = "对比一下风寒感冒和风热感冒的辨证要点、治法、代表方剂。"
    llm = json.dumps({
        "rewritten_query": "风寒感冒 风热感冒 辨证要点 治法 代表方剂",
        "sub_queries": [{"query": "风寒感冒 辨证 治法 方剂", "entities": ["风寒感冒"]},
                        {"query": "风热感冒 辨证 治法 方剂", "entities": ["风热感冒"]}],
        "entities": [{"name": "风寒感冒", "type": "证候"}, {"name": "风热感冒", "type": "证候"}],
        "intent": "comparison"}, ensure_ascii=False)
    final, calls = _run(monkeypatch, q, llm)

    assert final["intent"] == "compare"                    # 非法意图不再整包丢弃
    assert final["entity_names"] == ["风寒感冒", "风热感冒"]
    assert len(final["sub_queries"]) == 2                  # LLM 的子查询被保留
    assert _tools(calls).count("vector_search") == 2       # 确实检索了，不是直接拒答
    assert "【风寒感冒】" in final["prompt"] and "【风热感冒】" in final["prompt"]


def test_case7b_wellness_without_entity_goes_retrieval(monkeypatch):
    """「如何养生」：LLM 输出不可解析 + 词典无实体 → concept 放行检索，不再 chitchat 拒答。"""
    final, calls = _run(monkeypatch, "如何养生", "抱歉，我不太确定你的问题")

    assert final["intent"] == "concept"
    assert final["sub_queries"] == [{"query": "如何养生", "entities": []}]
    # 双路检索照跑（工具调用顺序由线程完成先后决定，故比较集合）
    assert sorted(_tools(calls)) == ["keyword_search", "vector_search"]
    assert final["safety_flag"] == "ok"                           # 不落在 LOW_CONFIDENCE_MESSAGE
    assert "如何养生 的文献原文" in final["prompt"]


def test_case7c_wellness_retrieval_insufficient_still_refuses(monkeypatch):
    """同一句在检索确实无果时仍由置信度兜底拒答——放行检索不等于放宽安全判据。"""
    final, _ = _run(monkeypatch, "如何养生", "抱歉，我不太确定你的问题", empty_tools=True)

    assert final["intent"] == "concept"
    assert final["safety_flag"] == "low_confidence"
    assert final["answer"] == smod.LOW_CONFIDENCE_MESSAGE


# ===== trace 可追溯性：understand 事件带子查询摘要 =====

def test_understand_trace_carries_sub_query_summary():
    from app.agent.nodes.understand import _parse_understand
    raw = ('{"rewritten_query": "麻黄汤 桂枝汤 区别", '
           '"sub_queries": [{"query": "麻黄汤 组成 主治", "entities": ["麻黄汤"]},'
           '                 {"query": "桂枝汤 组成 主治", "entities": ["桂枝汤"]}], '
           '"entities": [{"name": "麻黄汤", "type": "方剂"}], "intent": "compare"}')
    d = _parse_understand(raw)
    assert [sq["query"] for sq in d["sub_queries"]] == ["麻黄汤 组成 主治", "桂枝汤 组成 主治"]
