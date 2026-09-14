"""向量存储测试：upsert 去重 / 余弦检索排序 / 持久化往返。"""
import numpy as np

from app.retrieval.vector_store import LocalVectorStore


def _make_items():
    # 一维方向向量，构造明确的相似度排序
    return [
        {"chunk_id": "a", "title": "A", "text": "ta", "embedding": [1.0, 0.0]},
        {"chunk_id": "b", "title": "B", "text": "tb", "embedding": [0.0, 1.0]},
        {"chunk_id": "c", "title": "C", "text": "tc", "embedding": [0.9, 0.1]},
    ]


def test_search_orders_by_cosine(tmp_path) -> None:
    store = LocalVectorStore(str(tmp_path / "idx.json"))
    store.upsert(_make_items())

    hits = store.search([1.0, 0.0], top_k=3)
    assert [h["chunk_id"] for h in hits] == ["a", "c", "b"]
    assert hits[0]["score"] > 0.99  # a 与查询完全同向


def test_upsert_dedup(tmp_path) -> None:
    store = LocalVectorStore(str(tmp_path / "idx.json"))
    store.upsert(_make_items())
    updated = [{"chunk_id": "a", "title": "A2", "text": "ta2", "embedding": [0.5, 0.5]}]
    store.upsert(updated)
    assert len(store) == 3
    by_id = {c["chunk_id"]: c for c in store.chunks}
    assert by_id["a"]["title"] == "A2"


def test_persistence_roundtrip(tmp_path) -> None:
    path = str(tmp_path / "idx.json")
    s1 = LocalVectorStore(path)
    s1.upsert(_make_items())
    s1.save()

    s2 = LocalVectorStore(path).load()
    assert len(s2) == 3
    hits = s2.search([1.0, 0.0], top_k=1)
    assert hits[0]["chunk_id"] == "a"


def test_empty_store_returns_no_hits(tmp_path) -> None:
    store = LocalVectorStore(str(tmp_path / "idx.json"))
    assert store.search([1.0, 0.0]) == []
    assert np is not None  # 保持导入引用
