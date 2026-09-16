"""会话管理接口：列表统计 / 收藏过滤 / 删除 / 完整回放 / 越权一律 404。

id 假设：`_seed_users` 按 admin → user1 → tcm1 顺序插入，sqlite 自增即
admin=1、user1=2。因此 `_seed()` 把会话建在 user_id=1，而 `other` 夹具用
user1（id=2）验证越权。若将来调整 seed 顺序，这些用例需同步。
"""
import pytest

import app.db as dbmod
from app.services import chat_session as cs


@pytest.fixture(autouse=True)
def _db(monkeypatch):
    eng = dbmod._make_engine("sqlite:///:memory:")
    dbmod.init_db(eng)
    monkeypatch.setattr(dbmod, "_engine", eng)


@pytest.fixture
def admin(client) -> dict:
    tok = client.post("/api/auth/login",
                      json={"username": "admin", "password": "admin123"}).json()["token"]
    return {"Authorization": f"Bearer {tok}"}


@pytest.fixture
def other(client) -> dict:
    """user1 的头：越权用例（admin 的会话对 user1 不可见）。"""
    tok = client.post("/api/auth/login",
                      json={"username": "user1", "password": "admin123"}).json()["token"]
    return {"Authorization": f"Bearer {tok}"}


def _seed() -> str:
    a = cs.create_session(1, "四君子汤由哪些中药组成？")
    cs.append_message(a, "user", "四君子汤由哪些中药组成？")
    cs.append_message(a, "assistant", "人参、白术、茯苓、炙甘草", payload={
        "trace": [{"step": "understand"}],
        "references": [{"chunk_id": "c1", "title": "四君子汤", "doc_name": "中药方剂学基础",
                        "chapter": "第1节", "page_no": 1, "score": 0.9}],
        "graph_facts": [{"source": "四君子汤", "relation": "组成", "target": "人参",
                         "source_type": "方剂", "target_type": "中药"}],
        "safety": None})
    return a


def test_list_returns_totals_and_counts(client, admin):
    a = _seed()
    cs.create_session(1, "脾气虚常见哪些症状和方剂？")
    r = client.get("/api/chat/sessions", headers=admin)
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 2
    assert body["favorite_total"] == 0
    item = next(x for x in body["sessions"] if x["session_id"] == a)
    assert item["message_count"] == 2
    assert item["favorite"] is False
    assert item["updated_at"].endswith("Z")


def test_list_requires_auth(client):
    assert client.get("/api/chat/sessions").status_code == 401


def test_write_and_replay_endpoints_require_auth(client):
    """PATCH / DELETE / messages 三个端点无凭证一律 401。

    这些正是 require_admin/current_user 改造时最容易漏挂依赖的地方，补上鉴权断言。
    """
    assert client.patch("/api/chat/sessions/x", json={"favorite": True}).status_code == 401
    assert client.delete("/api/chat/sessions/x").status_code == 401
    assert client.get("/api/chat/sessions/x/messages").status_code == 401


def test_favorite_toggle_then_filter(client, admin):
    a = _seed()
    r = client.patch(f"/api/chat/sessions/{a}", json={"favorite": True}, headers=admin)
    assert r.status_code == 200
    assert r.json() == {"session_id": a, "favorite": True}
    only = client.get("/api/chat/sessions?favorite=true", headers=admin).json()
    assert only["total"] == 1
    assert only["favorite_total"] == 1
    assert [x["session_id"] for x in only["sessions"]] == [a]
    # 取消后筛选为空
    client.patch(f"/api/chat/sessions/{a}", json={"favorite": False}, headers=admin)
    assert client.get("/api/chat/sessions?favorite=true", headers=admin).json()["sessions"] == []


def test_delete_then_404(client, admin):
    a = _seed()
    assert client.delete(f"/api/chat/sessions/{a}", headers=admin).status_code == 200
    assert client.get("/api/chat/sessions", headers=admin).json()["total"] == 0
    assert client.delete(f"/api/chat/sessions/{a}", headers=admin).status_code == 404


def test_messages_replay_full_payload(client, admin):
    a = _seed()
    r = client.get(f"/api/chat/sessions/{a}/messages", headers=admin)
    assert r.status_code == 200
    msgs = r.json()["messages"]
    assert [m["role"] for m in msgs] == ["user", "assistant"]
    assert msgs[0]["payload"] is None
    p = msgs[1]["payload"]
    assert p["graph_facts"][0]["target"] == "人参"
    assert p["references"][0]["chunk_id"] == "c1"
    assert p["trace"] == [{"step": "understand"}]


def test_cross_user_access_all_404(client, admin, other):
    a = _seed()
    assert client.patch(f"/api/chat/sessions/{a}", json={"favorite": True},
                        headers=other).status_code == 404
    assert client.delete(f"/api/chat/sessions/{a}", headers=other).status_code == 404
    assert client.get(f"/api/chat/sessions/{a}/messages", headers=other).status_code == 404
    assert client.get("/api/chat/sessions", headers=other).json()["total"] == 0
    # 未被越权操作影响
    assert client.get(f"/api/chat/sessions/{a}/messages", headers=admin).status_code == 200
