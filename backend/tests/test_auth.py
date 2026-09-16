"""登录 / 当前用户 / 改密码（seed 用户由 init_db 注入，conftest 已建库）。"""
import hashlib

import pytest

import app.db as dbmod


@pytest.fixture(autouse=True)
def _db(monkeypatch):
    # conftest 的裸 TestClient(app) 不进入 context manager，startup 不会触发，
    # 所以这里显式 init_db：建表 + seed 三个演示账号。
    eng = dbmod._make_engine("sqlite:///:memory:")
    monkeypatch.setattr(dbmod, "_engine", eng)
    dbmod.init_db(eng)


def test_login_admin(client):
    r = client.post("/api/auth/login", json={"username": "admin", "password": "admin123"})
    assert r.status_code == 200
    body = r.json()
    assert body["user"]["username"] == "admin"
    assert body["user"]["role"] == "管理员"
    assert "token" in body


def test_login_bad_password(client):
    r = client.post("/api/auth/login", json={"username": "admin", "password": "wrong"})
    assert r.status_code == 401


def test_me_requires_token(client):
    assert client.get("/api/auth/me").status_code == 401
    tok = client.post("/api/auth/login",
                      json={"username": "user1", "password": "admin123"}).json()["token"]
    r = client.get("/api/auth/me", headers={"Authorization": f"Bearer {tok}"})
    assert r.status_code == 200 and r.json()["username"] == "user1"


def test_change_password(client):
    tok = client.post("/api/auth/login",
                      json={"username": "user1", "password": "admin123"}).json()["token"]
    r = client.put("/api/auth/password", headers={"Authorization": f"Bearer {tok}"},
                   json={"old_password": "admin123", "new_password": "newpass1"})
    assert r.status_code == 200
    assert client.post("/api/auth/login",
                       json={"username": "user1", "password": "newpass1"}).status_code == 200
    assert client.post("/api/auth/login",
                       json={"username": "user1", "password": "admin123"}).status_code == 401


def test_token_signature_is_verified(client):
    """签名分量必须校验：伪造/篡改的 token 不可冒充用户（Ruling T4-1）。"""
    assert client.get("/api/auth/me",
                      headers={"Authorization": "Bearer user:1:deadbeef"}).status_code == 401
    assert client.get("/api/auth/me",
                      headers={"Authorization": "Bearer garbage"}).status_code == 401
    # 跨用户冒充：拿 user1 的合法签名去顶 admin 的 id
    tok = client.post("/api/auth/login",
                      json={"username": "user1", "password": "admin123"}).json()["token"]
    _, _, sig = tok.split(":")
    assert client.get("/api/auth/me",
                      headers={"Authorization": f"Bearer user:1:{sig}"}).status_code == 401
    # 合法 token 仍可用（未过度收紧）
    assert client.get("/api/auth/me",
                      headers={"Authorization": f"Bearer {tok}"}).status_code == 200