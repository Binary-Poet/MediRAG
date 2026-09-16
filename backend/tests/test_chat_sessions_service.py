"""会话持久化服务：列表统计、收藏过滤、归属隔离、回放 payload、最近历史上限。"""
from datetime import datetime

import pytest

import app.db as dbmod
from app.db import session_scope
from app.models.chat import ChatSession
from app.services import chat_session as cs


@pytest.fixture(autouse=True)
def _db(monkeypatch):
    eng = dbmod._make_engine("sqlite:///:memory:")
    dbmod.init_db(eng)
    monkeypatch.setattr(dbmod, "_engine", eng)


def test_list_orders_by_updated_desc_and_counts_messages():
    a = cs.create_session(1, "四君子汤由哪些中药组成？")
    b = cs.create_session(1, "脾气虚常见哪些症状？")
    # 显式设定时间：Windows 时钟粒度约 15ms，连续三次写入可能落在同一刻度上，
    # 靠 sleep 或真实时钟排序会让用例变成 flaky。这里直接验证 ORDER BY 语义。
    with session_scope() as s:
        s.get(ChatSession, b).updated_at = datetime(2026, 9, 15, 10, 0, 0)
        s.get(ChatSession, a).updated_at = datetime(2026, 9, 16, 10, 0, 0)
    cs.append_message(a, "user", "四君子汤由哪些中药组成？")
    cs.append_message(a, "assistant", "人参、白术、茯苓、炙甘草")
    r = cs.list_sessions(1)
    assert r["total"] == 2
    assert r["favorite_total"] == 0
    assert [x["session_id"] for x in r["sessions"]] == [a, b]
    assert r["sessions"][0]["message_count"] == 2
    assert r["sessions"][1]["message_count"] == 0


def test_favorite_toggle_and_filter():
    a = cs.create_session(1, "问一")
    cs.create_session(1, "问二")
    assert cs.set_favorite(a, 1, True) is True
    r = cs.list_sessions(1, favorite_only=True)
    assert r["total"] == 2          # 统计是全部会话数
    assert r["favorite_total"] == 1
    assert [x["session_id"] for x in r["sessions"]] == [a]
    assert cs.set_favorite(a, 1, False) is True
    assert cs.list_sessions(1, favorite_only=True)["sessions"] == []


def test_ownership_isolation():
    a = cs.create_session(1, "问一")
    assert cs.owns(a, 1) is True
    assert cs.owns(a, 2) is False
    assert cs.set_favorite(a, 2, True) is False
    assert cs.delete_session(a, 2) is False
    assert cs.load_messages(a, 2) is None
    assert cs.load_messages(a, 1) == []      # 归属正确但尚无消息
    assert cs.list_sessions(2)["total"] == 0


def test_delete_removes_messages_too():
    a = cs.create_session(1, "问一")
    cs.append_message(a, "user", "问一")
    assert cs.delete_session(a, 1) is True
    assert cs.list_sessions(1)["total"] == 0
    assert cs.load_messages(a, 1) is None    # 会话没了，消息也不该能读到


def test_append_bumps_updated_at():
    a = cs.create_session(1, "问一")
    with session_scope() as s:
        s.get(ChatSession, a).updated_at = datetime(2020, 1, 1)
    cs.append_message(a, "user", "问一")
    with session_scope() as s:
        assert s.get(ChatSession, a).updated_at.year > 2020


def test_recent_history_capped_and_chronological():
    a = cs.create_session(1, "问")
    for i in range(12):
        cs.append_message(a, "user", f"q{i}")
    h = cs.recent_history(a, 8)
    assert len(h) == 8
    assert h[0]["content"] == "q4"
    assert h[-1]["content"] == "q11"


def test_replay_payload_roundtrip_and_utc_suffix():
    a = cs.create_session(1, "问")
    cs.append_message(a, "user", "问")
    cs.append_message(a, "assistant", "答", payload={
        "trace": [{"step": "understand"}], "references": [],
        "graph_facts": [{"source": "四君子汤", "relation": "组成", "target": "人参"}],
        "safety": None})
    msgs = cs.load_messages(a, 1)
    assert [m["role"] for m in msgs] == ["user", "assistant"]
    assert msgs[0]["payload"] is None
    assert msgs[1]["payload"]["graph_facts"][0]["target"] == "人参"
    assert msgs[1]["payload"]["trace"] == [{"step": "understand"}]
    assert msgs[1]["created_at"].endswith("Z")   # naive UTC 必须带 Z，否则前端偏 8 小时
    assert msgs[1]["seq"] > msgs[0]["seq"]
