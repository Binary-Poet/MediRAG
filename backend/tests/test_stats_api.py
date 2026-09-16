"""统计 API：趋势/角色/主题/状态/质量 全来自真实表。"""
from datetime import datetime, timedelta

import pytest
from sqlalchemy import select

import app.db as dbmod
from app.db import session_scope
from app.models.document import Document
from app.models.feedback import Feedback
from app.models.retrieval_log import RetrievalLog


@pytest.fixture(autouse=True)
def _db(monkeypatch):
    eng = dbmod._make_engine("sqlite:///:memory:")
    dbmod.Base.metadata.create_all(eng)
    monkeypatch.setattr(dbmod, "_engine", eng)


def _mk_log(session_id, is_fallback=False):
    with session_scope() as s:
        s.add(RetrievalLog(session_id=session_id, intent="relation",
                           vector_n=5, keyword_n=0, graph_n=3, evidence_n=5,
                           confidence=0.9, is_fallback=is_fallback))


def _mk_feedback(session_id, useful):
    with session_scope() as s:
        s.add(Feedback(session_id=session_id, useful=useful))


def _mk_doc(name, topic, status, chunk_count=1):
    with session_scope() as s:
        s.add(Document(name=name, file_type="md", size=10, topic=topic,
                       status=status, chunk_count=chunk_count))


def test_overview_aggregates(client):
    _mk_log("s1"), _mk_log("s2", is_fallback=True), _mk_log("s3")
    _mk_feedback("s1", True), _mk_feedback("s2", False)
    _mk_doc("a.md", "内科", "就绪", 3), _mk_doc("b.md", "内科", "失败", 0)
    _mk_doc("c.md", "儿科", "就绪")

    r = client.get("/api/stats/overview")
    assert r.status_code == 200
    d = r.json()
    # 趋势：今天有 3 条日志；14 天长度
    assert len(d["trend"]) == 14
    today = datetime.utcnow().strftime("%Y-%m-%d")
    assert next(x for x in d["trend"] if x["date"] == today)["count"] == 3
    assert all(x["count"] == 0 for x in d["trend"] if x["date"] != today)
    # 主题：切片数聚合
    topic = {x["name"]: x["value"] for x in d["topic_dist"]}
    assert topic["内科"] == 3 and topic["儿科"] == 1
    # 状态
    status = {x["name"]: x["value"] for x in d["status_dist"]}
    assert status["就绪"] == 2 and status["失败"] == 1
    # 质量
    q = d["quality"]
    assert q["total"] == 3 and q["fallback_n"] == 1 and q["normal_n"] == 2
    assert q["useful"] == 1 and q["useless"] == 1
    assert q["success_rate"] == pytest.approx(2 / 3, abs=1e-3)
    assert q["satisfaction"] == pytest.approx(0.5)
    # 配置一并带出（推理配置页/概览页联动）
    assert d["config"]["semantic_k"] == 20


def test_overview_empty(client):
    r = client.get("/api/stats/overview")
    assert r.status_code == 200
    d = r.json()
    q = d["quality"]
    assert q["total"] == 0 and q["satisfaction"] == 0 and q["success_rate"] == 0
    assert len(d["trend"]) == 14 and all(x["count"] == 0 for x in d["trend"])
    assert d["topic_dist"] == [] and d["status_dist"] == []
    assert "semantic_k" in d["config"]
    # 形状断言（非 == []）：Task 4 seed 落地后 users 表会有行，只钉 shape 契约
    rd = d["role_dist"]
    assert isinstance(rd, list) and all(set(x) == {"name", "value"} for x in rd)