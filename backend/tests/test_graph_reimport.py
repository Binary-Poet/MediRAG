"""图谱 re-import 端点（幂等）；neighbors 去重与 2-hop 白名单过滤（fake graph）。"""
import pytest

from app.api import graph_api
from app.graph.importer import import_seed


class FakeWriteGraph:
    def __init__(self):
        self.calls = 0

    def execute_write(self, cypher: str, **params):
        self.calls += 1


def test_reimport_calls_seed(monkeypatch):
    api = FakeWriteGraph()
    monkeypatch.setattr(graph_api, "get_graph", lambda: api)
    monkeypatch.setattr("app.api.graph_api.import_seed", lambda *a, **k: {"nodes": 33, "edges": 32})
    r = graph_api.reimport()
    assert r["imported"]["nodes"] == 33
    assert api.calls == 0  # 幂等 seed 走 import_seed 自身的 MERGE，不额外写


def _rows(hop):
    """模拟 run_read 返回（1-hop 两跳混合）。"""
    if hop == 1:
        return [
            {"source": "四君子汤", "relation": "组成", "target": "人参",
             "source_type": "方剂", "target_type": "中药",
             "source_status": "已发布", "target_status": "已发布", "status": "已发布"},
            {"source": "四君子汤", "relation": "组成", "target": "白术",
             "source_type": "方剂", "target_type": "中药",
             "source_status": "已发布", "target_status": "已发布", "status": "已发布"},
            {"source": "人参", "relation": "功效", "target": "大补元气",
             "source_type": "中药", "target_type": "功效",
             "source_status": "已发布", "target_status": "已发布", "status": "候选"},  # 候选边
        ]
    return _rows(1)


def test_neighbors_dedup_and_filter(monkeypatch):
    captured = {}

    def fake_read(cypher: str, **params):
        captured["cypher"] = cypher
        return _rows(params.get("hop", 2))

    class G:
        def run_read(self, cypher, **params):
            return fake_read(cypher, **params)

    monkeypatch.setattr(graph_api, "get_graph", lambda: G())
    r = graph_api.neighbors(name="四君子汤", hop=1)
    # 节点去重
    names = [n["name"] for n in r["nodes"]]
    assert len(names) == len(set(names))
    # 候选边不进入 result
    assert all(l["status"] == "已发布" for l in r["links"])
    assert "大补元气" not in [n["name"] for n in r["nodes"]]


def test_reimport_idempotent_via_testclient(client, monkeypatch):
    monkeypatch.setattr("app.api.graph_api.import_seed",
                        lambda *a, **k: {"nodes": 33, "edges": 32})
    r1 = client.post("/api/graph/import")
    r2 = client.post("/api/graph/import")
    assert r1.status_code == 200 and r2.status_code == 200
    assert r1.json() == r2.json()