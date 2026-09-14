"""向量存储：开发期 numpy 余弦后端（Windows 无法运行 milvus-lite）。

接口语义与后续 Milvus collection schema 对齐：
  chunk_id / doc_name / chapter / page_no / topic / text / embedding
阶段后期接 Docker Milvus standalone 时，替换为本模块内的 MilvusVectorStore，
调用方（pipeline / api）不感知后端差异。
"""
import json
import os
from functools import lru_cache

import numpy as np

from app.config import get_settings


class LocalVectorStore:
    """基于 numpy 的归一化余弦检索，JSON 持久化。语料为百级切片，性能足够。"""

    def __init__(self, path: str) -> None:
        self.path = path
        self.chunks: list[dict] = []  # 元数据 + 文本（不含向量）
        self._vectors: dict[str, list[float]] = {}  # chunk_id -> 原始向量
        self._matrix: np.ndarray | None = None  # 归一化后的向量矩阵

    # ===== 写入 =====
    def upsert(self, items: list[dict]) -> int:
        """批量插入/覆盖（按 chunk_id 去重），返回库内总数。"""
        by_id = {c["chunk_id"]: c for c in self.chunks}
        for it in items:
            cid = it["chunk_id"]
            by_id[cid] = {k: v for k, v in it.items() if k != "embedding"}
            self._vectors[cid] = it["embedding"]
        self.chunks = list(by_id.values())
        self._rebuild_matrix()
        return len(self.chunks)

    def _rebuild_matrix(self) -> None:
        if not self.chunks:
            self._matrix = None
            return
        mat = np.array([self._vectors[c["chunk_id"]] for c in self.chunks], dtype=np.float32)
        norms = np.linalg.norm(mat, axis=1, keepdims=True)
        norms[norms == 0] = 1.0
        self._matrix = mat / norms

    # ===== 检索 =====
    def search(self, embedding: list[float], top_k: int = 5) -> list[dict]:
        """余弦相似度检索，返回 top_k 条（含 score）。"""
        if self._matrix is None or not self.chunks:
            return []
        q = np.array(embedding, dtype=np.float32)
        q = q / (np.linalg.norm(q) or 1.0)
        scores = self._matrix @ q
        order = np.argsort(-scores)[:top_k]
        hits = []
        for idx in order:
            hit = {k: v for k, v in self.chunks[int(idx)].items()}
            hit["score"] = float(scores[int(idx)])
            hits.append(hit)
        return hits

    # ===== 持久化 =====
    def save(self) -> None:
        os.makedirs(os.path.dirname(self.path) or ".", exist_ok=True)
        payload = {
            "chunks": self.chunks,
            "vectors": self._vectors,
        }
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False)

    def load(self) -> "LocalVectorStore":
        if not os.path.exists(self.path):
            return self
        with open(self.path, encoding="utf-8") as f:
            payload = json.load(f)
        self.chunks = payload["chunks"]
        self._vectors = payload["vectors"]
        self._rebuild_matrix()
        return self

    def __len__(self) -> int:
        return len(self.chunks)


@lru_cache
def get_store() -> LocalVectorStore:
    """进程级单例：路径来自配置 VECTOR_STORE_PATH。"""
    return LocalVectorStore(get_settings().vector_store_path).load()
