"""文档 API 测试：TestClient + SQLite + 内存向量库；后台任务同步执行（monkeypatch）。"""
import app.db as dbmod
import app.ingestion.pipeline as pmod
import app.retrieval.keyword as kmod
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
    monkeypatch.setattr(dmod, "get_store", lambda: store)      # 删除路径走内存库
    monkeypatch.setattr(kmod, "get_store", lambda: store)      # BM25 重建走内存库
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


def test_upload_sanitizes_path_traversal_filename(client, monkeypatch, tmp_path):
    """带目录成分的文件名被剥离为纯文件名，且落盘不越出 UPLOAD_DIR。"""
    _prepare(monkeypatch, tmp_path)
    resp = client.post("/api/documents",
                       files={"file": ("..\\..\\evil.md", b"x", "text/markdown")},
                       data={"topic": "内科"})
    assert resp.status_code == 200
    assert resp.json()["name"] == "evil.md"

    upload_dir = (tmp_path / "uploads").resolve()
    files = list(upload_dir.glob("*"))
    assert len(files) == 1
    for p in files:
        assert p.resolve().parent == upload_dir          # 无任何文件逃逸出上传目录


def test_upload_rejects_windows_reserved_name(client, monkeypatch, tmp_path):
    _prepare(monkeypatch, tmp_path)
    resp = client.post("/api/documents",
                       files={"file": ("CON.md", b"x", "text/markdown")},
                       data={"topic": "内科"})
    assert resp.status_code == 400
    assert "文件名非法" in resp.json()["detail"]


def test_upload_duplicate_name_conflicts_then_allows_after_delete(client, monkeypatch, tmp_path):
    """同名未失败文档拒绝重复上传（409，不留孤儿文件）；删除后可重传同名。"""
    _prepare(monkeypatch, tmp_path)
    files = {"file": ("同名.md", "四君子汤由人参白术组成。".encode(), "text/markdown")}
    first = client.post("/api/documents", files=files, data={"topic": "内科"})
    assert first.status_code == 200

    second = client.post("/api/documents", files=files, data={"topic": "内科"})
    assert second.status_code == 409
    assert "已存在同名文档" in second.json()["detail"]
    assert len(list((tmp_path / "uploads").glob("*"))) == 1      # 409 未落孤儿文件

    assert client.delete(f"/api/documents/{first.json()['id']}").status_code == 200
    third = client.post("/api/documents", files=files, data={"topic": "内科"})
    assert third.status_code == 200                              # 切片已清除，允许重传


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
    listed = client.get("/api/documents").json()
    assert listed["total"] == 0
    assert listed["total_chunks"] == 0

    client.post("/api/documents", files={"file": ("a.md", b"x", "text/markdown")}, data={"topic": "内科"})
    listed = client.get("/api/documents").json()
    assert listed["total"] == 1
    assert listed["total_chunks"] == listed["items"][0]["chunk_count"]
    assert listed["total_chunks"] > 0


def test_delete_removes_record_and_chunks(client, monkeypatch, tmp_path):
    _, store = _prepare(monkeypatch, tmp_path)
    resp = client.post("/api/documents",
                       files={"file": ("待删.md", "四君子汤由人参白术组成。".encode(), "text/markdown")},
                       data={"topic": "内科"})
    doc_id = resp.json()["id"]
    assert len(store.chunks) >= 1

    dele = client.delete(f"/api/documents/{doc_id}")
    assert dele.status_code == 200
    assert dele.json()["removed_chunks"] >= 1
    assert len(store.chunks) == 0
    assert client.get("/api/documents").json()["total"] == 0
    assert client.get(f"/api/documents/{doc_id}/parse-status").status_code == 404