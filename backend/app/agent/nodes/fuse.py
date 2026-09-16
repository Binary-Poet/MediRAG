"""融合节点：向量+关键词 RRF，图谱独立汇合不参与；rerank 精排 + 置信度判定。"""
from app.agent.state import AgentState
from app.config import get_settings
from app.llm.rerank import rerank
from app.retrieval.rrf import rrf_fuse

REFLECT_MAX = 1


def fuse(state: AgentState) -> dict:
    s = get_settings()
    cfg = state.get("inference") or {}
    fused = rrf_fuse(
        [state["vector_hits"], state["keyword_hits"]], k=cfg.get("rrf_k", s.rrf_k))[:cfg.get("fuse_candidate", s.fuse_candidate)]
    docs = [f"{c['title']}：{c['text']}" for c in fused]
    reranked = rerank(state["rewritten_query"], docs, top_n=cfg.get("rerank_top_n", s.rerank_top_n))
    evidence = [{**fused[r["index"]], "score": r["score"]} for r in reranked]
    confidence = max((e["score"] for e in evidence), default=0.0)
    low_confidence = bool(evidence) and evidence[0]["score"] < cfg.get("evidence_min_score", s.evidence_min_score)

    # 图谱强证据豁免：低置信但图谱命中 → 剔除低分文献噪声（阶段 2 R8 语义）
    if low_confidence and state.get("graph_facts"):
        evidence = [e for e in evidence if e["score"] >= cfg.get("evidence_min_score", s.evidence_min_score)]
        confidence = max((e["score"] for e in evidence), default=0.0)

    trace = [
        {"step": "fuse", "candidate_n": len(fused), "method": "RRF"},
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