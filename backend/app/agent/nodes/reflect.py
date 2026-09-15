"""自反思节点：证据不足时改写检索查询（合并方案 4.2 自反思，上限 1 轮）。"""
from pathlib import Path

from app.agent.state import AgentState
from app.config import get_settings
from app.llm.chat import chat_completion

PROMPTS_DIR = Path(__file__).resolve().parents[2] / "agent" / "prompts"


def reflect(state: AgentState) -> dict:
    s = get_settings()
    reason = "最终证据为空" if not state["evidence"] else \
        f"Top 相关度 {state['confidence']:.3f} 低于阈值 {s.evidence_min_score}"
    history_block = _history_block(state.get("chat_history") or [])
    prompt = (PROMPTS_DIR / "query_rewrite_reflect.txt").read_text(encoding="utf-8").format(
        reason=reason, question=state["question"],
        rewritten_query=state["rewritten_query"], history=history_block)
    try:
        new_query = chat_completion(system="你是中医药检索改写器。", user=prompt, temperature=0.2).strip()
    except RuntimeError:
        new_query = state["rewritten_query"]
    if not new_query:
        new_query = state["rewritten_query"]

    trace_evt = {"step": "reflect", "round": state["reflect_count"] + 1, "reason": reason,
                 "rewritten": new_query}
    return {"rewritten_query": new_query,
            "reflect_count": state["reflect_count"] + 1,
            "trace": [trace_evt]}


def _history_block(history: list) -> str:
    if not history:
        return "（无）"
    return "\n".join(f"【{'用户' if m['role'] == 'user' else '助手'}】{m['content']}" for m in history[-8:])
