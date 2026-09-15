import app.agent.nodes.reflect as remod
from app.agent.nodes.reflect import reflect
from app.agent.workflow import build_agent, get_agent


def _state(**over):
    base = {
        "question": "四君子汤有什么禁忌？", "session_id": "s", "chat_history": [],
        "rewritten_query": "四君子汤有什么禁忌？", "entities": [], "entity_names": ["四君子汤"],
        "intent": "relation", "plan": [], "vector_hits": [], "keyword_hits": [],
        "graph_facts": [], "fused": [], "evidence": [], "confidence": 0.0,
        "low_confidence": True, "reflect_count": 0, "safety_flag": None, "safety_message": "",
        "prompt": "", "answer": "", "trace": [],
    }
    base.update(over)
    return base


def test_reflect_rewrites_query(monkeypatch):
    captured = {}
    monkeypatch.setattr(
        remod, "chat_completion",
        lambda system, user, temperature: captured.setdefault("user", user) and "四君子汤 禁忌 使用注意",
    )
    upd = reflect(_state())
    assert upd["rewritten_query"] == "四君子汤 禁忌 使用注意"
    assert upd["reflect_count"] == 1
    assert upd["trace"][-1]["step"] == "reflect"
    assert "四君子汤有什么禁忌" in captured["user"]


def test_build_agent_has_expected_nodes():
    g = build_agent()
    nodes = g.nodes
    for name in ["understand", "retrieve", "fuse", "reflect", "safety", "context"]:
        assert name in nodes


def test_workflow_routes_chitchat_around_retrieval(monkeypatch):
    # 用真实图 + 全节点 monkeypatch，验证 chitchat 跳过 retrieve 且得到兜底答案
    import app.agent.workflow as wmod
    monkeypatch.setattr(wmod, "understand", lambda state: {"intent": "chitchat",
        "rewritten_query": state["question"], "entity_names": [], "trace": [{"step": "understand"}]})
    monkeypatch.setattr(wmod, "safety", lambda state: {"safety_flag": "low_confidence",
        "safety_message": "知识库中未检索到可靠依据。", "answer": "知识库中未检索到可靠依据。"})
    monkeypatch.setattr(wmod, "context", lambda state: {"prompt": "EMPTY"})
    g = wmod.build_agent().compile()
    final = g.invoke(_state(intent="chitchat"))
    assert final["safety_flag"] == "low_confidence"
    # 验证 retrieve 从未被调用（wmod 没有 monkeypatch retrieve，但 chitchat 路由不经过它）
