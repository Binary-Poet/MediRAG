"""融合节点：向量+关键词 RRF，图谱独立汇合不参与；rerank 精排 + 置信度判定。

查询分解（2026-09 方案）：候选按 sub_query 标签分组，各自 RRF 后按 chunk_id 合并取最高分；
精排按子查询分别打分取 max——对比型问题用整句做 query 会把「只讲一方实体」的证据系统性压分。
"""
import concurrent.futures

from app.agent.state import AgentState
from app.config import get_settings
from app.llm.rerank import rerank
from app.retrieval.rrf import rrf_fuse

REFLECT_MAX = 1


def _sub_groups(hits, n_subs: int) -> list[list[dict]]:
    """按命中上的 sub_query 标签分组；标签缺失/越界归入第 0 组（兼容老路径与测试 fake）。"""
    groups: list[list[dict]] = [[] for _ in range(n_subs)]
    for h in hits or []:
        if not isinstance(h, dict):
            continue
        i = h.get("sub_query", 0)
        groups[i if isinstance(i, int) and 0 <= i < n_subs else 0].append(h)
    return groups


def fuse(state: AgentState) -> dict:
    s = get_settings()
    cfg = state.get("inference") or {}
    queries = [sq["query"] for sq in (state.get("sub_queries") or []) if sq.get("query")] \
        or [state["rewritten_query"]]
    rrf_k = cfg.get("rrf_k", s.rrf_k)
    top_n = cfg.get("final_evidence", s.rerank_top_n)

    v_groups = _sub_groups(state["vector_hits"], len(queries))
    k_groups = _sub_groups(state["keyword_hits"], len(queries))

    # 每子查询各自 RRF，再按 chunk_id 合并取最高 rrf 分（同一切片可被多个子查询命中）
    merged: dict[str, dict] = {}
    matched: dict[str, list[int]] = {}
    for i in range(len(queries)):
        for c in rrf_fuse([v_groups[i], k_groups[i]], k=rrf_k):
            cid = c["chunk_id"]
            matched.setdefault(cid, []).append(i)
            if cid not in merged or c["rrf_score"] > merged[cid]["rrf_score"]:
                merged[cid] = c
    fused = sorted(merged.values(), key=lambda c: -c["rrf_score"])[:cfg.get("fuse_candidate", s.fuse_candidate)]

    evidence: list[dict] = []
    if fused:
        docs = [f"{c['title']}：{c['text']}" for c in fused]
        best: dict[int, float] = {}
        # 每个子查询一次精排 = 一次独立网络调用，串行会把 2-3 次 rerank 时延直接叠加（实测占
        # 检索编排的大头）。并发发起、主线程汇总取 max，语义与串行逐次 max 完全一致。
        with concurrent.futures.ThreadPoolExecutor(max_workers=max(1, len(queries))) as ex:
            for rs in ex.map(lambda q: rerank(q, docs, top_n=top_n), queries):
                for r in rs:
                    best[r["index"]] = max(best.get(r["index"], 0.0), r["score"])
        evidence = sorted(
            ({**fused[i], "score": sc, "matched_queries": matched.get(fused[i]["chunk_id"], [])}
             for i, sc in best.items()),
            key=lambda e: -e["score"])[:top_n]

    confidence = max((e["score"] for e in evidence), default=0.0)
    low_confidence = bool(evidence) and evidence[0]["score"] < s.evidence_min_score

    # 图谱强证据豁免：低置信但图谱命中 → 剔除低分文献噪声（阶段 2 R8 语义）
    if low_confidence and state.get("graph_facts"):
        evidence = [e for e in evidence if e["score"] >= s.evidence_min_score]
        confidence = max((e["score"] for e in evidence), default=0.0)

    trace = [
        {"step": "fuse", "candidate_n": len(fused), "method": "RRF", "sub_query_n": len(queries)},
        {"step": "rerank", "evidence_n": len(evidence), "confidence": round(confidence, 4),
         "status": "证据充分，正常生成" if not low_confidence else "知识库未匹配"},
    ]
    return {"fused": fused, "evidence": evidence, "confidence": confidence,
            "low_confidence": low_confidence, "trace": trace}


def reflect_edge(state: AgentState) -> str:
    """fuse 之后：证据不足且未达上限且意图非闲聊 → reflect；否则 safety。"""
    if state["intent"] == "chitchat":
        return "safety"
    insufficient = (not state["evidence"] or state["low_confidence"]) and not state["graph_facts"]
    if insufficient and state["reflect_count"] < REFLECT_MAX:
        return "reflect"
    return "safety"