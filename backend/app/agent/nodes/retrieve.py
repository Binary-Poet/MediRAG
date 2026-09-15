"""检索节点：按 plan（意图路由）调用被选 Tool。图谱无实体则跳过。"""
from app.agent import tools as tool_module
from app.agent.state import AgentState
from app.agent.nodes.route import PLAN_MATRIX
from app.config import get_settings

TOOLS = {
    "vector_search": tool_module.vector_search,
    "keyword_search": tool_module.keyword_search,
    "graph_search": tool_module.graph_search,
}


def retrieve(state: AgentState) -> dict:
    s = get_settings()
    plan = PLAN_MATRIX.get(state["intent"], [])
    vector_hits = TOOLS["vector_search"].invoke({"query": state["rewritten_query"], "top_k": s.semantic_k}) \
        if "vector_search" in plan else []
    keyword_hits = TOOLS["keyword_search"].invoke({"query": state["rewritten_query"], "top_k": s.keyword_k}) \
        if "keyword_search" in plan else []
    graph_facts = []
    if "graph_search" in plan and state.get("entity_names"):
        for name in state["entity_names"]:
            out = TOOLS["graph_search"].invoke({"entity": name, "hop": 1})
            graph_facts.extend(out.get("facts", []))

    trace_evt = {
        "step": "retrieve",
        "vector_n": len(vector_hits),
        "keyword_n": len(keyword_hits),
        "graph_n": len(graph_facts),
        "entity_n": len(state.get("entity_names", [])),
        "entities": state.get("entity_names", []),
    }
    return {
        "plan": plan,
        "vector_hits": vector_hits,
        "keyword_hits": keyword_hits,
        "graph_facts": graph_facts,
        "trace": [trace_evt],
    }