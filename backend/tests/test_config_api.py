"""推理配置 API：默认值=截图值；保存即写库；越界 422；再保存覆盖；
可用模型按 Key 就绪计算；未就绪模型保存 422；写端点须登录。"""
import pytest
from sqlalchemy import select

import app.db as dbmod
from app.config import get_settings
from app.db import session_scope
from app.models.inference_config import InferenceConfig


@pytest.fixture(autouse=True)
def _db(monkeypatch):
    eng = dbmod._make_engine("sqlite:///:memory:")
    dbmod.init_db(eng)                      # 建表 + seed 三用户（写端点鉴权用）
    monkeypatch.setattr(dbmod, "_engine", eng)


def _auth(client) -> dict:
    """登录 admin 取 Bearer 头（PUT /api/config 已挂 current_user）。"""
    tok = client.post("/api/auth/login",
                      json={"username": "admin", "password": "admin123"}).json()["token"]
    return {"Authorization": f"Bearer {tok}"}


def test_get_default_matches_spec(client):
    r = client.get("/api/config")
    assert r.status_code == 200
    d = r.json()["items"]
    assert d["semantic_k"] == 20 and d["keyword_k"] == 20
    assert d["fuse_candidate"] == 25 and d["final_evidence"] == 5
    assert d["rrf_k"] == 60
    assert d["model"] == "deepseek-chat"
    assert d["answer_temp"] == 0.3 and d["query_temp"] == 0.1


def test_get_available_models_follows_keys(client, monkeypatch):
    """可用模型由 Key 就绪情况决定：默认 .env 仅 deepseek；补 dashscope 后含 qwen-plus。"""
    monkeypatch.setattr(get_settings(), "dashscope_api_key", "")
    assert client.get("/api/config").json()["available_models"] == ["deepseek-chat"]

    monkeypatch.setattr(get_settings(), "dashscope_api_key", "sk-test-dashscope")
    assert client.get("/api/config").json()["available_models"] == ["deepseek-chat", "qwen-plus"]


def test_put_persists_and_overrides(client, monkeypatch):
    # qwen-plus 需 dashscope key 就绪（否则保存被 422 拦截）——本用例注入 key 走通保存路径
    monkeypatch.setattr(get_settings(), "dashscope_api_key", "sk-test-dashscope")
    headers = _auth(client)
    body = {"semantic_k": 12, "keyword_k": 8, "fuse_candidate": 30,
            "final_evidence": 3, "rrf_k": 50, "model": "qwen-plus",
            "answer_temp": 0.7, "query_temp": 0.2}
    r = client.put("/api/config", json=body, headers=headers)
    assert r.status_code == 200
    assert r.json()["semantic_k"] == 12 and r.json()["model"] == "qwen-plus"
    # 再次 GET 仍为保存值（已写库，非内存一次性）
    assert client.get("/api/config").json()["items"]["semantic_k"] == 12
    # 覆盖保存
    body["semantic_k"] = 15
    assert client.put("/api/config", json=body, headers=headers).status_code == 200
    assert client.get("/api/config").json()["items"]["semantic_k"] == 15
    # 落库断言
    with session_scope() as s:
        row = s.execute(select(InferenceConfig)).scalar_one()
        assert row.semantic_k == 15 and row.model == "qwen-plus"


def test_put_unavailable_model_rejected(client, monkeypatch):
    """dashscope key 未配置时选 qwen-plus → 422，detail 指明缺失的 Key。"""
    monkeypatch.setattr(get_settings(), "dashscope_api_key", "")
    body = {"semantic_k": 20, "keyword_k": 20, "fuse_candidate": 25,
            "final_evidence": 5, "rrf_k": 60, "model": "qwen-plus",
            "answer_temp": 0.3, "query_temp": 0.1}
    r = client.put("/api/config", json=body, headers=_auth(client))
    assert r.status_code == 422
    assert "qwen-plus" in r.json()["detail"] and "DASHSCOPE_API_KEY" in r.json()["detail"]
    # 未落库（拒绝即不写）
    with session_scope() as s:
        assert s.execute(select(InferenceConfig)).scalar_one_or_none() is None


def test_put_requires_token(client, monkeypatch):
    """写端点须登录：未带 token 一律 401。"""
    monkeypatch.setattr(get_settings(), "dashscope_api_key", "")
    body = {"semantic_k": 20, "keyword_k": 20, "fuse_candidate": 25,
            "final_evidence": 5, "rrf_k": 60, "model": "deepseek-chat",
            "answer_temp": 0.3, "query_temp": 0.1}
    assert client.put("/api/config", json=body).status_code == 401


@pytest.mark.parametrize("field,bad", [
    ("semantic_k", 0), ("semantic_k", 101), ("keyword_k", -1),
    ("fuse_candidate", 0), ("final_evidence", 200), ("rrf_k", 0),
    ("answer_temp", 2.1), ("query_temp", -0.1), ("model", "gpt-4"),
])
def test_put_rejects_out_of_range(client, field, bad):
    full = {"semantic_k": 20, "keyword_k": 20, "fuse_candidate": 25,
            "final_evidence": 5, "rrf_k": 60, "model": "deepseek-chat",
            "answer_temp": 0.3, "query_temp": 0.1}
    full[field] = bad
    r = client.put("/api/config", json=full, headers=_auth(client))
    assert r.status_code == 422
    assert field in r.json()["detail"]
