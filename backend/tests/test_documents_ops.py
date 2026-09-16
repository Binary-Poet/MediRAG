"""文档详情/下载/重命名（规格 P0-6 操作列）。

两组夹具，覆盖两类场景：
  - offline_env：向量化离线，上传后记录停在「失败」——证明 ops（详情/下载/重命名）
    只依赖记录行，对失败态记录依旧可用（且不触发真实 Embedding API / 仓库写盘）。
  - ready_env：可用 embed stub + 临时 LocalVectorStore，产出「就绪」记录——覆盖同名冲突 409
    （与上传语义对齐：仅非失败态占名）。
"""
import pytest

import app.db as dbmod
import app.ingestion.pipeline as pmod
import app.retrieval.keyword as kmod
from app.api import documents as dmod
from app.retrieval.vector_store import LocalVectorStore

# 中文正文需显式 UTF-8 编码：bytes 字面量只能含 ASCII 字符
_BODY = "# 测试\n\n正文。".encode()


def _base(monkeypatch, tmp_path):
    """sqlite 内存库（跨线程共享连接）+ 上传目录隔离（落盘不触仓库 data/）。"""
    eng = dbmod._make_engine("sqlite:///:memory:")
    dbmod.Base.metadata.create_all(eng)
    monkeypatch.setattr(dbmod, "_engine", eng)
    monkeypatch.setattr(dmod, "UPLOAD_DIR", tmp_path / "uploads")
    return eng


@pytest.fixture
def offline_env(monkeypatch, tmp_path):
    """向量化离线：后台 ingest 失败，记录停在「失败」态。"""
    _base(monkeypatch, tmp_path)

    def _offline(_texts: list[str]) -> list[list[float]]:
        raise RuntimeError("测试环境离线：向量化不可用")

    monkeypatch.setattr(pmod, "embed_texts", _offline)


@pytest.fixture
def ready_env(monkeypatch, tmp_path):
    """可用 embed stub + 临时 LocalVectorStore：产出「就绪」记录（零真实 API、零仓库写盘）。"""
    _base(monkeypatch, tmp_path)
    store = LocalVectorStore(str(tmp_path / "idx.json"))
    monkeypatch.setattr(pmod, "get_store", lambda: store)
    monkeypatch.setattr(kmod, "get_store", lambda: store)      # BM25 重建走内存库
    monkeypatch.setattr(pmod, "embed_texts",
                        lambda texts: [[1.0, float(i)] for i, _ in enumerate(texts)])
    return store


def _mk(client, name="验收语料.md") -> int:
    r = client.post("/api/documents", files={"file": (name, _BODY, "text/markdown")},
                    data={"topic": "内科"})
    assert r.status_code == 200
    return r.json()["id"]


def test_detail_and_rename_on_failed_record(client, offline_env):
    """失败态记录上详情/重命名仍可用（ops 只依赖记录行）。"""
    did = _mk(client)
    r = client.get(f"/api/documents/{did}")
    assert r.status_code == 200
    d = r.json()
    assert d["name"] == "验收语料.md" and d["topic"] == "内科"
    assert d["status"] == "失败" and d["stored_file"].endswith("验收语料.md")

    r = client.put(f"/api/documents/{did}", json={"name": "新名字.md"})
    assert r.status_code == 200
    assert client.get(f"/api/documents/{did}").json()["name"] == "新名字.md"


def test_rename_duplicate_name_conflicts(client, ready_env):
    """就绪态同名单重复 → 409（与上传语义对齐：仅非失败态占名）。"""
    did = _mk(client)                                          # 就绪：验收语料.md
    assert client.put(f"/api/documents/{did}", json={"name": "新名字.md"}).status_code == 200
    other = _mk(client, "别档.md")                              # 就绪：别档.md
    r = client.put(f"/api/documents/{other}", json={"name": "新名字.md"})
    assert r.status_code == 409


def test_rename_rejects_extension_change(client, offline_env):
    """扩展名需与原文一致：.md → .pdf 拒绝（否则 name/file_type/磁盘字节三者失配）。"""
    did = _mk(client)
    r = client.put(f"/api/documents/{did}", json={"name": "讲义.pdf"})
    assert r.status_code == 400


def test_download_serves_file(client, offline_env):
    did = _mk(client)
    r = client.get(f"/api/documents/{did}/download")
    assert r.status_code == 200
    assert r.content == _BODY
    assert "attachment" in r.headers.get("content-disposition", "")


def test_404s(client, offline_env):
    assert client.get("/api/documents/999").status_code == 404
    assert client.get("/api/documents/999/download").status_code == 404
