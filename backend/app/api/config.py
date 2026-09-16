"""推理配置 API：GET 当前生效值 / PUT 保存（下一次问答请求生效）。"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.services.inference_config import (defaults, load_inference_config,
                                           save_inference_config)

router = APIRouter()


class ConfigBody(BaseModel):
    semantic_k: int
    keyword_k: int
    fuse_candidate: int
    final_evidence: int
    rrf_k: int
    model: str
    answer_temp: float
    query_temp: float


@router.get("/config")
def get_config() -> dict:
    return {"items": load_inference_config()}


@router.put("/config")
def put_config(body: ConfigBody) -> dict:
    try:
        return save_inference_config(body.model_dump())
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))