"""推理配置 API：默认值=截图值；保存即写库；越界 422；再保存覆盖。"""
import pytest
from sqlalchemy import select

import app.db as dbmod
from app.db import session_scope
from app.models.inference_config import InferenceConfig


@pytest.fixture(autouse=True)
def _db(monkeypatch):
    eng = dbmod._make_engine("sqlite:///:memory:")
    dbmod.Base.metadata.create_all(eng)
    monkeypatch.setattr(dbmod, "_engine", eng)


def test_get_default_matches_spec(client):
    r = client.get("/api/config")
    assert r.status_code == 200
    d = r.json()["items"]
    assert d["semantic_k"] == 20 and d["keyword_k"] == 20
    assert d["fuse_candidate"] == 25 and d["final_evidence"] == 5
    assert d["rrf_k"] == 60
    assert d["model"] == "deepseek-chat"
    assert d["answer_temp"] == 0.3 and d["query_temp"] == 0.1


def test_put_persists_and_overrides(client):
    body = {"semantic_k": 12, "keyword_k": 8, "fuse_candidate": 30,
            "final_evidence": 3, "rrf_k": 50, "model": "qwen-plus",
            "answer_temp": 0.7, "query_temp": 0.2}
    r = client.put("/api/config", json=body)
    assert r.status_code == 200
    assert r.json()["semantic_k"] == 12 and r.json()["model"] == "qwen-plus"
    # 再次 GET 仍为保存值（已写库，非内存一次性）
    assert client.get("/api/config").json()["items"]["semantic_k"] == 12
    # 覆盖保存
    body["semantic_k"] = 15
    assert client.put("/api/config", json=body).status_code == 200
    assert client.get("/api/config").json()["items"]["semantic_k"] == 15
    # 落库断言
    with session_scope() as s:
        row = s.execute(select(InferenceConfig)).scalar_one()
        assert row.semantic_k == 15 and row.model == "qwen-plus"


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
    r = client.put("/api/config", json=full)
    assert r.status_code == 422
    assert field in r.json()["detail"]