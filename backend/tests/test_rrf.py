"""RRF 测试：去重 / 排序 / 权重 / 跨路同分。"""
from app.retrieval.rrf import rrf_fuse


def _chunk(cid):
    return {"chunk_id": cid, "title": cid, "text": cid, "score": 0.5}


def test_fuse_dedup_shared_chunk_and_rank_above_single():
    a, b, c = _chunk("a"), _chunk("b"), _chunk("c")
    fused = rrf_fuse([[a, b], [b, c]], k=60)

    ids = [d["chunk_id"] for d in fused]
    assert ids == ["b", "a", "c"]  # b 双路命中居首，随后按融合分
    assert len(fused) == 3
    assert fused[0]["rrf_score"] > fused[1]["rrf_score"] + 1e-9


def test_fuse_weights_shift_ranking():
    a, b = _chunk("a"), _chunk("b")
    # 次序反转判别：a=100/61≈1.639 > b=100/62+1/61≈1.630 → [a, b]
    # 若实现忽略权重：b=1/62+1/61≈0.0325 > a=1/61≈0.0164 → [b, a]，测试必失败
    fused = rrf_fuse([[a, b], [b]], k=60, weights=[100.0, 1.0])
    assert [d["chunk_id"] for d in fused] == ["a", "b"]
    # 归一权重下次序为 [b, a]（跨路去重排首），验证函数整体仍按融合分正确排序
    plain = rrf_fuse([[a, b], [b]], k=60)
    assert [d["chunk_id"] for d in plain] == ["b", "a"]


def test_fuse_empty_and_empty_lists():
    assert rrf_fuse([], k=60) == []
    assert rrf_fuse([[], []], k=60) == []