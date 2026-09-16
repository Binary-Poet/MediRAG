from unittest.mock import MagicMock

import pytest

import app.api.chat as chatmod
import app.db as dbmod


@pytest.fixture(autouse=True)
def _db(monkeypatch):
    eng = dbmod._make_engine("sqlite:///:memory:")
    dbmod.init_db(eng)                      # 建表 + seed 三用户（登录取 Bearer 用）
    monkeypatch.setattr(dbmod, "_engine", eng)


def _auth(client) -> dict:
    tok = client.post("/api/auth/login",
                      json={"username": "admin", "password": "admin123"}).json()["token"]
    return {"Authorization": f"Bearer {tok}"}


def _patch_agent(client, monkeypatch, *, safety="ok", answer=None, safety_message=""):
    """monkeypatch get_agent 返回一个假编译图：invoke/stream 返回统一 final state。"""
    final = {
        "question": "四君子汤由哪些中药组成？", "session_id": "", "chat_history": [],
        "rewritten_query": "四君子汤组成", "entities": [], "entity_names": ["四君子汤"],
        "intent": "relation", "plan": ["vector_search", "graph_search"],
        "vector_hits": [], "keyword_hits": [], "graph_facts": [
            {"source": "四君子汤", "relation": "组成", "target": "人参", "source_type": "方剂", "target_type": "中药"}],
        "fused": [], "evidence": [{"chunk_id": "a", "title": "四君子汤", "doc_name": "中药方剂学基础",
                                   "chapter": "第1节", "page_no": 1, "text": "组成", "score": 0.9}],
        "confidence": 0.9, "low_confidence": False, "reflect_count": 0,
        "safety_flag": safety, "safety_message": safety_message, "prompt": "P",
        "answer": answer or "", "trace": [
            {"step": "understand", "rewritten": "四君子汤组成"},
            {"step": "retrieve", "vector_n": 1, "graph_n": 1},
            {"step": "rerank", "evidence_n": 1, "confidence": 0.9, "status": "证据充分，正常生成"}],
    }
    fake_graph = MagicMock()
    fake_graph.stream.return_value = [  # 单键 dict：langgraph 1.x stream_mode="updates" 真实形状
        {"understand": {"rewritten_query": "四君子汤组成", "trace": [{"step": "understand"}]}},
        {"retrieve": {"vector_hits": [], "graph_facts": final["graph_facts"], "trace": [{"step": "retrieve", "vector_n": 0, "graph_n": 1}]}},
        {"fuse": {"evidence": final["evidence"], "confidence": 0.9,
                   "trace": [{"step": "fuse", "candidate_n": 1}, {"step": "rerank", "evidence_n": 1, "confidence": 0.9, "status": "证据充分，正常生成"}]}},
        {"safety": {"safety_flag": safety}},
        {"context": {"prompt": "P"}},
    ]
    monkeypatch.setattr(chatmod, "get_agent", lambda: fake_graph)
    monkeypatch.setattr(chatmod, "chat_completion_stream", lambda system, user, temperature=0.3, vendor=None, model=None: iter(["四君子汤由人参、白术、茯苓、炙甘草组成 [1]"]))
    return fake_graph


def test_stream_emits_expected_events(client, monkeypatch):
    fake = _patch_agent(client, monkeypatch)
    with client.stream("POST", "/api/chat/stream", json={"question": "四君子汤由哪些中药组成？"}, headers=_auth(client)) as resp:
        assert resp.status_code == 200
        raw = "".join(resp.iter_text())
    # 事件顺序：step...、token、references、safety、done
    assert "event: step" in raw
    assert "event: token" in raw
    assert "event: references" in raw
    assert "event: done" in raw
    assert "组成" in raw


def test_stream_low_confidence_emits_safety_and_fallback_text(client, monkeypatch):
    _patch_agent(client, monkeypatch, safety="low_confidence",
                 safety_message="知识库中未检索到可靠依据。", answer="知识库中未检索到可靠依据。")
    with client.stream("POST", "/api/chat/stream", json={"question": "今天天气"}, headers=_auth(client)) as resp:
        raw = "".join(resp.iter_text())
    assert '"type": "low_confidence"' in raw
    assert "知识库中未检索到可靠依据" in raw


def test_stream_low_confidence_emits_no_token_event(client, monkeypatch):
    # 低置信分支无 LLM 生成：只发 safety，不发 token（前端以框渲染兜底话术）
    _patch_agent(client, monkeypatch, safety="low_confidence",
                 safety_message="知识库中未检索到可靠依据。", answer="知识库中未检索到可靠依据。")
    with client.stream("POST", "/api/chat/stream", json={"question": "今天天气"}, headers=_auth(client)) as resp:
        raw = "".join(resp.iter_text())
    assert "event: safety" in raw
    assert "event: token" not in raw


def test_stream_emergency_injects_emergency_system_prompt(client, monkeypatch):
    # 急症分支：就医约束需注入 system prompt，保证回答开头出现加粗就医提示
    _patch_agent(client, monkeypatch, safety="emergency",
                 safety_message="您提到的情况可能属于急症，请立即就医或拨打 120。")
    seen = {}

    def _cap(system, user, temperature=0.3, vendor=None, model=None):
        seen["system"] = system
        yield "请立即就医"

    monkeypatch.setattr(chatmod, "chat_completion_stream", _cap)
    with client.stream("POST", "/api/chat/stream", json={"question": "我胸痛"}, headers=_auth(client)) as resp:
        raw = "".join(resp.iter_text())
    assert '"type": "emergency"' in raw
    assert "120" in seen["system"]


def test_stream_empty_question_rejected(client):
    resp = client.post("/api/chat/stream", json={"question": ""}, headers=_auth(client))
    assert resp.status_code == 422


def test_stream_generation_error_emits_error_event(client, monkeypatch):
    _patch_agent(client, monkeypatch)

    def _boom(system, user, temperature=0.3, vendor=None, model=None):
        raise RuntimeError("LLM 网络故障")
        yield  # pragma: no cover

    monkeypatch.setattr(chatmod, "chat_completion_stream", _boom)
    with client.stream("POST", "/api/chat/stream", json={"question": "四君子汤组成"}, headers=_auth(client)) as resp:
        assert resp.status_code == 200
        raw = "".join(resp.iter_text())
    assert "event: error" in raw
    assert "LLM 网络故障" in raw


def test_stream_graph_error_emits_error_event(client, monkeypatch):
    # 图阶段抛非 RuntimeError（如 ValueError）时仍收口为 error 事件（对齐 S4）
    fake_graph = MagicMock()
    fake_graph.stream.side_effect = ValueError("图执行失败")
    monkeypatch.setattr(chatmod, "get_agent", lambda: fake_graph)
    with client.stream("POST", "/api/chat/stream", json={"question": "四君子汤组成"}, headers=_auth(client)) as resp:
        assert resp.status_code == 200
        raw = "".join(resp.iter_text())
    assert "event: error" in raw
    assert "图执行失败" in raw


def test_stream_persists_turn_and_claims_session(client, monkeypatch):
    """本轮问答落库：done 返回的 message_id 即会话 id，且消息可回放。"""
    import json as _json

    from app.db import session_scope
    from app.models.chat import ChatMessage, ChatSession
    from app.services import chat_session as cs

    _patch_agent(client, monkeypatch)
    with client.stream("POST", "/api/chat/stream",
                       json={"question": "四君子汤由哪些中药组成？"},
                       headers=_auth(client)) as resp:
        raw = "".join(resp.iter_text())
    done = [ln for ln in raw.splitlines() if ln.startswith("data:") and "message_id" in ln][0]
    sid = _json.loads(done[len("data:"):].strip())["message_id"]

    with session_scope() as s:
        assert s.get(ChatSession, sid).title == "四君子汤由哪些中药组成？"
        msgs = s.query(ChatMessage).filter_by(session_id=sid).order_by(ChatMessage.seq).all()
    assert [m.role for m in msgs] == ["user", "assistant"]
    assert msgs[0].payload is None
    assert msgs[1].payload["graph_facts"][0]["target"] == "人参"
    assert msgs[1].payload["safety"] is None
    assert cs.load_messages(sid, 1) is not None


def test_stream_rejects_foreign_session(client, monkeypatch):
    """带上不属于自己的 session_id → 404，不能往他人会话灌消息。"""
    from app.services import chat_session as cs

    _patch_agent(client, monkeypatch)
    foreign = cs.create_session(2, "user1 的会话")
    r = client.post("/api/chat/stream", json={"question": "问", "session_id": foreign},
                    headers=_auth(client))       # admin 的 token，id=1
    assert r.status_code == 404


def test_stream_requires_auth(client):
    assert client.post("/api/chat/stream", json={"question": "问"}).status_code == 401


def _done_session_id(raw: str) -> str:
    import json as _json
    line = [ln for ln in raw.splitlines() if ln.startswith("data:") and "message_id" in ln][0]
    return _json.loads(line[len("data:"):].strip())["message_id"]


def test_chat_reads_history_before_appending_current_question(client, monkeypatch):
    """时序不变量（本计划 #1 全局约束）：建会话 → 取历史 → 写当前提问 → 跑图。

    历史必须是「本轮之前」的历史。把 chat.py 的 get_history / append_message 对调
    后，若没有以下断言则整套测试仍会全绿（假图从不消费 chat_history，无人察觉），
    线上表现却是「每轮追问把自己的问题也当历史再答一遍」。故用三层断言钉死：
      1) 调用顺序：前三步依次是 建会话 → 取历史 → 写提问；
      2) 后果：本轮提问不出现在本轮 chat_history；
      3) 后果：第二轮能读到第一问原文（历史确实生效），且仍不含本轮提问。
    """
    q1, q2 = "四君子汤由哪些中药组成？", "它的禁忌是什么？"

    fake = _patch_agent(client, monkeypatch)         # 复用假图 + 假 LLM
    chunks = list(fake.stream.return_value)          # 保住原有 chunk 列表，只接管入参
    histories: list[list[dict]] = []

    def _capture(initial, *args, **kwargs):
        histories.append(list(initial.get("chat_history", [])))
        return iter(chunks)

    fake.stream.side_effect = _capture

    order: list[str] = []
    real_create = chatmod.chat_session.create_session
    real_history = chatmod.get_history
    real_append = chatmod.chat_session.append_message

    def spy_create(*a, **k):
        order.append("create_session")
        return real_create(*a, **k)

    def spy_history(*a, **k):
        order.append("get_history")
        return real_history(*a, **k)

    def spy_append(*a, **k):
        order.append("append_message")
        return real_append(*a, **k)

    # get_history 是 `from app.agent.memory import get_history` 直接导入，必须打在模块属性上
    monkeypatch.setattr(chatmod.chat_session, "create_session", spy_create)
    monkeypatch.setattr(chatmod, "get_history", spy_history)
    monkeypatch.setattr(chatmod.chat_session, "append_message", spy_append)

    headers = _auth(client)
    with client.stream("POST", "/api/chat/stream", json={"question": q1}, headers=headers) as resp:
        sid = _done_session_id("".join(resp.iter_text()))
    with client.stream("POST", "/api/chat/stream", json={"question": q2, "session_id": sid},
                       headers=headers) as resp:
        "".join(resp.iter_text())

    # 1) 顺序断言
    assert order[:3] == ["create_session", "get_history", "append_message"]
    # 2) 后果断言：本轮提问不在本轮历史里（对调后第一轮历史会含 q1）
    assert all(m["content"] != q1 for m in histories[0])
    # 3) 后果断言：第二轮历史含第一问原文，且不含本轮提问
    assert any(m["content"] == q1 for m in histories[1])
    assert all(m["content"] != q2 for m in histories[1])
