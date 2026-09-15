"""图级集成测试：safety 三分支单测 + 完整图 reflect-then-recover demo case。

demo case（方案 4.4 直接证据）：首轮检索不足（向量/图谱均未命中）→ reflect 改写查询
→ 第二轮补查命中图谱事实 → safety 放行（ok）。

注意：monkeypatch 的节点 lambda 只返回"更新 key 的 dict"——trace 为
Annotated[list, add] reducer 累计，全量返回会让 trace 双份堆积。
"""
import app.agent.workflow as wmod
from app.agent.workflow import get_agent  # noqa: F401  接口清单：完整图编译单例

from test_workflow import _state  # 复用上一 Task 的 _state 工厂


def test_safety_emergency_flag():
    import app.agent.nodes.safety as smod
    from app.agent.nodes.safety import safety
    st = _state(question="我胸痛得厉害", entity_names=[], intent="complex")
    upd = safety(st)
    assert upd["safety_flag"] == "emergency"
    assert "120" in upd["safety_message"]


def test_safety_low_confidence_when_no_evidence_and_no_graph():
    import app.agent.nodes.safety as smod
    from app.agent.nodes.safety import safety
    st = _state(question="今天天气", intent="complex", evidence=[], graph_facts=[], low_confidence=True)
    upd = safety(st)
    assert upd["safety_flag"] == "low_confidence"
    assert upd["answer"] == smod.LOW_CONFIDENCE_MESSAGE


def test_safety_ok_when_evidence_sufficient_or_graph_exempted():
    from app.agent.nodes.safety import safety
    # 证据充分 → ok
    st = _state(question="四君子汤有什么禁忌？", intent="relation",
                evidence=[{"chunk_id": "x", "score": 0.8}], low_confidence=False)
    assert safety(st)["safety_flag"] == "ok"
    # 图谱豁免：无证据但图谱事实非空 → 同样放行（与 reflect_edge 同判据）
    st2 = _state(question="四君子汤有什么禁忌？", intent="relation", evidence=[], low_confidence=True,
                 graph_facts=[{"source": "四君子汤", "relation": "禁忌", "target": "对方剂成分过敏者禁用"}])
    assert safety(st2)["safety_flag"] == "ok"


def _round_fuse(state, rounds):
    """轮次判别 fuse：第 1 轮判定证据不足，第 2 轮证据充分。只返回更新 key。"""
    rounds["n"] += 1
    if rounds["n"] == 1:
        return {"evidence": [], "confidence": 0.0, "low_confidence": True,
                "trace": [{"step": "rerank", "status": "知识库未匹配"}]}
    return {"evidence": [{"chunk_id": "x", "score": 0.8}], "confidence": 0.8, "low_confidence": False,
            "trace": [{"step": "rerank", "status": "证据充分，正常生成"}]}


def _round_retrieve(state, rounds):
    """轮次判别 retrieve：第 1 轮向量/图谱均未命中（构造首轮不足），第 2 轮补查命中图谱事实。"""
    rounds["n"] += 1
    if rounds["n"] == 1:
        return {"vector_hits": [], "graph_facts": [], "trace": [{"step": "retrieve"}]}
    return {"vector_hits": [], "graph_facts": [{"source": "四君子汤", "relation": "禁忌",
            "target": "对方剂成分过敏者禁用"}], "trace": [{"step": "retrieve"}]}


def test_full_graph_reflect_then_recover(monkeypatch):
    # demo case：首轮检索不足 → reflect 改写 → 第二轮补查成功 → ok
    rounds = {"n": 0}
    ret_rounds = {"n": 0}
    monkeypatch.setattr(wmod, "fuse", lambda state: _round_fuse(state, rounds))
    monkeypatch.setattr(wmod, "understand", lambda state: {"intent": "relation",
        "entity_names": ["四君子汤"], "rewritten_query": "四君子汤 禁忌", "trace": [{"step": "understand"}]})
    monkeypatch.setattr(wmod, "retrieve", lambda state: _round_retrieve(state, ret_rounds))
    monkeypatch.setattr(wmod, "reflect", lambda state: {"reflect_count": state["reflect_count"] + 1,
        "rewritten_query": "四君子汤 使用注意", "trace": [{"step": "reflect"}]})
    monkeypatch.setattr(wmod, "context", lambda state: {"prompt": "P"})

    g = wmod.build_agent().compile()
    final = g.invoke(_state(question="四君子汤有什么禁忌？"))
    assert final["reflect_count"] == 1
    assert final["graph_facts"]                 # 次轮检索确实命中图谱（证明 reflect 后补查真的发生）
    assert final["safety_flag"] == "ok"          # 图谱补充后放行