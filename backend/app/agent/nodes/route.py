"""意图→工具路由矩阵（合并方案 4.2 逐字）与条件边。"""

PLAN_MATRIX = {
    "relation": ["vector_search", "graph_search"],
    "concept": ["vector_search", "keyword_search"],
    "complex": ["vector_search", "keyword_search", "graph_search"],
    "chitchat": [],
}


def route(state) -> str:
    """understand 之后：chitchat 直接进 safety，其余进检索。"""
    return "safety" if state["intent"] == "chitchat" else "retrieve"