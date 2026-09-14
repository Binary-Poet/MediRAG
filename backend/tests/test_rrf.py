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
    # 路 1 权重 10 > 路 2 权重 1：a 双分仍应超过 b 单分？此处验证权重放大路面排名
    fused = rrf_fuse([[a], [b]], k=60, weights=[10.0, 1.0])
    assert fused[0]["chunk_id"] == "a"
    double = rrf_fuse([[a, b], [b, c := _chunk("c")]], k=60, weights=[1.0, 1.0])
    assert double[0]["chunk_id"] == "b"


def test_fuse_empty_and_empty_lists():
    assert rrf_fuse([], k=60) == []
    assert rrf_fuse([[], []], k=60) == []