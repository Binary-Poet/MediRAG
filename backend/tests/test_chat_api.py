"""问答接口闭环测试：monkeypatch 向量库与 LLM 客户端，无网络。

验证：检索→证据组装→生成→引用返回的完整链路。
"""
from pathlib import Path

import app.api.chat as chat_module
from app.retrieval.vector_store import LocalVectorStore


def _fake_store(tmp_path) -> LocalVectorStore:
    store = LocalVectorStore(str(tmp_path / "idx.json"))
    store.upsert(
        [
            {
                "chunk_id": "中药方剂学基础#0001",
                "title": "四君子汤",
                "doc_name": "中药方剂学基础",
                "chapter": "第1节",
                "page_no": 1,
                "topic": "综合典籍",
                "text": "四君子汤由人参、白术、茯苓、炙甘草四味药组成",
                "embedding": [1.0, 0.0],
            }
        ]
    )
    return store


def test_ask_full_loop(client, monkeypatch, tmp_path) -> None:
    captured: dict = {}

    monkeypatch.setattr(chat_module, "get_store", lambda: _fake_store(tmp_path))
    monkeypatch.setattr(chat_module, "embed_texts", lambda texts: [[1.0, 0.0]])
    monkeypatch.setattr(
        chat_module,
        "chat_completion",
        lambda system, user, temperature=0.3: captured.setdefault("user", user)
        and "四君子汤由人参、白术、茯苓、炙甘草组成 [1]",
    )

    resp = client.post("/api/chat/ask", json={"question": "四君子汤由哪些中药组成？"})
    assert resp.status_code == 200
    body = resp.json()

    assert "人参" in body["answer"]
    assert len(body["references"]) == 1
    ref = body["references"][0]
    assert ref["doc_name"] == "中药方剂学基础"
    assert ref["page_no"] == 1

    # Prompt 里应包含编号证据与问题（防幻觉约束是否进入上下文）
    assert "[1] 《中药方剂学基础》" in captured["user"]
    assert "四君子汤由哪些中药组成？" in captured["user"]


def test_ask_empty_store_returns_fallback(client, monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(
        chat_module, "get_store", lambda: LocalVectorStore(str(tmp_path / "e.json"))
    )
    monkeypatch.setattr(chat_module, "embed_texts", lambda texts: [[1.0, 0.0]])

    resp = client.post("/api/chat/ask", json={"question": "随便问点什么"})
    assert resp.status_code == 200
    assert "未检索到可靠依据" in resp.json()["answer"]
    assert resp.json()["references"] == []


def test_ask_rejects_empty_question(client) -> None:
    resp = client.post("/api/chat/ask", json={"question": ""})
    assert resp.status_code == 422
