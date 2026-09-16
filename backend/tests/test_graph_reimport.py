"""图谱 re-import 端点（真实 seed 驱动的幂等）；neighbors 去重与 2-hop 白名单过滤（fake graph）。"""
import pytest

import app.db as dbmod
from app.api import graph_api
from app.graph import importer
from app.graph.extractor import VALID_RELATIONS


@pytest.fixture(autouse=True)
def _db(monkeypatch):
    eng = dbmod._make_engine("sqlite:///:memory:")
    dbmod.init_db(eng)                      # 建表 + seed 三用户（re-import 鉴权用）
    monkeypatch.setattr(dbmod, "_engine", eng)


def _auth(client) -> dict:
    """登录 admin 取 Bearer 头（POST /api/graph/import 已挂 current_user）。"""
    tok = client.post("/api/auth/login",
                      json={"username": "admin", "password": "admin123"}).json()["token"]
    return {"Authorization": f"Bearer {tok}"}


class RecordingGraph:
    """记录 execute_write 的 (cypher, params) 序列，不连 Neo4j。"""

    def __init__(self):
        self.calls: list[tuple] = []

    def execute_write(self, cypher: str, **params) -> None:
        self.calls.append((cypher, tuple(sorted(params.items()))))


def test_import_seed_idempotent_statements(monkeypatch):
    """真实 import_seed 连跑两轮，MERGE 语句序列必须逐字一致（幂等性非恒真断言）。"""
    g = RecordingGraph()
    monkeypatch.setattr(importer, "get_graph", lambda: g)
    stats = importer.import_seed()
    first = list(g.calls)
    g.calls.clear()
    importer.import_seed()
    assert g.calls == first            # 第二轮语句序列与第一轮一致（幂等）
    assert stats == {"nodes": 33, "edges": 32}


def test_reimport_endpoint_returns_imported_counts(client, monkeypatch):
    """POST /api/graph/import 契约：200 + {"imported":{nodes,edges}}。

    经 importer.get_graph 注入 RecordingGraph，驱动真实 import_seed（不连 Neo4j）；
    语句级幂等由 test_import_seed_idempotent_statements 覆盖。
    """
    g = RecordingGraph()
    monkeypatch.setattr(importer, "get_graph", lambda: g)
    r = client.post("/api/graph/import", headers=_auth(client))
    assert r.status_code == 200
    assert r.json() == {"imported": {"nodes": 33, "edges": 32}}
    assert g.calls  # 端点确实驱动了 seed 写入


def test_reimport_requires_token(client, monkeypatch):
    """写端点须登录：未带 token 一律 401。"""
    monkeypatch.setattr(importer, "get_graph", lambda: RecordingGraph())
    assert client.post("/api/graph/import").status_code == 401


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
    # 2-hop 关系白名单 Cypher 守卫（字符串层面防白名单/语法回归）
    assert "ALL(r IN relationships(p)" in captured["cypher"] and "'组成'" in captured["cypher"]
    # 白名单须由 VALID_RELATIONS 全量构造（防退回硬编码列表导致「抽取侧加关系、浏览侧静默失联」）
    assert all(f"'{rel}'" in captured["cypher"] for rel in VALID_RELATIONS)