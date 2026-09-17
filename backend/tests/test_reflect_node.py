"""reflect 节点测试：改写查询 + 修正实体（JSON 容忍解析，纯文本回落旧行为）。"""
import app.agent.nodes.reflect as rmod
from app.agent.nodes.reflect import reflect


class _Cfg:
    evidence_min_score = 0.3


def _state(**over):
    base = {
        "question": "四君子汤的组成", "rewritten_query": "四君子汤 组成", "chat_history": [],
        "evidence": [], "confidence": 0.0, "reflect_count": 0, "trace": [],
        "entities": [], "entity_names": [],
    }
    base.update(over)
    return base


def test_reflect_parses_json_query_and_entities(monkeypatch):
    """反思输出带实体 → 合并进 state，第二轮图谱路才用得上（问题 #7 修复）。"""
    monkeypatch.setattr(rmod, "get_settings", lambda: _Cfg())
    monkeypatch.setattr(rmod, "chat_completion", lambda system, user, temperature: (
        '{"rewritten_query": "四君子汤 组成 人参 白术 茯苓", "entities": ["人参", "白术"]}'))
    upd = reflect(_state(entity_names=["四君子汤"]))
    assert upd["rewritten_query"] == "四君子汤 组成 人参 白术 茯苓"
    assert upd["entity_names"] == ["四君子汤", "人参", "白术"]   # 并集保序去重
    assert upd["entities"][1] == {"name": "人参", "type": "", "matched": "人参"}
    assert upd["reflect_count"] == 1
    assert upd["trace"][0]["step"] == "reflect"


def test_reflect_plain_text_falls_back_to_query_only(monkeypatch):
    """LLM 未按 JSON 输出（含旧格式）→ 整段文本即查询，实体不动，链路不中断。"""
    monkeypatch.setattr(rmod, "get_settings", lambda: _Cfg())
    monkeypatch.setattr(rmod, "chat_completion", lambda *a, **k: "四君子汤 使用注意")
    upd = reflect(_state(entity_names=["四君子汤"]))
    assert upd["rewritten_query"] == "四君子汤 使用注意"
    assert "entity_names" not in upd
    assert upd["reflect_count"] == 1


def test_reflect_llm_failure_keeps_previous_query(monkeypatch):
    monkeypatch.setattr(rmod, "get_settings", lambda: _Cfg())

    def _boom(*a, **k):
        raise RuntimeError("llm down")

    monkeypatch.setattr(rmod, "chat_completion", _boom)
    upd = reflect(_state(rewritten_query="四君子汤 组成"))
    assert upd["rewritten_query"] == "四君子汤 组成"
