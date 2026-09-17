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