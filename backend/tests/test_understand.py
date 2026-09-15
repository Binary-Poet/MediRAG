import app.agent.nodes.understand as umod
from app.agent.nodes.understand import _parse_understand, understand


def _state(**over):
    base = {
        "question": "四君子汤由哪些中药组成？",
        "session_id": "s1", "chat_history": [], "entity_names": [],
        "entities": [], "intent": "", "plan": [], "trace": [], "reflect_count": 0,
    }
    base.update(over)
    return base


def test_parse_understand_valid_json():
    raw = '{"rewritten_query": "四君子汤的中药组成成分", "entities": [{"name": "四君子汤", "type": "方剂"}], "intent": "relation"}'
    d = _parse_understand(raw)
    assert d["intent"] == "relation"
    assert d["entities"][0]["name"] == "四君子汤"


def test_parse_understand_invalid_returns_none():
    assert _parse_understand("不是 JSON") is None
    assert _parse_understand('{"intent": "bogus"}') is None


def test_understand_parses_llm_output(monkeypatch):
    monkeypatch.setattr(umod, "get_graph", lambda: _FakeGraph())
    monkeypatch.setattr(
        umod, "chat_completion",
        lambda system, user, temperature: (
            '{"rewritten_query": "四君子汤的中药组成成分", '
            '"entities": [{"name": "四君子汤", "type": "方剂"}], "intent": "relation"}'
        ),
    )
    upd = understand(_state())
    assert upd["intent"] == "relation"
    assert upd["entity_names"] == ["四君子汤"]
    assert upd["trace"][0]["step"] == "understand"


def test_understand_falls_back_to_lexicon_on_garbage(monkeypatch):
    monkeypatch.setattr(umod, "get_graph", lambda: _FakeGraph2())
    monkeypatch.setattr(umod, "chat_completion", lambda *a, **k: "抱歉我不确定")
    upd = understand(_state(question="人参的功效是什么"))
    assert upd["intent"] == "complex"          # 词典命中实体 → 视为综合问题
    assert "人参" in upd["entity_names"]


class _FakeGraph:
    def all_entities(self):
        return [{"name": "四君子汤", "alias": "", "type": "方剂"}]


class _FakeGraph2:
    def all_entities(self):
        return [{"name": "人参", "alias": "园参、山参", "type": "中药"}]