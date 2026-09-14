"""图谱导入测试：注入 fake client，验证 MERGE 计数与哨兵字段。"""
import json
from pathlib import Path

import pytest

from app.graph.importer import import_seed


class FakeGraph:
    def __init__(self):
        self.calls: list[tuple[str, dict]] = []

    def execute_write(self, cypher: str, **params) -> None:
        self.calls.append((cypher, params))


def _seed(tmp_path: Path, nodes: int = 2, edges: int = 1) -> Path:
    p = tmp_path / "seed.json"
    p.write_text(json.dumps({
        "nodes": [
            {"id": "n1", "name": "人参", "type": "中药", "alias": "园参、山参",
             "desc": "补气", "source": "内置数据"},
            {"id": "n2", "name": "四君子汤", "type": "方剂", "alias": "",
             "desc": "益气健脾", "source": "内置数据"},
        ],
        "edges": [{"source": "n2", "relation": "组成", "target": "n1", "note": "组成之一"}],
    }, ensure_ascii=False), encoding="utf-8")
    return p


def test_import_seed_merges_nodes_and_edges(tmp_path):
    g = FakeGraph()
    seed_path = _seed(tmp_path)

    stats = import_seed(g, path=seed_path)

    assert stats == {"nodes": 2, "edges": 1}
    # 节点 MERGE 与边 MERGE 均含 "MERGE"，需按语句前缀区分（见自审记录）
    node_calls = [c for c in g.calls if c[0].startswith("MERGE")]
    edge_calls = [c for c in g.calls if c[0].startswith("MATCH (a")]
    assert len(node_calls) == 2 and len(edge_calls) == 1
    # 节点哨兵：status=已发布 且带 type 属性（实现输出 `status = '已发布'`）
    assert "status = '已发布'" in node_calls[0][0]
    assert node_calls[0][1]["name"] == "人参"
    # 边端点用 name 关联（seed 边以 id 引用，导入前需映射 id -> name）
    assert edge_calls[0][1] == {"s": "四君子汤", "t": "人参", "note": "组成之一"}