import json
import httpx
import pytest

import app.llm.chat as cmod
from app.llm.chat import chat_completion_stream


class _FakeResponse:
    def __init__(self, lines):
        self._lines = lines
    def raise_for_status(self):
        pass
    def iter_lines(self):
        return iter(self._lines)
    def __enter__(self):
        return self
    def __exit__(self, *a):
        return False


def test_stream_yields_deltas(monkeypatch):
    lines = [
        'data: {"choices": [{"delta": {"content": "四君子"}}]}',
        'data: {"choices": [{"delta": {"content": "汤"}}]}',
        "data: [DONE]",
    ]
    monkeypatch.setattr(cmod, "get_settings", lambda: _S())
    monkeypatch.setattr(httpx, "stream", lambda *a, **k: _FakeResponse(lines))
    out = "".join(chat_completion_stream(system="s", user="u"))
    assert out == "四君子汤"


def test_stream_skips_non_data_and_empty_delta(monkeypatch):
    lines = [
        "event: ping",
        'data: {"choices": [{"delta": {}}]}',
        'data: {"choices": [{"delta": {"content": "人参"}}]}',
        "data: [DONE]",
    ]
    monkeypatch.setattr(cmod, "get_settings", lambda: _S())
    monkeypatch.setattr(httpx, "stream", lambda *a, **k: _FakeResponse(lines))
    assert "".join(chat_completion_stream("s", "u")) == "人参"


class _S:
    llm_vendor = "deepseek"
    deepseek_api_key = "k"; deepseek_base_url = "http://x"; llm_model_main = "m"
    dashscope_api_key = ""; dashscope_base_url = "http://y"; llm_model_alt = "q"
