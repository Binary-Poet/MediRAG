"""运行概览统计（规格 P1：数据来自真实接口，非写死）。"""
from datetime import datetime, timedelta

from fastapi import APIRouter
from sqlalchemy import func, select

from app.db import session_scope
from app.models.document import Document
from app.models.feedback import Feedback
from app.models.retrieval_log import RetrievalLog
from app.models.user import User
from app.services.inference_config import load_inference_config

router = APIRouter()


def _trend() -> list[dict]:
    today = datetime.utcnow().date()
    start = today - timedelta(days=13)
    with session_scope() as s:
        rows = s.execute(
            select(func.date(RetrievalLog.created_at), func.count(RetrievalLog.id))
            .where(RetrievalLog.created_at >= datetime(start.year, start.month, start.day))
            .group_by(func.date(RetrievalLog.created_at))
        ).all()
    counts = {str(d): c for d, c in rows}
    return [{"date": (start + timedelta(days=i)).isoformat(),
             "count": counts.get((start + timedelta(days=i)).isoformat(), 0)}
            for i in range(14)]


def _role_dist() -> list[dict]:
    with session_scope() as s:
        rows = s.execute(select(User.role, func.count(User.id)).group_by(User.role)).all()
    return [{"name": r, "value": c} for r, c in rows]


def _topic_dist() -> list[dict]:
    with session_scope() as s:
        rows = s.execute(
            select(Document.topic, func.coalesce(func.sum(Document.chunk_count), 0))
            .group_by(Document.topic)).all()
    return [{"name": t, "value": int(c)} for t, c in rows]


def _status_dist() -> list[dict]:
    with session_scope() as s:
        rows = s.execute(select(Document.status, func.count(Document.id))
                         .group_by(Document.status)).all()
    return [{"name": st, "value": c} for st, c in rows]


def _quality() -> dict:
    with session_scope() as s:
        total = s.execute(select(func.count(RetrievalLog.id))).scalar_one()
        fallback_n = s.execute(
            select(func.count(RetrievalLog.id)).where(RetrievalLog.is_fallback)).scalar_one()
        useful = s.execute(
            select(func.count(Feedback.id)).where(Feedback.useful)).scalar_one()
        useless = s.execute(
            select(func.count(Feedback.id)).where(Feedback.useful.is_(False))).scalar_one()
    normal_n = total - fallback_n
    satisfaction = (useful / (useful + useless)) if (useful + useless) else 0.0
    success_rate = (normal_n / total) if total else 0.0
    return {"total": total, "fallback_n": fallback_n, "normal_n": normal_n,
            "useful": useful, "useless": useless,
            "satisfaction": round(satisfaction, 3), "success_rate": round(success_rate, 3)}


@router.get("/stats/overview")
def overview() -> dict:
    return {"trend": _trend(), "role_dist": _role_dist(), "topic_dist": _topic_dist(),
            "status_dist": _status_dist(), "quality": _quality(),
            "config": load_inference_config()}