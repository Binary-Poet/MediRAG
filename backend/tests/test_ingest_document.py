"""异步入库流水线测试：SQLite + 内存向量库 + monkeypatch 向量化，无网络。"""
import app.db as dbmod
import app.ingestion.pipeline as pmod
import app.retrieval.keyword as kmod
from app.db import Base, _make_engine, session_scope
from app.models.document import Document
from app.retrieval.vector_store import LocalVectorStore


def _setup(monkeypatch, tmp_path):
    engine = _make_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    store = LocalVectorStore(str(tmp_path / "idx.json"))
    monkeypatch.setattr(dbmod, "_engine", engine)      # 所有 session_scope() 走测试库
    monkeypatch.setattr(pmod, "get_store", lambda: store)
    monkeypatch.setattr(kmod, "get_store", lambda: store)  # rebuild 走同一内存库，不触磁盘配置路径
    monkeypatch.setattr(pmod, "embed_texts", lambda texts: [[float(len(t)), 1.0] for t in texts])
    return engine, store


def test_ingest_marks_ready_and_writes_chunks(monkeypatch, tmp_path):
    engine, store = _setup(monkeypatch, tmp_path)
    src = tmp_path / "内科讲义.md"
    src.write_text("四君子汤由人参、白术、茯苓、炙甘草组成。", encoding="utf-8")

    with session_scope(engine) as s:
        doc = Document(name="内科讲义.md", file_type="md", size=src.stat().st_size,
                       topic="内科", status="上传中", stored_path=str(src))
        s.add(doc)
        s.flush()
        doc_id = doc.id

    stats = pmod.ingest_document(doc_id)

    assert stats["chunks"] >= 1
    with session_scope(engine) as s:
        got = s.get(Document, doc_id)
        assert got.status == "就绪"
        assert got.chunk_count == stats["chunks"]
    assert len(store) >= 1
    assert any("四君子汤" in c["text"] for c in store.chunks)


def test_ingest_marks_failed_on_parse_error(monkeypatch, tmp_path):
    engine, _ = _setup(monkeypatch, tmp_path)
    src = tmp_path / "坏文件.exe"
    src.write_bytes(b"\x00\x01")

    with session_scope(engine) as s:
        doc = Document(name="坏文件.exe", file_type="exe", size=2, topic="内科",
                       status="上传中", stored_path=str(src))
        s.add(doc)
        s.flush()
        doc_id = doc.id

    stats = pmod.ingest_document(doc_id)

    assert stats["chunks"] == 0
    with session_scope(engine) as s:
        got = s.get(Document, doc_id)
        assert got.status == "失败"
        assert "不支持" in got.error_message


def test_ingest_rebuilds_keyword_index(monkeypatch, tmp_path):
    engine, store = _setup(monkeypatch, tmp_path)
    called = {"n": 0}
    monkeypatch.setattr(pmod, "rebuild_keyword_index",
                        lambda: called.__setitem__("n", called["n"] + 1))
    src = tmp_path / "a.md"
    src.write_text("脾气虚常见便溏倦怠。", encoding="utf-8")
    with session_scope(engine) as s:
        doc = Document(name="a.md", file_type="md", size=10, topic="内科",
                       status="上传中", stored_path=str(src))
        s.add(doc)
        s.flush()
        doc_id = doc.id

    pmod.ingest_document(doc_id)
    assert called["n"] == 1


def test_rebuild_keyword_index_rebuilds_from_store(monkeypatch, tmp_path):
    store = LocalVectorStore(str(tmp_path / "idx.json"))
    store.upsert([{"chunk_id": "a#0000", "title": "四君子汤", "text": "人参白术茯苓炙甘草",
                   "doc_name": "a.md", "chapter": "第 1 页", "page_no": 1, "topic": "内科",
                   "embedding": [1.0, 0.0]}])
    monkeypatch.setattr(kmod, "get_store", lambda: store)
    kmod.rebuild_keyword_index()
    hits = kmod.get_keyword_index().search("四君子汤", top_k=5)
    assert hits and hits[0]["chunk_id"] == "a#0000"