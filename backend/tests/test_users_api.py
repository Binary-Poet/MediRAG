"""账户管理：列表含 seed；新建/删除；用户名唯一 409；角色枚举 422。"""
import pytest

import app.db as dbmod


@pytest.fixture(autouse=True)
def _db(monkeypatch):
    # conftest 的裸 TestClient(app) 不进入 context manager，startup 不会触发，
    # 所以这里显式 init_db：建表 + seed 三个演示账号。
    eng = dbmod._make_engine("sqlite:///:memory:")
    monkeypatch.setattr(dbmod, "_engine", eng)
    dbmod.init_db(eng)


def _auth(client, username: str = "admin") -> dict:
    """账户管理接口有登录 + 管理员守卫——先登录取 token。"""
    tok = client.post("/api/auth/login",
                      json={"username": username, "password": "admin123"}).json()["token"]
    return {"Authorization": f"Bearer {tok}"}


def test_list_users(client):
    assert client.get("/api/users").status_code == 401  # 未登录不可读
    r = client.get("/api/users", headers=_auth(client))
    assert r.status_code == 200
    names = {u["username"] for u in r.json()["items"]}
    assert {"admin", "user1", "tcm1"} <= names


def test_create_and_delete(client):
    h = _auth(client)
    r = client.post("/api/users", headers=h, json={
        "username": "doc2", "display_name": "李大夫",
        "role": "中医药从业者", "password": "doc2123"})
    assert r.status_code == 200
    uid = r.json()["id"]
    assert client.post("/api/users", headers=h, json={
        "username": "doc2", "display_name": "李大夫",
        "role": "中医药从业者", "password": "doc2123"}).status_code == 409
    assert client.delete(f"/api/users/{uid}", headers=h).status_code == 200
    assert client.delete(f"/api/users/{uid}", headers=h).status_code == 404


def test_role_enum_and_required(client):
    r = client.post("/api/users", headers=_auth(client), json={
        "username": "x1", "display_name": "X", "role": "老板", "password": "x12345"})
    assert r.status_code == 422


def test_non_admin_forbidden(client):
    """账户管理仅限管理员（Ruling T4-2）：知识用户不可增删用户。"""
    h = _auth(client, "user1")
    assert client.get("/api/users", headers=h).status_code == 403
    assert client.post("/api/users", headers=h, json={
        "username": "sneak", "display_name": "S",
        "role": "管理员", "password": "sneak123"}).status_code == 403
    assert client.delete("/api/users/1", headers=h).status_code == 403


def test_admin_cannot_delete_self(client):
    """防系统自锁：不能删除当前登录用户（Ruling T4-2）。"""
    h = _auth(client)
    me = client.get("/api/auth/me", headers=h).json()
    r = client.delete(f"/api/users/{me['id']}", headers=h)
    assert r.status_code == 403
    # admin 仍在（未被删掉）
    names = {u["username"] for u in client.get("/api/users", headers=h).json()["items"]}
    assert "admin" in names