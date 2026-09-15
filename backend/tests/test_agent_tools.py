from unittest.mock import MagicMock

import app.agent.tools as tmod
from app.agent.tools import TOOL_NAMES, graph_search, keyword_search, vector_search


def test_tool_names_set():
    assert TOOL_NAMES == {"vector_search", "keyword_search", "graph_search"}


def test_vector_search_invokes_store(monkeypatch):
    fake_store = MagicMock()
    fake_store.search.return_value = [{"chunk_id": "a", "title": "四君子汤"}]
    monkeypatch.setattr(tmod, "get_store", lambda: fake_store)
    monkeypatch.setattr(tmod, "embed_texts", lambda texts: [[0.1, 0.2]])

    hits = vector_search.invoke({"query": "四君子汤组成", "top_k": 5})

    assert hits == [{"chunk_id": "a", "title": "四君子汤"}]
    fake_store.search.assert_called_once()
    assert fake_store.search.call_args.args[1] == 5


def test_keyword_search_invokes_index(monkeypatch):
    fake_idx = MagicMock()
    fake_idx.search.return_value = [{"chunk_id": "k1"}]
    monkeypatch.setattr(tmod, "get_keyword_index", lambda: fake_idx)

    hits = keyword_search.invoke({"query": "风寒束表", "top_k": 3})

    assert hits == [{"chunk_id": "k1"}]
    fake_idx.search.assert_called_once()


def test_graph_search_wraps_neighbors(monkeypatch):
    fake_graph = MagicMock()
    fake_graph.neighbors.return_value = [{"source": "四君子汤", "relation": "组成", "target": "人参"}]
    monkeypatch.setattr(tmod, "get_graph", lambda: fake_graph)

    out = graph_search.invoke({"entity": "四君子汤", "hop": 1})

    assert out["entity"] == "四君子汤"
    assert out["facts"][0]["relation"] == "组成"
    fake_graph.neighbors.assert_called_once_with(["四君子汤"], hop=1)