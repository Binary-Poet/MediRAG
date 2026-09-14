"""问答接口闭环测试：monkeypatch 向量库/关键词/图谱/LLM/rerank，无网络。

验证：三路召回 → RRF → 精排 → 证据组装 → 图谱事实独立汇入 → trace 返回。
"""
from unittest.mock import MagicMock

import app.api.chat as chat_module
from app.retrieval.keyword import KeywordIndex
from app.retrieval.vector_store import LocalVectorStore

SAMPLE_CHUNK = {
    "chunk_id": "中药方剂学基础#0001",
    "title": "四君子汤",
    "doc_name": "中药方剂学基础",
    "chapter": "第1节",
    "page_no": 1,
    "topic": "综合典籍",
    "text": "四君子汤由人参、白术、茯苓、炙甘草四味药组成",
    "embedding": [1.0, 0.0],
}


def _fake_store(tmp_path) -> LocalVectorStore:
    store = LocalVectorStore(str(tmp_path / "idx.json"))
    store.upsert([SAMPLE_CHUNK])
    return store


def _fake_graph():
    g = MagicMock()
    g.all_entities.return_value = [
        {"name": "四君子汤", "alias": "", "type": "方剂"},
        {"name": "人参", "alias": "", "type": "中药"},
    ]
    g.neighbors.return_value = [
        {"source": "四君子汤", "relation": "组成", "target": "人参",
         "source_type": "方剂", "target_type": "中药"},
    ]
    return g


def _patch_all(client, monkeypatch, tmp_path, graph=None):
    monkeypatch.setattr(chat_module, "get_store", lambda: _fake_store(tmp_path))
    monkeypatch.setattr(chat_module, "get_keyword_index", lambda: KeywordIndex().build([]) or KeywordIndex())
    monkeypatch.setattr(chat_module, "get_graph", lambda: graph if graph is not None else _fake_graph())
    monkeypatch.setattr(chat_module, "embed_texts", lambda texts: [[1.0, 0.0]])
    monkeypatch.setattr(
        chat_module,
        "rerank",
        lambda query, docs, top_n: [{"index": i, "score": 0.9 - i * 0.1} for i in range(min(top_n, len(docs)))],
    )
    monkeypatch.setattr(
        chat_module,
        "chat_completion",
        lambda system, user, temperature=0.3: "四君子汤由人参、白术、茯苓、炙甘草组成 [1]",
    )


def test_ask_full_loop_with_trace(client, monkeypatch, tmp_path) -> None:
    _patch_all(client, monkeypatch, tmp_path)
    # 关键词路 stub 返回 1 个命中；真实 BM25 命中/排序由 test_keyword.py 覆盖。
    # （rank-bm25 对单篇语料 IDF 为负，真实 KeywordIndex 会过滤为 0 命中，故此处打桩。）
    kw_index = MagicMock()
    kw_index.search.return_value = [{**SAMPLE_CHUNK, "score": 1.0}]
    monkeypatch.setattr(chat_module, "get_keyword_index", lambda: kw_index)

    resp = client.post("/api/chat/ask", json={"question": "四君子汤由哪些中药组成？"})

    assert resp.status_code == 200
    body = resp.json()
    assert "人参" in body["answer"]
    assert len(body["references"]) == 1

    # 图谱事实独立返回
    assert body["graph_facts"] == [{
        "source": "四君子汤", "relation": "组成", "target": "人参",
        "source_type": "方剂", "target_type": "中药",
    }]

    # trace 全链路数字
    t = body["trace"]
    assert t["understand"]["raw"] == "四君子汤由哪些中药组成？"
    assert "四君子汤" in t["understand"]["entities"]
    assert t["retrieve"]["vector_n"] == 1
    assert t["retrieve"]["keyword_n"] == 1
    assert t["retrieve"]["graph_n"] == 1
    assert t["fuse"]["candidate_n"] == 1
    assert t["fuse"]["method"] == "RRF"
    assert t["rerank"]["evidence_n"] == 1
    assert t["rerank"]["status"] == "证据充分，正常生成"


def test_ask_empty_evidence_returns_fallback(client, monkeypatch, tmp_path) -> None:
    empty_graph = MagicMock()
    empty_graph.all_entities.return_value = []
    empty_graph.neighbors.return_value = []
    idx = KeywordIndex()
    idx.build([SAMPLE_CHUNK])
    # 向量命中 0：让 fake store 为空
    monkeypatch.setattr(chat_module, "get_store",
                        lambda: LocalVectorStore(str(tmp_path / "e.json")))
    monkeypatch.setattr(chat_module, "get_keyword_index", lambda: idx)
    monkeypatch.setattr(chat_module, "get_graph", lambda: empty_graph)
    monkeypatch.setattr(chat_module, "embed_texts", lambda texts: [[1.0, 0.0]])

    resp = client.post("/api/chat/ask", json={"question": "今天天气怎么样"})

    assert resp.status_code == 200
    body = resp.json()
    assert "未检索到可靠依据" in body["answer"]
    assert body["references"] == []
    assert body["graph_facts"] == []
    assert body["trace"]["rerank"]["evidence_n"] == 0
    assert body["trace"]["rerank"]["status"] == "知识库未匹配"


def test_ask_rejects_empty_question(client) -> None:
    resp = client.post("/api/chat/ask", json={"question": ""})
    assert resp.status_code == 422