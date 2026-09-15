"""LangGraph StateGraph 组装：检索编排状态机（合并方案 4.2）。"""
from langgraph.graph import END, START, StateGraph

from app.agent.nodes.context import context
from app.agent.nodes.fuse import fuse, reflect_edge
from app.agent.nodes.reflect import reflect
from app.agent.nodes.retrieve import retrieve
from app.agent.nodes.route import route
from app.agent.nodes.safety import safety
from app.agent.nodes.understand import understand
from app.agent.state import AgentState


def build_agent() -> StateGraph:
    g = StateGraph(AgentState)
    g.add_node("understand", understand)
    g.add_node("retrieve", retrieve)
    g.add_node("fuse", fuse)
    g.add_node("reflect", reflect)
    g.add_node("safety", safety)
    g.add_node("context", context)

    g.add_edge(START, "understand")
    g.add_conditional_edges("understand", route, {"retrieve": "retrieve", "safety": "safety"})
    g.add_edge("retrieve", "fuse")
    g.add_conditional_edges("fuse", reflect_edge, {"reflect": "reflect", "safety": "safety"})
    g.add_edge("reflect", "retrieve")
    g.add_edge("safety", "context")
    g.add_edge("context", END)
    return g


_graph = None


def get_agent():
    """进程级编译单例（图无状态，可安全复用）。"""
    global _graph
    if _graph is None:
        _graph = build_agent().compile()
    return _graph
