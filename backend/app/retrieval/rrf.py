"""RRF（Reciprocal Rank Fusion）：向量 + 关键词两路按 chunk_id 去重累加。

公式与合并方案 6.3 伪码一致：score += w * 1 / (k + rank + 1)。
k 对应推理配置页「融合平衡系数 60」。
"""


def rrf_fuse(rank_lists: list[list[dict]], k: int = 60,
             weights: list[float] | None = None) -> list[dict]:
    if not rank_lists:
        return []
    ws = weights or [1.0] * len(rank_lists)
    scores: dict[str, float] = {}
    by_id: dict[str, dict] = {}
    for docs, w in zip(rank_lists, ws):
        for rank, d in enumerate(docs):
            cid = d["chunk_id"]
            scores[cid] = scores.get(cid, 0.0) + w * (1.0 / (k + rank + 1))
            by_id[cid] = d
    return [
        {**by_id[cid], "rrf_score": s}
        for cid, s in sorted(scores.items(), key=lambda x: -x[1])
    ]