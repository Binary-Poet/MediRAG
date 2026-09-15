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
    fake = FakeGraph(rows=[{"name": "四君子汤", "type": "方剂", "alias": "", "status": "已发布"}])
    _use(monkeypatch, fake)
    resp = client.get("/api/graph/search", params={"entity": "四君子"})
    assert resp.status_code == 200
    assert resp.json()["items"][0]["name"] == "四君子汤"
    cypher, _ = fake.calls[0]
    assert "n.status IN ['已发布','候选']" in cypher


def test_neighbors_returns_nodes_and_links(client, monkeypatch):
    rows = [{"source": "四君子汤", "relation": "组成", "target": "人参",
             "source_type": "方剂", "target_type": "中药",
             "source_status": "已发布", "target_status": "已发布", "status": "已发布"}]
    fake = FakeGraph(rows=rows)
    _use(monkeypatch, fake)
    body = client.get("/api/graph/neighbors", params={"name": "四君子汤", "hop": 2}).json()
    ids = {n["name"] for n in body["nodes"]}
    assert ids == {"四君子汤", "人参"}
    assert body["links"][0]["relation"] == "组成"
    # links.status 取边状态（r.status），节点状态另取 source_status/target_status
    cypher, _ = fake.calls[-1]
    assert "r.status AS status" in cypher
    assert "startNode(r).status AS source_status" in cypher
    assert "endNode(r).status AS target_status" in cypher


def test_neighbors_mixed_status_assigns_per_endpoint(client, monkeypatch):
    rows = [{"source": "四君子汤", "relation": "组成", "target": "人参",
             "source_type": "方剂", "target_type": "中药",
             "source_status": "已发布", "target_status": "候选", "status": "候选"}]
    _use(monkeypatch, FakeGraph(rows=rows))
    body = client.get("/api/graph/neighbors", params={"name": "四君子汤"}).json()
    statuses = {n["name"]: n["status"] for n in body["nodes"]}
    assert statuses["四君子汤"] == "已发布"
    assert statuses["人参"] == "候选"


def test_neighbors_link_status_reflects_edge_status(client, monkeypatch):
    """C3：两端节点均已发布、边为候选时，links[0].status 应反映「边状态」而非源节点状态。"""
    rows = [{"source": "四君子汤", "relation": "组成", "target": "人参",
             "source_type": "方剂", "target_type": "中药",
             "source_status": "已发布", "target_status": "已发布", "status": "候选"}]
    _use(monkeypatch, FakeGraph(rows=rows))
    body = client.get("/api/graph/neighbors", params={"name": "四君子汤"}).json()
    assert body["links"][0]["status"] == "候选"
    assert {n["status"] for n in body["nodes"]} == {"已发布"}


def test_candidates_lists_pending_only(client, monkeypatch):
    rows = [{"source": "归脾汤", "relation": "组成", "target": "远志",
             "source_type": "方剂", "target_type": "中药", "status": "候选",
             "source_doc": "内科讲义.md"}]
    fake = FakeGraph(rows=rows)
    _use(monkeypatch, fake)
    resp = client.get("/api/graph/candidates").json()
    assert resp["edges"][0]["target"] == "远志"
    assert resp["edges"][0]["source_doc"] == "内科讲义.md"
    cypher, _ = fake.calls[0]
    assert "r.status = '候选'" in cypher


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


def test_reject_node_requires_name(client, monkeypatch):
    fake = FakeGraph()
    _use(monkeypatch, fake)
    resp = client.post("/api/graph/candidates/reject", json={"kind": "node"})
    assert resp.status_code == 422
    assert fake.calls == []


def test_reject_edge_requires_fields(client, monkeypatch):
    fake = FakeGraph()
    _use(monkeypatch, fake)
    resp = client.post("/api/graph/candidates/reject",
                       json={"kind": "edge", "source": "归脾汤"})
    assert resp.status_code == 422
    assert fake.calls == []


def test_reject_node_blocked_by_published_edge(client, monkeypatch):
    fake = FakeGraph(rows=[{"n": 1}])
    _use(monkeypatch, fake)
    resp = client.post("/api/graph/candidates/reject", json={"kind": "node", "name": "人参"})
    assert resp.status_code == 409
    assert len(fake.calls) == 1  # 仅引用检查，未执行删除


def test_reject_node_success(client, monkeypatch):
    fake = FakeGraph(rows=[{"n": 0}])
    _use(monkeypatch, fake)
    resp = client.post("/api/graph/candidates/reject", json={"kind": "node", "name": "远志"})
    assert resp.status_code == 200
    cypher, params = fake.calls[-1]
    assert "DETACH DELETE" in cypher
    assert params["name"] == "远志"