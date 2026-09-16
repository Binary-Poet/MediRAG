"""推理配置即服务：DB 单行 ↔ dict；未落库时回落 get_settings() 默认（与截图一致）。"""
from sqlalchemy import select

from app.config import get_settings
from app.db import session_scope
from app.models.inference_config import InferenceConfig

MODEL_FIELD_RANGES = {
    "semantic_k": (1, 100), "keyword_k": (1, 100), "fuse_candidate": (1, 100),
    "final_evidence": (1, 100), "rrf_k": (1, 200),
}
TEMP_FIELDS = ("answer_temp", "query_temp")
MODELS = {"deepseek-chat", "qwen-plus"}


def defaults() -> dict:
    s = get_settings()
    return {"semantic_k": s.semantic_k, "keyword_k": s.keyword_k,
            "fuse_candidate": s.fuse_candidate, "final_evidence": s.final_evidence,
            "rrf_k": s.rrf_k, "model": "deepseek-chat",
            "answer_temp": 0.3, "query_temp": 0.1}


def load_inference_config() -> dict:
    """返回带全部字段的配置 dict；无存行时回落 settings 默认。"""
    with session_scope() as s:
        row = s.execute(select(InferenceConfig)).scalar_one_or_none()
    if row is None:
        return defaults()
    return {"semantic_k": row.semantic_k, "keyword_k": row.keyword_k,
            "fuse_candidate": row.fuse_candidate, "final_evidence": row.final_evidence,
            "rrf_k": row.rrf_k, "model": row.model or "deepseek-chat",
            "answer_temp": row.answer_temp, "query_temp": row.query_temp}


def validate(body: dict) -> None:
    """校验范围；违规抛 ValueError（detail 含字段名）。"""
    for f, (lo, hi) in MODEL_FIELD_RANGES.items():
        v = body.get(f)
        if not isinstance(v, int) or not (lo <= v <= hi):
            raise ValueError(f"{f} 取值 {lo}~{hi}")
    for f in TEMP_FIELDS:
        v = body.get(f)
        if not isinstance(v, (int, float)) or not (0 <= v <= 2):
            raise ValueError(f"{f} 取值 0~2")
    if body.get("model") not in MODELS:
        raise ValueError("model 取值 deepseek-chat|qwen-plus")


def save_inference_config(body: dict) -> dict:
    validate(body)
    with session_scope() as s:
        row = s.execute(select(InferenceConfig)).scalar_one_or_none()
        if row is None:
            row = InferenceConfig(id=1)
            s.add(row)
        for k in defaults():
            setattr(row, k, body[k])
    return body