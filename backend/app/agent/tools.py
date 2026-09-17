"""三个检索 Tool（Function Calling 的直接证据，合并方案 6.2）。

用 langchain_core.tools.tool 封装，与 LangGraph 状态机的"条件路由"配合，
由 PLAN_MATRIX 决定调用子集；不用自由 ReAct 循环（医疗可控性）。
"""
from langchain_core.tools import tool

from app.graph.neo4j_client import get_graph
from app.llm.embedding import embed_texts
from app.retrieval.keyword import get_keyword_index
from app.retrieval.vector_store import get_store


@tool
def vector_search(query: str, top_k: int = 20) -> list:
    """语义向量检索：用于概念解释、机理对比、症状与方剂关联等需要语义理解的问题。
    返回切片文本、文档名、章节、页码、相似度分数。"""
    embedding = embed_texts([query])[0]
    return get_store().search(embedding, top_k)


@tool
def keyword_search(query: str, top_k: int = 20) -> list:
    """关键词检索(BM25)：用于精确匹配中医药专有名词、方剂名、药材名、术语缩写。
    返回切片文本与 BM25 分数。"""
    return get_keyword_index().search(query, top_k=top_k)


@tool
def graph_search(entity: str, hop: int = 1) -> dict:
    """中医药知识图谱检索：查询某实体(药材/方剂/证候/症状/功效/禁忌)的 1~2 跳关系，
    返回节点、关系、路径，用于组成、配伍、禁忌等事实型问题。返回 {"entity", "facts"}。"""
    return {"entity": entity, "facts": get_graph().neighbors([entity], hop=hop)}


@tool
def graph_path_search(template: str, names: list[str]) -> dict:
    """定向多跳路径检索：按语义模板走链路，比无向邻居更精准。

    模板：symptom_to_formula（症状→证候→方剂，按多症状共现计数排序）、
    syndrome_to_formula（多证候→方剂，合病推理）、
    formula_mechanism（方剂→组成→中药→功效，配伍机制链）。
    返回 {"template", "facts"}，事实带 path_template 与（共现类模板的）hit。
    """
    return {"template": template, "facts": get_graph().directed_paths(template, names)}


TOOL_NAMES = {"vector_search", "keyword_search", "graph_search", "graph_path_search"}