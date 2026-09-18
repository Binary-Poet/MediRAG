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


def test_delete_all_sessions_only_removes_own():
    """清空只删自己的会话与消息。

    消息表无外键、子表删除是按 session_id 集合做的：一旦集合里混进别人的会话 id，
    就会连带删掉他人消息，故这里专门断言他人会话与消息完好。
    """
    mine = cs.create_session(1, "我的问一")
    cs.append_message(mine, "user", "我的问一")
    cs.append_message(mine, "assistant", "答一")
    mine2 = cs.create_session(1, "我的问二")
    cs.append_message(mine2, "user", "我的问二")
    other = cs.create_session(2, "别人的问")
    cs.append_message(other, "user", "别人的问")

    assert cs.delete_all_sessions(1) == 2
    assert cs.list_sessions(1)["total"] == 0
    assert cs.load_messages(mine, 1) is None
    assert cs.list_sessions(2)["total"] == 1
    assert [m["content"] for m in cs.load_messages(other, 2)] == ["别人的问"]


def test_delete_all_sessions_when_empty_returns_zero():
    assert cs.delete_all_sessions(1) == 0
    assert cs.delete_all_sessions(2) == 0


def test_delete_all_sessions_favorite_only_keeps_unfavorited():
    """favorite_only=True 只清收藏：对应前端停在「已收藏」筛选页时的清空。"""
    fav = cs.create_session(1, "收藏的问")
    cs.append_message(fav, "user", "收藏的问")
    cs.append_message(fav, "assistant", "答")
    plain = cs.create_session(1, "没收藏的问")
    cs.append_message(plain, "user", "没收藏的问")
    cs.set_favorite(fav, 1, True)

    assert cs.delete_all_sessions(1, favorite_only=True) == 1
    assert cs.load_messages(fav, 1) is None                    # 收藏的被删（含消息）
    assert cs.list_sessions(1)["favorite_total"] == 0
    assert cs.list_sessions(1)["total"] == 1
    assert [m["content"] for m in cs.load_messages(plain, 1)] == ["没收藏的问"]


def test_delete_all_sessions_favorite_only_isolated_by_user():
    """按收藏清空同样不能越权：只删自己的收藏。"""
    mine = cs.create_session(1, "我的收藏")
    cs.set_favorite(mine, 1, True)
    other = cs.create_session(2, "别人的收藏")
    cs.set_favorite(other, 2, True)

    assert cs.delete_all_sessions(1, favorite_only=True) == 1
    assert cs.list_sessions(1)["total"] == 0
    assert cs.list_sessions(2)["favorite_total"] == 1


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


def test_append_returns_seq_for_round_locating():
    """append 返回 seq：撤回要按指定轮精确定位，光靠「最后两条」在撤回非末轮时会删错。"""
    a = cs.create_session(1, "问一")
    assert cs.append_message(a, "user", "问一") == 1
    assert cs.append_message(a, "assistant", "答一") == 2
    assert cs.append_message(a, "user", "问二") == 3


def test_withdraw_last_round_keeps_session_and_title():
    a = cs.create_session(1, "第一问")
    cs.append_message(a, "user", "第一问")
    cs.append_message(a, "assistant", "答一")
    cs.append_message(a, "user", "第二问")
    cs.append_message(a, "assistant", "答二")

    assert cs.withdraw_round(a, 1) == {"deleted": 2, "session_deleted": False}
    assert [m["content"] for m in cs.load_messages(a, 1)] == ["第一问", "答一"]
    with session_scope() as s:
        assert s.get(ChatSession, a).title == "第一问"


def test_withdraw_only_round_deletes_session():
    a = cs.create_session(1, "唯一一问")
    cs.append_message(a, "user", "唯一一问")
    cs.append_message(a, "assistant", "答")

    assert cs.withdraw_round(a, 1) == {"deleted": 2, "session_deleted": True}
    assert cs.list_sessions(1)["total"] == 0
    assert cs.load_messages(a, 1) is None     # 会话没了，消息也不该能读到


def test_withdraw_trailing_user_message_when_answer_failed():
    """生成阶段失败时只剩提问（没有回答），撤回只删 1 条，不误删上一轮的回答。"""
    a = cs.create_session(1, "问一")
    cs.append_message(a, "user", "问一")
    cs.append_message(a, "assistant", "答一")
    cs.append_message(a, "user", "问二（生成失败）")

    assert cs.withdraw_round(a, 1) == {"deleted": 1, "session_deleted": False}
    assert [m["content"] for m in cs.load_messages(a, 1)] == ["问一", "答一"]


def test_withdraw_middle_round_rolls_back_that_round_and_after():
    """撤回是回滚：撤第 2 轮会把第 2、3 轮一起去掉，第 1 轮原样保留。

    只删中间一轮会留下「第1轮 → 第3轮」的断档——后续轮次本就建立在该轮上下文之上。
    """
    a = cs.create_session(1, "第一问")
    cs.append_message(a, "user", "第一问")
    cs.append_message(a, "assistant", "答一")
    second = cs.append_message(a, "user", "第二问")
    cs.append_message(a, "assistant", "答二")
    cs.append_message(a, "user", "第三问")
    cs.append_message(a, "assistant", "答三")

    assert cs.withdraw_round(a, 1, seq=second) == {"deleted": 4, "session_deleted": False}
    assert [m["content"] for m in cs.load_messages(a, 1)] == ["第一问", "答一"]
    with session_scope() as s:
        assert s.get(ChatSession, a).title == "第一问"    # 首轮未动，标题不变


def test_withdraw_first_round_removes_all_rounds_and_session():
    """撤首轮 = 回到会话还没建之前：全部轮次删掉，会话一并删除。"""
    a = cs.create_session(1, "第一问")
    for q, ans in (("第一问", "答一"), ("第二问", "答二"), ("第三问", "答三")):
        cs.append_message(a, "user", q)
        cs.append_message(a, "assistant", ans)

    assert cs.withdraw_round(a, 1, seq=1) == {"deleted": 6, "session_deleted": True}
    assert cs.load_messages(a, 1) is None
    assert cs.list_sessions(1)["total"] == 0


def test_withdraw_rejects_unknown_seq_and_foreign_session():
    a = cs.create_session(1, "问")
    cs.append_message(a, "user", "问")
    cs.append_message(a, "assistant", "答")

    assert cs.withdraw_round(a, 1, seq=999) is None    # 该轮不存在
    assert cs.withdraw_round(a, 2) is None             # 别人的会话
    assert cs.withdraw_round("不存在的会话", 1) is None
    assert len(cs.load_messages(a, 1)) == 2            # 失败路径不得误删
