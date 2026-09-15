"""图谱 API 测试：fake graph client（记录 cypher），无真实 Neo4j。"""
import app.api.graph_api as gmod


class FakeGraph:
    def __init__(self, rows=None):
        self.rows = rows or []
        self.calls = []

    def execute_write(self, cypher, **params):
        self.calls.append((cypher, params))

    def run_read(self, cypher, **params):
        self.calls.append((cypher, params))
        return self.rows


def _use(monkeypatch, fake):
    monkeypatch.setattr(gmod, "get_graph", lambda: fake)


def test_search_returns_items(client, monkeypatch):
    _use(monkeypatch, FakeGraph(rows=[{"name": "四君子汤", "type": "方剂", "alias": "", "status": "已发布"}]))
    resp = client.get("/api/graph/search", params={"entity": "四君子"})
    assert resp.status_code == 200
    assert resp.json()["items"][0]["name"] == "四君子汤"


def test_neighbors_returns_nodes_and_links(client, monkeypatch):
    rows = [{"source": "四君子汤", "relation": "组成", "target": "人参",
             "source_type": "方剂", "target_type": "中药", "status": "已发布"}]
    _use(monkeypatch, FakeGraph(rows=rows))
    body = client.get("/api/graph/neighbors", params={"name": "四君子汤", "hop": 2}).json()
    ids = {n["name"] for n in body["nodes"]}
    assert ids == {"四君子汤", "人参"}
    assert body["links"][0]["relation"] == "组成"


def test_candidates_lists_pending_only(client, monkeypatch):
    rows = [{"source": "归脾汤", "relation": "组成", "target": "远志",
             "source_type": "方剂", "target_type": "中药", "status": "候选",
             "source_doc": "内科讲义.md"}]
    _use(monkeypatch, FakeGraph(rows=rows))
    resp = client.get("/api/graph/candidates").json()
    assert resp["edges"][0]["target"] == "远志"
    assert resp["edges"][0]["source_doc"] == "内科讲义.md"


def test_approve_sets_published(client, monkeypatch):
    fake = FakeGraph()
    _use(monkeypatch, fake)
    resp = client.post("/api/graph/candidates/approve",
                       json={"kind": "edge", "source": "归脾汤", "relation": "组成", "target": "远志"})
    assert resp.status_code == 200
    cypher, params = fake.calls[-1]
    assert "已发布" in cypher and params["s"] == "归脾汤"


def test_approve_node(client, monkeypatch):
    fake = FakeGraph()
    _use(monkeypatch, fake)
    resp = client.post("/api/graph/candidates/approve", json={"kind": "node", "name": "远志"})
    assert resp.status_code == 200
    cypher, params = fake.calls[-1]
    assert params["name"] == "远志" and "已发布" in cypher


def test_entity_detail_404(client, monkeypatch):
    _use(monkeypatch, FakeGraph(rows=[]))
    assert client.get("/api/graph/entities/不存在").status_code == 404