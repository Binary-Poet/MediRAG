"""InferenceConfig：全局单行推理配置（阶段 5 推理配置页落库；方案 6.6）。"""
from sqlalchemy import Float, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class InferenceConfig(Base):
    __tablename__ = "inference_config"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    semantic_k: Mapped[int] = mapped_column(Integer, default=20)   # 语义召回数
    keyword_k: Mapped[int] = mapped_column(Integer, default=20)    # 关键词召回数
    fuse_candidate: Mapped[int] = mapped_column(Integer, default=25)  # 融合候选数
    final_evidence: Mapped[int] = mapped_column(Integer, default=5)   # 最终证据数
    rrf_k: Mapped[int] = mapped_column(Integer, default=60)       # 融合平衡系数
    model: Mapped[str] = mapped_column(String(32), default="deepseek-chat")
    answer_temp: Mapped[float] = mapped_column(Float, default=0.3)
    query_temp: Mapped[float] = mapped_column(Float, default=0.1)