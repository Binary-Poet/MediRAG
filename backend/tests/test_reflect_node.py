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


def test_reflect_caps_supplemented_entities(monkeypatch):
    """补实体上限 3：真实环境实测 LLM 会一次性补出 9 个（麻黄/桂枝/芍药/杏仁/甘草…），
    甘草这类泛用药味是图谱枢纽，一带就把酸枣仁汤等无关方剂的事实拖进来。"""
    monkeypatch.setattr(rmod, "get_settings", lambda: _Cfg())
    many = '{"rewritten_query": "q2", "entities": ' + str(
        ["麻黄", "桂枝", "芍药", "杏仁", "甘草", "生姜", "大枣", "太阳伤寒证", "太阳中风证"]
    ).replace("'", '"') + '}'
    monkeypatch.setattr(rmod, "chat_completion", lambda *a, **k: many)
    upd = reflect(_state(entity_names=["麻黄汤"]))
    assert upd["entity_names"] == ["麻黄汤", "麻黄", "桂枝", "芍药"]   # 只收前 3 个新增


def test_reflect_prompt_forbids_inferring_entities(monkeypatch):
    """prompt 必须要求只取原问题中直接出现的实体，禁止凭中医知识推断补全。"""
    from pathlib import Path
    prompt = (Path(__file__).resolve().parents[1] / "app" / "agent" / "prompts"
              / "query_rewrite_reflect.txt").read_text(encoding="utf-8")
    assert "推断" in prompt


def test_reflect_rewrite_reaches_single_sub_query(monkeypatch):
    """单子查询：改写必须替换 sub_queries——retrieve/fuse 优先读 sub_queries，只改
    rewritten_query 等于改写被静默丢弃。真实环境实测「如何养生」被改写为「中医养生方法」
    后下游仍按旧查询精排，置信度停在 0.267 继续拒答（改前同一改写可到 0.55 作答）。"""
    monkeypatch.setattr(rmod, "get_settings", lambda: _Cfg())
    monkeypatch.setattr(rmod, "chat_completion", lambda *a, **k: (
        '{"rewritten_query": "中医养生方法", "entities": []}'))
    upd = reflect(_state(entity_names=["四君子汤"],
                         sub_queries=[{"query": "四君子汤 组成", "entities": ["四君子汤"]}]))
    assert upd["sub_queries"] == [{"query": "中医养生方法", "entities": ["四君子汤"]}]


def test_reflect_rewrite_appends_for_multi_sub_query(monkeypatch):
    """多子查询：追加而非替换——替换会抹掉按实体的扇出（比较型问题的立命之本），
    fuse 取各子查询精排 max 分，追加只增不损。"""
    monkeypatch.setattr(rmod, "get_settings", lambda: _Cfg())
    monkeypatch.setattr(rmod, "chat_completion", lambda *a, **k: (
        '{"rewritten_query": "四君子汤 归脾汤 组成 主治 区别", "entities": []}'))
    subs = [{"query": "四君子汤 组成 主治", "entities": ["四君子汤"]},
            {"query": "归脾汤 组成 主治", "entities": ["归脾汤"]}]
    upd = reflect(_state(entity_names=["四君子汤", "归脾汤"], sub_queries=subs))
    assert upd["sub_queries"][:2] == subs                        # 原扇出原样保留
    assert upd["sub_queries"][2] == {"query": "四君子汤 归脾汤 组成 主治 区别", "entities": []}


def test_reflect_rewrite_sets_sub_queries_when_absent(monkeypatch):
    """老路径/直接构造 state 时无 sub_queries：补一条，下游零特判。"""
    monkeypatch.setattr(rmod, "get_settings", lambda: _Cfg())
    monkeypatch.setattr(rmod, "chat_completion", lambda *a, **k: (
        '{"rewritten_query": "四君子汤 使用注意", "entities": []}'))
    upd = reflect(_state())
    assert upd["sub_queries"] == [{"query": "四君子汤 使用注意", "entities": []}]
