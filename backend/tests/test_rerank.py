"""Rerank 测试：monkeypatch httpx，无网络。"""
import httpx
import pytest

import app.llm.rerank as rerank_mod
from app.llm.rerank import rerank


def _fake_post_ok(monkeypatch, results=None):
    # httpx>=0.28 的 raise_for_status 要求 Response 带 request，故手动构造
    resp = httpx.Response(200, request=httpx.Request("POST", "http://fake/rerank"), json={"id": "x", "results": results or [
        {"index": 1, "relevance_score": 0.90},
        {"index": 0, "relevance_score": 0.70},
    ]})
    monkeypatch.setattr(rerank_mod.httpx, "post", lambda *a, **k: resp)


def test_rerank_returns_top_n_sorted(monkeypatch):
    _fake_post_ok(monkeypatch)

    out = rerank("人参的功效", ["文本a", "文本b"])

    assert out == [{"index": 1, "score": 0.90}, {"index": 0, "score": 0.70}]


def test_rerank_empty_documents_returns_empty():
    assert rerank("问题", []) == []


def test_rerank_no_key_raises(monkeypatch):
    class FakeSettings:
        siliconflow_api_key = ""

    monkeypatch.setattr(rerank_mod, "get_settings", lambda: FakeSettings())
    with pytest.raises(RuntimeError, match="SILICONFLOW_API_KEY"):
        rerank("q", ["d"])