"""检索节点：按 plan（意图路由）调用被选 Tool，向量/关键词按子查询扇出。图谱无实体则跳过。

三路检索相互独立，用线程池并行执行以缩短「发送→首个 token」等待（向量/关键词为
SiliconFlow API + 本地索引，图谱为 Neo4j，读操作均线程安全）。任一路失败只降级
该路为空结果并记录日志，不拖垮整轮回答。

查询分解（2026-09 方案）：understand 产出 sub_queries（多实体比较时每实体一查），
向量/关键词的执行单位从「路」改为「子查询 × 路」，每条命中打 sub_query 下标供
fuse 按子查询对齐精排；图谱实体取 全局实体 ∪ 各子查询实体 的保序并集。
"""
import concurrent.futures
import logging

from app.agent import tools as tool_module
from app.agent.state import AgentState
from app.agent.nodes.route import PLAN_MATRIX
from app.config import get_settings

logger = logging.getLogger(__name__)

TOOLS = {
    "vector_search": tool_module.vector_search,
    "keyword_search": tool_module.keyword_search,
    "graph_search": tool_module.graph_search,
}


def _guard(fn, default):
    """单路检索兜底：异常记录日志并降级为空结果。"""
    try:
        return fn()
    except Exception:
        logger.exception("检索路执行失败，降级为空结果")
        return default


def _tag(hits, sub_idx: int):
    """给列表内的 dict 命中打子查询下标（工具返回非列表时原样透传，兼容测试 fake）。"""
    if isinstance(hits, list):
        for h in hits:
            if isinstance(h, dict):
                h["sub_query"] = sub_idx
    return hits


def retrieve(state: AgentState) -> dict:
    s = get_settings()
    cfg = state.get("inference") or {}
    plan = list(PLAN_MATRIX.get(state["intent"], []))
    query = state["rewritten_query"]
    entity_names = state.get("entity_names") or []
    # 子查询缺失（词典兜底/直接构造 state）→ 包装为单查询，下游零特判
    sub_queries = state.get("sub_queries") or [{"query": query, "entities": entity_names}]
    # concept 类比较问题若抽到明确实体（如「四君子汤与归脾汤的区别」），补开图谱路
    # 让组成/功效等事实参与比较——否则图谱证据被静默丢弃（PLAN_MATRIX 需复制再改）。
    if state["intent"] == "concept" and entity_names and "graph_search" not in plan:
        plan.append("graph_search")

    # 图谱实体：全局实体 ∪ 各子查询实体（保序去重）
    graph_entities = list(dict.fromkeys(
        entity_names + [e for sq in sub_queries for e in sq.get("entities", [])]))

    def _vector(sub_idx, q):
        return _tag(TOOLS["vector_search"].invoke(
            {"query": q, "top_k": cfg.get("semantic_k", s.semantic_k)}), sub_idx)

    def _keyword(sub_idx, q):
        return _tag(TOOLS["keyword_search"].invoke(
            {"query": q, "top_k": cfg.get("keyword_k", s.keyword_k)}), sub_idx)

    def _graph():
        facts = []
        for name in graph_entities:
            out = TOOLS["graph_search"].invoke({"entity": name, "hop": s.graph_hop})
            for f in out.get("facts", []):
                if isinstance(f, dict):
                    f["entity"] = name
                facts.append(f)
        return facts

    jobs: dict[tuple, concurrent.futures.Future] = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as ex:
        for i, sq in enumerate(sub_queries):
            # 默认参数绑定循环变量：lambda 直接闭包会在任务真正执行时读到最后一轮的值
            if "vector_search" in plan:
                jobs[("vector", i)] = ex.submit(
                    _guard, lambda i=i, q=sq["query"]: _vector(i, q), [])
            if "keyword_search" in plan:
                jobs[("keyword", i)] = ex.submit(
                    _guard, lambda i=i, q=sq["query"]: _keyword(i, q), [])
        if "graph_search" in plan and graph_entities:
            jobs[("graph", 0)] = ex.submit(_guard, _graph, [])
        # 按子查询下标顺序汇聚，保证结果顺序与子查询一致（线程完成顺序无关）
        vector_hits = [h for i in range(len(sub_queries)) if ("vector", i) in jobs
                       for h in jobs[("vector", i)].result()]
        keyword_hits = [h for i in range(len(sub_queries)) if ("keyword", i) in jobs
                        for h in jobs[("keyword", i)].result()]
        graph_facts = jobs[("graph", 0)].result() if ("graph", 0) in jobs else []

    trace_evt = {
        "step": "retrieve",
        "vector_n": len(vector_hits),
        "keyword_n": len(keyword_hits),
        "graph_n": len(graph_facts),
        "entity_n": len(graph_entities),
        "entities": graph_entities,
        "sub_query_n": len(sub_queries),
    }
    return {
        "plan": plan,
        "vector_hits": vector_hits,
        "keyword_hits": keyword_hits,
        "graph_facts": graph_facts,
        "trace": [trace_evt],
    }
