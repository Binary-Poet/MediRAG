"""关键词检索：jieba 分词 + rank-bm25 内存索引（语料为百级切片，性能足够）。

索引构建自 vector store 的同一批切片（get_store().chunks），保证
向量/关键词两路元数据与 chunk_id 一致性，供 RRF 按 chunk_id 去重融合。
"""
import jieba
from rank_bm25 import BM25Okapi

from app.retrieval.vector_store import get_store


class KeywordIndex:
    def __init__(self) -> None:
        self._bm25: BM25Okapi | None = None
        self._chunks: list[dict] = []

    def build(self, chunks: list[dict]) -> int:
        """全量重建索引，返回切片数。"""
        self._chunks = list(chunks)
        corpus = [jieba.lcut(f"{c['title']}：{c['text']}") for c in self._chunks]
        self._bm25 = BM25Okapi(corpus)
        return len(self._chunks)

    def search(self, query: str, top_k: int = 20) -> list[dict]:
        if self._bm25 is None or not self._chunks:
            return []
        scores = self._bm25.get_scores(jieba.lcut(query))
        order = sorted(range(len(scores)), key=lambda i: -scores[i])[:top_k]
        return [
            {**self._chunks[i], "score": float(scores[i])}
            for i in order if scores[i] > 0.0
        ]


_index: KeywordIndex | None = None


def get_keyword_index() -> KeywordIndex:
    """进程级单例：懒构建，语料来自向量库已入库切片。"""
    global _index
    if _index is None:
        _index = KeywordIndex()
        _index.build(get_store().chunks)
    return _index