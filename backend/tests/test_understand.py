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


def test_understand_reads_inference_config(monkeypatch):
    monkeypatch.setattr(umod, "get_graph", lambda: _FakeGraph())
    seen = {}

    def _mock(*a, **k):
        seen["temperature"] = k.get("temperature")
        seen["model"] = k.get("model")
        return ('{"rewritten_query": "四君子汤的中药组成成分", '
                '"entities": [{"name": "四君子汤", "type": "方剂"}], "intent": "relation"}')

    monkeypatch.setattr(umod, "chat_completion", _mock)
    upd = understand(_state(inference={"query_temp": 1.7, "model": "qwen-plus"}))
    assert seen["temperature"] == 1.7          # query_temp 生效（默认 0.1 被覆盖）
    assert seen["model"] == "qwen-plus"        # 模型透传
    assert upd["intent"] == "relation"


class _FakeGraph:
    def all_entities(self):
        return [{"name": "四君子汤", "alias": "", "type": "方剂"}]


class _FakeGraph2:
    def all_entities(self):
        return [{"name": "人参", "alias": "园参、山参", "type": "中药"}]


class _FakeGraphEmpty:
    def all_entities(self):
        return []


# ===== Task 1（查询分解方案）：sub_queries / compare 意图 / 降级修复 =====

def test_parse_understand_sub_queries_and_compare():
    raw = ('{"rewritten_query": "麻黄汤和桂枝汤在主治和配伍上的区别", '
           '"sub_queries": [{"query": "麻黄汤 组成 主治 证候", "entities": ["麻黄汤"]},'
           '                 {"query": "桂枝汤 组成 主治 证候", "entities": ["桂枝汤"]}], '
           '"entities": [{"name": "麻黄汤", "type": "方剂"}, {"name": "桂枝汤", "type": "方剂"}], '
           '"intent": "compare"}')
    d = _parse_understand(raw)
    assert d["intent"] == "compare"
    assert len(d["sub_queries"]) == 2
    assert d["sub_queries"][0]["entities"] == ["麻黄汤"]


def test_parse_understand_invalid_intent_keeps_output():
    """非法意图不再整包丢弃：结构合法时保留输出、intent 置 None 待映射（例 7）。"""
    raw = ('{"rewritten_query": "风寒感冒和风热感冒的辨证要点对比", '
           '"entities": [{"name": "风寒感冒", "type": "证候"}, {"name": "风热感冒", "type": "证候"}], '
           '"intent": "comparison"}')
    d = _parse_understand(raw)
    assert d is not None
    assert d["intent"] is None                      # 非法 → 待映射，而非丢弃
    assert d["rewritten_query"] == "风寒感冒和风热感冒的辨证要点对比"
    assert [e["name"] for e in d["entities"]] == ["风寒感冒", "风热感冒"]


def test_understand_maps_invalid_intent_to_compare(monkeypatch):
    """LLM 输出 intent=comparison 且问题含比较词 → 映射 compare，其余输出保留。"""
    monkeypatch.setattr(umod, "get_graph", lambda: _FakeGraphEmpty())
    monkeypatch.setattr(
        umod, "chat_completion",
        lambda system, user, temperature: (
            '{"rewritten_query": "麻黄汤和桂枝汤主治配伍对比", '
            '"entities": [{"name": "麻黄汤", "type": "方剂"}, {"name": "桂枝汤", "type": "方剂"}], '
            '"intent": "comparison"}'
        ),
    )
    upd = understand(_state(question="麻黄汤和桂枝汤在主治和配伍上有什么区别？"))
    assert upd["intent"] == "compare"
    assert upd["rewritten_query"] == "麻黄汤和桂枝汤主治配伍对比"
    assert upd["entity_names"] == ["麻黄汤", "桂枝汤"]   # LLM 输出未被丢弃


def test_understand_maps_invalid_intent_to_complex(monkeypatch):
    """非法意图且问题无比较词 → 映射 complex。"""
    monkeypatch.setattr(umod, "get_graph", lambda: _FakeGraphEmpty())
    monkeypatch.setattr(
        umod, "chat_completion",
        lambda system, user, temperature: (
            '{"rewritten_query": "人参的功效", '
            '"entities": [{"name": "人参", "type": "中药"}], "intent": "bogus"}'
        ),
    )
    upd = understand(_state(question="人参的功效是什么"))
    assert upd["intent"] == "complex"
    assert upd["entity_names"] == ["人参"]


def test_understand_sub_queries_passthrough_and_trace(monkeypatch):
    monkeypatch.setattr(umod, "get_graph", lambda: _FakeGraphEmpty())
    monkeypatch.setattr(
        umod, "chat_completion",
        lambda system, user, temperature: (
            '{"rewritten_query": "麻黄汤和桂枝汤的区别", '
            '"sub_queries": [{"query": "麻黄汤 组成 主治", "entities": ["麻黄汤"]},'
            '                 {"query": "桂枝汤 组成 主治", "entities": ["桂枝汤"]}], '
            '"entities": [{"name": "麻黄汤", "type": "方剂"}, {"name": "桂枝汤", "type": "方剂"}], '
            '"intent": "compare"}'
        ),
    )
    upd = understand(_state(question="麻黄汤和桂枝汤有什么区别？"))
    assert len(upd["sub_queries"]) == 2
    assert upd["sub_queries"][0]["query"] == "麻黄汤 组成 主治"
    assert upd["trace"][0]["sub_query_n"] == 2


def test_understand_sub_queries_fallback_single(monkeypatch):
    """LLM 未输出 sub_queries → 回落为单查询包装（向后兼容）。"""
    monkeypatch.setattr(umod, "get_graph", lambda: _FakeGraph())
    monkeypatch.setattr(
        umod, "chat_completion",
        lambda system, user, temperature: (
            '{"rewritten_query": "四君子汤的中药组成成分", '
            '"entities": [{"name": "四君子汤", "type": "方剂"}], "intent": "relation"}'
        ),
    )
    upd = understand(_state())
    assert upd["sub_queries"] == [{"query": "四君子汤的中药组成成分", "entities": ["四君子汤"]}]
    assert upd["trace"][0]["sub_query_n"] == 1


def test_understand_caps_sub_queries_at_3(monkeypatch):
    monkeypatch.setattr(umod, "get_graph", lambda: _FakeGraphEmpty())
    subs = [{"query": f"子查询{i}", "entities": []} for i in range(5)]
    monkeypatch.setattr(
        umod, "chat_completion",
        lambda system, user, temperature: (
            '{"rewritten_query": "多实体", "sub_queries": ' + str(subs).replace("'", '"') +
            ', "entities": [], "intent": "concept"}'
        ),
    )
    upd = understand(_state(question="多实体问题"))
    assert len(upd["sub_queries"]) == 3                # 硬上限 3


def test_understand_fallback_no_entity_is_concept(monkeypatch):
    """词典兜底无实体 → concept（放行检索），不再 chitchat 拒答（「如何养生」回归）。"""
    monkeypatch.setattr(umod, "get_graph", lambda: _FakeGraphEmpty())
    monkeypatch.setattr(umod, "chat_completion", lambda *a, **k: "抱歉我不确定")
    upd = understand(_state(question="如何养生"))
    assert upd["intent"] == "concept"
    assert upd["sub_queries"] == [{"query": "如何养生", "entities": []}]
    assert upd["trace"][0]["sub_query_n"] == 1


def test_query_understand_prompt_declares_compare_and_wellness_rule():
    """prompt 必须声明 compare 意图与「泛健康话题归 concept 非 chitchat」。"""
    from pathlib import Path
    prompt = (Path(__file__).resolve().parents[1] / "app" / "agent" / "prompts"
              / "query_understand.txt").read_text(encoding="utf-8")
    assert "compare" in prompt
    assert "sub_queries" in prompt
    assert "养生" in prompt