"""文档 API 测试：TestClient + SQLite + 内存向量库；后台任务同步执行（monkeypatch）。"""
import app.db as dbmod
import app.ingestion.pipeline as pmod
from app.api import documents as dmod
from app.db import Base, _make_engine
from app.retrieval.vector_store import LocalVectorStore


def _prepare(monkeypatch, tmp_path):
    engine = _make_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    store = LocalVectorStore(str(tmp_path / "idx.json"))
    monkeypatch.setattr(dbmod, "_engine", engine)      # 所有 session_scope() 走测试库
    monkeypatch.setattr(pmod, "get_store", lambda: store)
    monkeypatch.setattr(pmod, "embed_texts", lambda texts: [[1.0, float(i)] for i, _ in enumerate(texts)])
    monkeypatch.setattr(dmod, "UPLOAD_DIR", tmp_path / "uploads")
    return engine, store


def test_upload_requires_topic(client, monkeypatch, tmp_path):
    _prepare(monkeypatch, tmp_path)
    resp = client.post("/api/documents", files={"file": ("a.md", b"content", "text/markdown")})
    assert resp.status_code == 422          # 主题必选


def test_upload_rejects_unsupported_ext(client, monkeypatch, tmp_path):
    _prepare(monkeypatch, tmp_path)
    resp = client.post("/api/documents",
                       files={"file": ("a.exe", b"MZ", "application/octet-stream")},
                       data={"topic": "内科"})
    assert resp.status_code == 400
    assert "不支持" in resp.json()["detail"]


def test_upload_ingest_and_status_polling(client, monkeypatch, tmp_path):
    _prepare(monkeypatch, tmp_path)
    resp = client.post("/api/documents",
                       files={"file": ("内科讲义.md", "四君子汤由人参白术组成。".encode(), "text/markdown")},
                       data={"topic": "内科"})
    assert resp.status_code == 200
    doc_id = resp.json()["id"]

    st = client.get(f"/api/documents/{doc_id}/parse-status").json()
    assert st["status"] == "就绪"           # TestClient 同步跑完 BackgroundTasks
    assert st["chunk_count"] >= 1

    listed = client.get("/api/documents").json()
    assert listed["total"] == 1
    assert listed["items"][0]["name"] == "内科讲义.md"


def test_list_computes_total_chunks(client, monkeypatch, tmp_path):
    _prepare(monkeypatch, tmp_path)
    client.post("/api/documents", files={"file": ("a.md", b"x", "text/markdown")}, data={"topic": "内科"})
    listed = client.get("/api/documents").json()
    assert listed["total_chunks"] >= 0