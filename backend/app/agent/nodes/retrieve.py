"""检索节点：按 plan（意图路由）调用被选 Tool。图谱无实体则跳过。

三路检索相互独立，用线程池并行执行以缩短「发送→首个 token」等待（向量/关键词为
SiliconFlow API + 本地索引，图谱为 Neo4j，读操作均线程安全）。任一路失败只降级
该路为空结果并记录日志，不拖垮整轮回答。
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


def retrieve(state: AgentState) -> dict:
    s = get_settings()
    cfg = state.get("inference") or {}
    plan = PLAN_MATRIX.get(state["intent"], [])
    query = state["rewritten_query"]
    entity_names = state.get("entity_names") or []

    def _vector():
        return TOOLS["vector_search"].invoke({"query": query,
                                              "top_k": cfg.get("semantic_k", s.semantic_k)})

    def _keyword():
        return TOOLS["keyword_search"].invoke({"query": query,
                                               "top_k": cfg.get("keyword_k", s.keyword_k)})

    def _graph():
        facts = []
        for name in entity_names:
            out = TOOLS["graph_search"].invoke({"entity": name, "hop": 1})
            facts.extend(out.get("facts", []))
        return facts

    vector_hits, keyword_hits, graph_facts = [], [], []
    jobs: dict[str, concurrent.futures.Future] = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as ex:
        if "vector_search" in plan:
            jobs["vector"] = ex.submit(_guard, _vector, [])
        if "keyword_search" in plan:
            jobs["keyword"] = ex.submit(_guard, _keyword, [])
        if "graph_search" in plan and entity_names:
            jobs["graph"] = ex.submit(_guard, _graph, [])
        if "vector" in jobs:
            vector_hits = jobs["vector"].result()
        if "keyword" in jobs:
            keyword_hits = jobs["keyword"].result()
        if "graph" in jobs:
            graph_facts = jobs["graph"].result()

    trace_evt = {
        "step": "retrieve",
        "vector_n": len(vector_hits),
        "keyword_n": len(keyword_hits),
        "graph_n": len(graph_facts),
        "entity_n": len(entity_names),
        "entities": entity_names,
    }
    return {
        "plan": plan,
        "vector_hits": vector_hits,
        "keyword_hits": keyword_hits,
        "graph_facts": graph_facts,
        "trace": [trace_evt],
    }
