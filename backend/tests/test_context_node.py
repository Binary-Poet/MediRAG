"""context 节点测试：compare 意图证据按实体分组，非 compare 保持平铺。"""
import app.agent.nodes.context as cmod


def _ev(title, matched, chunk="c1"):
    return {"chunk_id": chunk, "doc_name": "伤寒论", "chapter": "辨太阳病脉证并治",
            "page_no": 12, "title": title, "text": "原文……", "score": 0.9,
            "matched_queries": matched}


def test_context_groups_compare_evidence_by_entity():
    """compare：证据按子查询/实体分组，共同证据两块中都出现且编号一致（例 1/6 对照可见）。"""
    st = {
        "intent": "compare", "question": "麻黄汤和桂枝汤在主治和配伍上有什么区别？",
        "sub_queries": [{"query": "麻黄汤 组成 主治", "entities": ["麻黄汤"]},
                        {"query": "桂枝汤 组成 主治", "entities": ["桂枝汤"]}],
        "evidence": [_ev("麻黄汤方", [0], "a"), _ev("桂枝汤方", [1], "b"),
                     _ev("太阳病总论", [0, 1], "c")],
        "graph_facts": [{"source": "麻黄汤", "relation": "组成", "target": "麻黄"}],
    }
    prompt = cmod.context(st)["prompt"]

    assert "【麻黄汤】" in prompt and "【桂枝汤】" in prompt
    assert prompt.index("【麻黄汤】") < prompt.index("【桂枝汤】")
    assert prompt.count("[3] 《伤寒论》") == 2      # 共同证据两块各一次，编号不漂移
    assert "麻黄汤 --组成--> 麻黄" in prompt         # 图谱事实仍走模板占位


def test_context_flat_when_not_compare():
    """非 compare（即使多子查询）保持平铺，避免小题大做与编号变化。"""
    st = {
        "intent": "complex", "question": "胸痛心悸失眠该用什么方剂",
        "sub_queries": [{"query": "胸痛 心悸", "entities": ["胸痛"]},
                        {"query": "失眠 方剂", "entities": ["失眠"]}],
        "evidence": [_ev("胸痛", [0], "a"), _ev("失眠", [1], "b")],
        "graph_facts": [],
    }
    prompt = cmod.context(st)["prompt"]

    assert "【麻黄汤】" not in prompt
    assert "[1] 《伤寒论》" in prompt and "[2] 《伤寒论》" in prompt
    assert "（无）" in prompt                        # 图谱事实为空占位


def test_context_compare_without_evidence():
    st = {"intent": "compare", "question": "q",
          "sub_queries": [{"query": "qa", "entities": ["a"]}, {"query": "qb", "entities": ["b"]}],
          "evidence": [], "graph_facts": []}
    prompt = cmod.context(st)["prompt"]
    assert "（无）" in prompt
