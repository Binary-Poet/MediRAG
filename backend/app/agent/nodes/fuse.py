"""融合节点：向量+关键词 RRF，图谱独立汇合不参与；rerank 精排 + 置信度判定。

查询分解（2026-09 方案）：候选按 sub_query 标签分组，各自 RRF 后按 chunk_id 合并取最高分；
精排按子查询分别打分取 max——对比型问题用整句做 query 会把「只讲一方实体」的证据系统性压分。

置信度与覆盖度是两个维度：confidence 是全局 max（证据有多强），sub_query_covered 记录各
子查询是否有过阈证据（几个实体真的查到了依据）——只命中一个实体时前者照样很高，后者才
反映得出缺口。
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
    per_sub: list[dict[int, float]] = []
    if fused:
        docs = [f"{c['title']}：{c['text']}" for c in fused]
        best: dict[int, float] = {}
        # 每个子查询一次精排 = 一次独立网络调用，串行会把 2-3 次 rerank 时延直接叠加（实测占
        # 检索编排的大头）。并发发起、主线程汇总取 max，语义与串行逐次 max 完全一致。
        # per_sub 保留各子查询**各自**的打分：合并成 max 后就分不出「哪个实体没依据」了。
        with concurrent.futures.ThreadPoolExecutor(max_workers=max(1, len(queries))) as ex:
            for rs in ex.map(lambda q: rerank(q, docs, top_n=top_n), queries):
                per: dict[int, float] = {}
                for r in rs:
                    per[r["index"]] = r["score"]
                    best[r["index"]] = max(best.get(r["index"], 0.0), r["score"])
                per_sub.append(per)
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

    # 覆盖度：confidence 是全局 max——只命中一个实体也照样高分。实测三联比较
    # 「人参、党参、西洋参」只有人参有依据，confidence 却 0.96、显示「证据充分」，用户会
    # 以为三方都比过了。故另按**各子查询自己的精排最高分**判断该实体有没有依据。
    # 阈值必须比拒答阈值(0.3)严得多：实测（8 题 / 16 子查询）库里没内容的子查询也能靠
    # 「人参 补气」这类近义查询蹭到 0.37~0.44，0.3 完全没有区分度。用 coverage_min_score
    # （见 config 注释里的实测分布）。不能看 matched_queries：演示库仅 13 条切片，任何子查询
    # 都会命中全库，matched 恒为全部子查询。置信度（证据多强）与覆盖度（几个实体有依据）
    # 保持正交，不调小置信度以免误触拒答。
    bar = s.coverage_min_score
    scores = ([round(max(per.values()), 4) if per else 0.0 for per in per_sub]
              if per_sub else [])
    covered = ([bool(per) and max(per.values()) >= bar for per in per_sub]
               if per_sub else [False] * len(queries))
    covered_n = sum(covered)
    partial = (state.get("intent") == "compare" and len(queries) > 1
               and 0 < covered_n < len(queries))
    if low_confidence:
        status = "知识库未匹配"
    elif partial:
        status = f"部分实体无依据（{covered_n}/{len(queries)}）"
    else:
        status = "证据充分，正常生成"

    trace = [
        {"step": "fuse", "candidate_n": len(fused), "method": "RRF", "sub_query_n": len(queries)},
        {"step": "rerank", "evidence_n": len(evidence), "confidence": round(confidence, 4),
         "status": status, "covered_n": covered_n, "sub_query_n": len(queries)},
    ]
    return {"fused": fused, "evidence": evidence, "confidence": confidence,
            "low_confidence": low_confidence, "sub_query_covered": covered,
            "sub_query_scores": scores, "trace": trace}


def reflect_edge(state: AgentState) -> str:
    """fuse 之后：证据不足且未达上限且意图非闲聊 → reflect；否则 safety。"""
    if state["intent"] == "chitchat":
        return "safety"
    insufficient = (not state["evidence"] or state["low_confidence"]) and not state["graph_facts"]
    if insufficient and state["reflect_count"] < REFLECT_MAX:
        return "reflect"
    return "safety"