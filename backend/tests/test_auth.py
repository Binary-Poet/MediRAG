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


def test_register_creates_least_privilege_user_and_returns_token(client):
    """自助注册（登录页「立即注册」）：固定发放最低权限角色，且返回 token 免二次登录。"""
    r = client.post("/api/auth/register", json={"username": "newdoc", "password": "secret123"})
    assert r.status_code == 200
    body = r.json()
    assert body["user"]["role"] == "知识用户"
    assert body["user"]["display_name"] == "newdoc"      # 未填姓名时回落为用户名
    me = client.get("/api/auth/me", headers={"Authorization": f"Bearer {body['token']}"})
    assert me.status_code == 200 and me.json()["username"] == "newdoc"
    assert client.post("/api/auth/login",
                       json={"username": "newdoc", "password": "secret123"}).status_code == 200


def test_register_ignores_role_in_request_body(client):
    """请求体里塞 role 不生效。

    注册接口若把 role 透传给建号逻辑，任何人构造一条请求就能把自己注册成管理员——
    故这里既断言角色被强制，也真去调一次管理员接口确认拿不到权限。
    """
    r = client.post("/api/auth/register",
                    json={"username": "sneaky", "password": "secret123", "role": "管理员"})
    assert r.status_code == 200
    assert r.json()["user"]["role"] == "知识用户"
    tok = r.json()["token"]
    assert client.get("/api/users",
                      headers={"Authorization": f"Bearer {tok}"}).status_code == 403


def test_register_rejects_duplicate_username(client):
    assert client.post("/api/auth/register",
                       json={"username": "admin", "password": "admin123"}).status_code == 409


def test_register_trims_fields(client):
    r = client.post("/api/auth/register", json={
        "username": "  zhang3  ", "password": "secret123", "display_name": "  张三  "})
    assert r.status_code == 200
    assert r.json()["user"]["username"] == "zhang3"
    assert r.json()["user"]["display_name"] == "张三"


@pytest.mark.parametrize("payload", [
    {"username": "ab", "password": "secret123"},        # 用户名过短
    {"username": "x" * 21, "password": "secret123"},    # 用户名过长
    {"username": "okname", "password": "12345"},        # 密码过短
    {"username": "   ", "password": "secret123"},       # 去空白后为空
])
def test_register_validates_input(client, payload):
    assert client.post("/api/auth/register", json=payload).status_code == 422


def _user1_token(client) -> str:
    return client.post("/api/auth/login",
                       json={"username": "user1", "password": "admin123"}).json()["token"]


def test_update_profile_requires_token(client):
    assert client.put("/api/auth/profile", json={"display_name": "x"}).status_code == 401


def test_update_profile_persists(client):
    tok = _user1_token(client)
    r = client.put("/api/auth/profile", headers={"Authorization": f"Bearer {tok}"},
                   json={"display_name": "李时珍"})
    assert r.status_code == 200 and r.json()["display_name"] == "李时珍"
    # 落库并回读：/me 反映新姓名，用户名与角色不受影响
    me = client.get("/api/auth/me", headers={"Authorization": f"Bearer {tok}"}).json()
    assert me["display_name"] == "李时珍"
    assert me["username"] == "user1" and me["role"] == "知识用户"


def test_update_profile_trims_whitespace(client):
    tok = _user1_token(client)
    r = client.put("/api/auth/profile", headers={"Authorization": f"Bearer {tok}"},
                   json={"display_name": "  张三  "})
    assert r.status_code == 200 and r.json()["display_name"] == "张三"


@pytest.mark.parametrize("name", ["", "   ", "甲" * 51])
def test_update_profile_rejects_invalid_name(client, name):
    tok = _user1_token(client)
    r = client.put("/api/auth/profile", headers={"Authorization": f"Bearer {tok}"},
                   json={"display_name": name})
    assert r.status_code == 422