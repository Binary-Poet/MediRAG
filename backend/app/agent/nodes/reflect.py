"""自反思节点：证据不足时改写检索查询、并可补充实体（合并方案 4.2 自反思，上限 1 轮）。

LLM 输出按 JSON 容忍解析（改写查询 + 实体）；拿不到 JSON 时整段文本即查询词——
保持对旧输出格式与异常输出的兼容，链路不因格式问题中断。
"""
import json
import re
from pathlib import Path

from app.agent.state import AgentState
from app.config import get_settings
from app.llm.chat import chat_completion

PROMPTS_DIR = Path(__file__).resolve().parents[2] / "agent" / "prompts"


def _parse_reflect(raw: str) -> tuple[str, list[str]]:
    """容忍解析：JSON → (改写查询, 实体名列表)；否则 (整段文本, [])。"""
    text = raw.strip()
    m = re.search(r"\{.*\}", text, flags=re.DOTALL)
    if m:
        try:
            d = json.loads(m.group(0))
        except (json.JSONDecodeError, ValueError):
            d = None
        if isinstance(d, dict):
            q = str(d.get("rewritten_query") or "").strip()
            if q:
                ents = d.get("entities")
                names = []
                if isinstance(ents, list):
                    for e in ents:
                        if isinstance(e, dict) and e.get("name"):
                            names.append(str(e["name"]))
                        elif isinstance(e, str) and e:
                            names.append(e)
                return q, names
    return text, []


def reflect(state: AgentState) -> dict:
    s = get_settings()
    reason = "最终证据为空" if not state["evidence"] else \
        f"Top 相关度 {state['confidence']:.3f} 低于阈值 {s.evidence_min_score}"
    history_block = _history_block(state.get("chat_history") or [])
    prompt = (PROMPTS_DIR / "query_rewrite_reflect.txt").read_text(encoding="utf-8").format(
        reason=reason, question=state["question"],
        rewritten_query=state["rewritten_query"], history=history_block)
    try:
        raw = chat_completion(system="你是中医药检索改写器。", user=prompt, temperature=0.2).strip()
    except RuntimeError:
        raw = ""
    new_query, new_ents = _parse_reflect(raw) if raw else ("", [])
    if not new_query:
        new_query = state["rewritten_query"]

    trace_evt = {"step": "reflect", "round": state["reflect_count"] + 1, "reason": reason,
                 "rewritten": new_query}
    upd: dict = {"rewritten_query": new_query,
                 "reflect_count": state["reflect_count"] + 1,
                 "trace": [trace_evt]}
    # 反思补实体：与既有实体并集（保序去重），否则第二轮图谱路仍用旧实体等于白跑
    base_entities = list(state.get("entities") or []) or \
        [{"name": n, "type": "", "matched": n} for n in (state.get("entity_names") or [])]
    known = {e["name"] for e in base_entities}
    added = [n for n in new_ents if n not in known]
    if added:
        merged = base_entities + [{"name": n, "type": "", "matched": n} for n in added]
        upd["entities"] = merged
        upd["entity_names"] = [e["name"] for e in merged]
    return upd


def _history_block(history: list) -> str:
    if not history:
        return "（无）"
    return "\n".join(f"【{'用户' if m['role'] == 'user' else '助手'}】{m['content']}" for m in history[-8:])
