"""业务库接入测试：SQLite 内存库建表 + Document CRUD，不连 MySQL。"""
from datetime import datetime

import app.db as dbmod
from app.models.document import Document


def _sqlite_engine(monkeypatch):
    monkeypatch.setattr(dbmod, "get_engine", lambda: dbmod._make_engine("sqlite:///:memory:"))
    engine = dbmod.get_engine()
    dbmod.Base.metadata.create_all(engine)
    return engine


def test_create_table_and_insert_document(monkeypatch):
    engine = _sqlite_engine(monkeypatch)

    with dbmod.session_scope(engine) as s:
        doc = Document(name="伤寒论.pdf", file_type="pdf", size=1024,
                       topic="内科", status="上传中", chunk_count=0)
        s.add(doc)
        s.flush()
        doc_id = doc.id

    with dbmod.session_scope(engine) as s:
        got = s.get(Document, doc_id)
        assert got.name == "伤寒论.pdf"
        assert got.status == "上传中"
        assert got.chunk_count == 0
        assert isinstance(got.uploaded_at, datetime)


def test_update_status_and_chunk_count(monkeypatch):
    engine = _sqlite_engine(monkeypatch)
    with dbmod.session_scope(engine) as s:
        doc = Document(name="a.md", file_type="md", size=10, topic="内科", status="上传中")
        s.add(doc)
        s.flush()
        doc_id = doc.id

    with dbmod.session_scope(engine) as s:
        doc = s.get(Document, doc_id)
        doc.status = "就绪"
        doc.chunk_count = 7

    with dbmod.session_scope(engine) as s:
        got = s.get(Document, doc_id)
        assert (got.status, got.chunk_count) == ("就绪", 7)


def test_sqlalchemy_url_falls_back_to_mysql_dsn(monkeypatch):
    from app.config import Settings

    s = Settings(database_url="", mysql_dsn="mysql+pymysql://u:p@h:3307/d")
    assert s.sqlalchemy_url == "mysql+pymysql://u:p@h:3307/d"
    s2 = Settings(database_url="sqlite:///:memory:")
    assert s2.sqlalchemy_url == "sqlite:///:memory:"