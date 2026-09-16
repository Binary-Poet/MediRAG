"""FastAPI 入口：阶段 0 仅提供 /health 与 CORS，路由随阶段逐步挂载。"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.chat import router as chat_router
from app.api.config import router as config_router
from app.api.documents import router as documents_router
from app.api.graph_api import router as graph_router
from app.config import get_settings
from app.db import init_db

settings = get_settings()

app = FastAPI(title="本草智问 MediRAG API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(chat_router, prefix="/api")
app.include_router(config_router, prefix="/api")
app.include_router(documents_router, prefix="/api")
app.include_router(graph_router, prefix="/api")


@app.on_event("startup")
def _startup() -> None:
    init_db()


@app.get("/health")
def health() -> dict:
    """健康检查：不依赖任何外部服务，用于阶段 0 验收。"""
    return {"status": "ok", "app": settings.app_name, "env": settings.app_env}
