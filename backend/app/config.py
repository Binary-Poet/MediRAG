"""全局配置：pydantic-settings 读取 backend/.env。

默认值与《MediRAG-合并改造方案.md》5.1 运行默认配置一致（API 优先）。
未提供 .env 时使用此处默认值即可启动（/health 不依赖任何外部服务）。
"""
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # ===== 应用 =====
    app_name: str = "MediRAG"
    app_env: str = "dev"
    cors_origins: list[str] = ["http://localhost:5173"]

    # ===== 聊天模型（API 优先）=====
    llm_vendor: str = "deepseek"
    llm_model_main: str = "deepseek-chat"
    llm_model_alt: str = "qwen-plus"
    deepseek_api_key: str = ""
    deepseek_base_url: str = "https://api.deepseek.com"
    dashscope_api_key: str = ""
    dashscope_base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"

    # ===== Embedding / Rerank（API 优先，可切 local）=====
    embed_vendor: str = "siliconflow"
    embed_model: str = "BAAI/bge-m3"
    embed_dim: int = 1024
    rerank_vendor: str = "siliconflow"
    rerank_model: str = "BAAI/bge-reranker-v2-m3"
    siliconflow_api_key: str = ""
    siliconflow_base_url: str = "https://api.siliconflow.cn/v1"

    # ===== 向量库（阶段 1：numpy 本地后端；Windows 不支持 milvus-lite，后续接 Milvus standalone）=====
    vector_store: str = "numpy_local"
    vector_store_path: str = "../data/vectorstore/index.json"
    milvus_uri: str = "../data/milvus/medirag.db"
    milvus_collection: str = "tcm_chunks"

    # ===== 混合检索（阶段 2；阶段 5 改为用户级推理配置存储）=====
    semantic_k: int = 20        # 语义召回数
    keyword_k: int = 20         # 关键词召回数
    fuse_candidate: int = 25    # 融合候选数
    final_evidence: int = 5     # 最终证据数
    rrf_k: int = 60             # 融合平衡系数
    rerank_top_n: int = 5       # 精排取前 N（与 final_evidence 联动）
    evidence_min_score: float = 0.3   # rerank 相关性阈值：top 分低于此且无图谱事实 → 拒答兜底

    # ===== Neo4j / MySQL（docker compose 启动）=====
    neo4j_uri: str = "bolt://localhost:7687"
    neo4j_user: str = "neo4j"
    neo4j_password: str = "medirag123"
    mysql_dsn: str = "mysql+pymysql://medirag:medirag123@localhost:3306/medirag"

    # ===== 记忆/缓存 =====
    redis_mode: str = "memory"
    redis_url: str = "redis://localhost:6379/0"


@lru_cache
def get_settings() -> Settings:
    return Settings()
