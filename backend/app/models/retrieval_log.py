"""RetrievalLog：每次问答的检索质量日志（运行概览趋势/兜底率数据源；方案 6.6）。"""
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class RetrievalLog(Base):
    __tablename__ = "retrieval_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id: Mapped[str] = mapped_column(String(64), index=True)
    intent: Mapped[str] = mapped_column(String(16))
    vector_n: Mapped[int] = mapped_column(Integer, default=0)
    keyword_n: Mapped[int] = mapped_column(Integer, default=0)
    graph_n: Mapped[int] = mapped_column(Integer, default=0)
    evidence_n: Mapped[int] = mapped_column(Integer, default=0)
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    is_fallback: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)