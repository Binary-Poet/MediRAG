"""AgentState：LangGraph 状态机共享状态（合并方案 4.2，字段与 SSE trace 对应）。"""
from operator import add
from typing import Annotated, TypedDict


class AgentState(TypedDict):
    question: str                     # 用户原始问题
    session_id: str                   # 会话标识（多轮记忆）
    chat_history: list                # [{"role": "user"|"assistant", "content": str}, ...]
    rewritten_query: str              # 理解/反思后的检索查询
    sub_queries: list                 # 子查询 [{"query", "entities"}]（查询分解；单查询时仅一项）
    entities: list                    # [{"name", "type", "matched"}, ...]
    entity_names: list                # 实体名的扁平列表（供图谱检索）
    intent: str                       # relation / concept / complex / chitchat
    plan: list                        # 本次路由的工具名列表（vector_search / keyword_search / graph_search）
    vector_hits: list                 # 向量召回
    keyword_hits: list                # 关键词召回
    graph_facts: list                 # 图谱事实（独立汇合，不参与 RRF）
    fused: list                       # RRF 融合截断后候选
    evidence: list                    # rerank 后最终证据
    confidence: float                 # max(evidence.score)
    low_confidence: bool              # 阈值判定
    reflect_count: int                # 自反思轮次（硬上限 1）
    safety_flag: str | None           # emergency / low_confidence / ok
    safety_message: str               # 急救提示或拒答话术（safety 节点产出）
    prompt: str                       # 组装好的最终生成 Prompt（供宿主流式生成）
    answer: str                       # 兜底固定话术（非流式）或最终完整回答（流式完成后回填供记忆）
    trace: Annotated[list, add]       # SSE step 事件流：节点只返回本次新增事件，langgraph 自动累计
    inference: dict                   # 推理配置（chat.py 注入；节点侧 state.get("inference") 回落 settings）