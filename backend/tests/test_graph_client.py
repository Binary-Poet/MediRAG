"""图谱客户端测试：driver 注入 fake，不连真实 Neo4j。"""
from unittest.mock import MagicMock

import pytest

from app.graph.neo4j_client import GraphClient


def _rx(*rows):
    m = MagicMock(name="result")
    m.data.return_value = list(rows)
    return m


def _fake_driver(rx):
    driver = MagicMock()
    session = MagicMock()
    session.run.return_value = rx
    driver.session.return_value.__enter__.return_value = session
    return driver


def test_all_entities_returns_name_alias_type():
    driver = _fake_driver(_rx({"name": "人参", "alias": "园参、山参", "type": "中药"}))
    c = GraphClient("bolt://x", "u", "p", driver=driver)

    ents = c.all_entities()

    assert ents == [{"name": "人参", "alias": "园参、山参", "type": "中药"}]
    session = driver.session.return_value.__enter__.return_value
    cypher = session.run.call_args.args[0]
    assert "status = '已发布'" in cypher


def test_neighbors_returns_facts_and_filters_status():
    driver = _fake_driver(_rx({"source": "四君子汤", "relation": "组成",
                               "target": "人参", "source_type": "方剂", "target_type": "中药"}))
    c = GraphClient("bolt://x", "u", "p", driver=driver)

    facts = c.neighbors(["四君子汤"], hop=1)

    assert facts[0]["relation"] == "组成"
    session = driver.session.return_value.__enter__.return_value
    kwargs = session.run.call_args.kwargs
    assert kwargs["names"] == ["四君子汤"]


def test_neighbors_filters_candidate_edges():
    """C1：问答图谱只取已发布边，候选边（两端节点已发布时）不得泄漏。"""
    driver = _fake_driver(_rx())
    c = GraphClient("bolt://x", "u", "p", driver=driver)

    c.neighbors(["四君子汤"], hop=1)

    cypher = driver.session.return_value.__enter__.return_value.run.call_args.args[0]
    assert "WITH r WHERE r.status = '已发布'" in cypher
    assert "a.status = '已发布'" in cypher and "b.status = '已发布'" in cypher
    assert "r.status AS status" in cypher


def test_neighbors_empty_names_returns_empty():
    c = GraphClient("bolt://x", "u", "p", driver=MagicMock())
    assert c.neighbors([], hop=1) == []


def test_neighbors_clamps_hop_to_1_2():
    driver = _fake_driver(_rx())
    c = GraphClient("bolt://x", "u", "p", driver=driver)
    c.neighbors(["人参"], hop=5)
    cypher = driver.session.return_value.__enter__.return_value.run.call_args.args[0]
    assert "[*1..2]" in cypher


def test_neighbors_restricts_relation_whitelist():
    """问答路 2 跳遍历必须与浏览路同源收紧：中间边只允许 VALID_RELATIONS（防 fan-out 噪声）。"""
    driver = _fake_driver(_rx())
    c = GraphClient("bolt://x", "u", "p", driver=driver)
    c.neighbors(["四君子汤"], hop=2)
    cypher = driver.session.return_value.__enter__.return_value.run.call_args.args[0]
    assert "ALL(r IN relationships(p) WHERE type(r) IN [" in cypher
    for rel in ("组成", "主治", "功效", "禁忌", "表现"):
        assert f"'{rel}'" in cypher


# ===== Task 6（查询分解方案）：定向路径模板 =====

def test_directed_paths_symptom_to_formula_counts_cooccurrence():
    """症状→证候→方剂：按多症状共现计数排序（例 2/5 的「共同指向」推理）。"""
    driver = _fake_driver(_rx({"source": "心血虚", "relation": "主治", "target": "归脾汤", "hit": 3}))
    c = GraphClient("bolt://x", "u", "p", driver=driver)

    facts = c.directed_paths("symptom_to_formula", ["胸痛", "心悸", "失眠"])

    assert facts == [{"source": "心血虚", "relation": "主治", "target": "归脾汤", "hit": 3,
                      "path_template": "symptom_to_formula"}]
    session = driver.session.return_value.__enter__.return_value
    cypher = session.run.call_args.args[0]
    assert "r1:表现" in cypher and "r2:主治" in cypher
    assert "count(DISTINCT s.name)" in cypher          # 共现计数
    assert "ORDER BY hit DESC" in cypher
    assert cypher.count("已发布") >= 5                  # 节点与边都只查已发布（候选不泄漏）
    assert session.run.call_args.kwargs["names"] == ["胸痛", "心悸", "失眠"]


def test_directed_paths_formula_mechanism_expands_effect_edges():
    """方剂→组成→中药（+中药→功效）：机制链展开为组成/功效两类事实。"""
    driver = _fake_driver(_rx({"source": "麻黄", "relation": "组成", "target": "麻黄",
                               "eff_source": "麻黄", "eff_target": "发汗解表"}))
    c = GraphClient("bolt://x", "u", "p", driver=driver)

    facts = c.directed_paths("formula_mechanism", ["麻黄汤"])

    assert facts == [
        {"source": "麻黄", "relation": "组成", "target": "麻黄", "path_template": "formula_mechanism"},
        {"source": "麻黄", "relation": "功效", "target": "发汗解表", "path_template": "formula_mechanism"},
    ]
    cypher = driver.session.return_value.__enter__.return_value.run.call_args.args[0]
    assert "r1:组成" in cypher and "r2:功效" in cypher
    assert "OPTIONAL MATCH" in cypher                    # 无功效边的中药也要返回组成事实


def test_directed_paths_unknown_template_or_empty_names_returns_empty():
    c = GraphClient("bolt://x", "u", "p", driver=MagicMock())
    assert c.directed_paths("bogus", ["X"]) == []
    assert c.directed_paths("symptom_to_formula", []) == []