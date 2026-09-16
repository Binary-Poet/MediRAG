"""文档详情/下载/重命名（规格 P0-6 操作列）。"""
import pytest

import app.db as dbmod
import app.ingestion.pipeline as pmod
from app.api import documents as dmod


@pytest.fixture(autouse=True)
def _db(monkeypatch, tmp_path):
    """sqlite 内存库 + 上传目录隔离 + 向量化离线。

    本组只验「记录行」三类操作（详情/下载/重命名）——按约定它们不依赖 ingest 成功，
    故显式让后台 ingest 的向量化不可用：既锁定该契约，也避免测试触发真实 Embedding
    API 与仓库 data/ 落盘副作用。
    """
    eng = dbmod._make_engine("sqlite:///:memory:")
    dbmod.Base.metadata.create_all(eng)
    monkeypatch.setattr(dbmod, "_engine", eng)
    monkeypatch.setattr(dmod, "UPLOAD_DIR", tmp_path / "uploads")

    def _offline(_texts: list[str]) -> list[list[float]]:
        raise RuntimeError("测试环境离线：向量化不可用")

    monkeypatch.setattr(pmod, "embed_texts", _offline)


# 中文正文需显式 UTF-8 编码：bytes 字面量只能含 ASCII 字符
_BODY = "# 测试\n\n正文。".encode()


def _mk(client, name="验收语料.md") -> int:
    r = client.post("/api/documents", files={"file": (name, _BODY, "text/markdown")},
                    data={"topic": "内科"})
    assert r.status_code == 200
    return r.json()["id"]


def test_detail_and_rename(client):
    did = _mk(client)
    r = client.get(f"/api/documents/{did}")
    assert r.status_code == 200
    d = r.json()
    assert d["name"] == "验收语料.md" and d["topic"] == "内科"

    r = client.put(f"/api/documents/{did}", json={"name": "新名字.md"})
    assert r.status_code == 200
    assert client.get(f"/api/documents/{did}").json()["name"] == "新名字.md"

    # 同名单重复 → 409
    _mk(client, "别档.md")
    dup = client.post("/api/documents", files={"file": ("新名字.md", b"x", "text/markdown")},
                      data={"topic": "内科"}).json()["id"]
    r = client.put(f"/api/documents/{dup}", json={"name": "新名字.md"})
    assert r.status_code == 409


def test_download_serves_file(client):
    did = _mk(client)
    r = client.get(f"/api/documents/{did}/download")
    assert r.status_code == 200
    assert r.content == _BODY
    assert "attachment" in r.headers.get("content-disposition", "")


def test_404s(client):
    assert client.get("/api/documents/999").status_code == 404
    assert client.get("/api/documents/999/download").status_code == 404
