"""自反思节点：证据不足时改写检索查询、并可补充实体（合并方案 4.2 自反思，上限 1 轮）。

LLM 输出按 JSON 容忍解析（改写查询 + 实体）；拿不到 JSON 时整段文本即查询词——
保持对旧输出格式与异常输出的兼容，链路不因格式问题中断。

改写同时写回 `sub_queries`：查询分解后 retrieve/fuse 以 sub_queries 为执行单位，只更新
`rewritten_query` 不会生效（见下方注释）。
"""
import json
import re
from pathlib import Path

from app.agent.state import AgentState
from app.config import get_settings
from app.llm.chat import chat_completion

PROMPTS_DIR = Path(__file__).resolve().parents[2] / "agent" / "prompts"

# 反思轮补实体上限：真实环境实测 LLM 一次补出 9 个（含麻黄/桂枝/芍药/…/甘草）——甘草这类
# 泛用药味是图谱枢纽，一带就把酸枣仁汤等无关方剂的事实拖进上下文。上限同时挡住图谱扇出成本。
MAX_NEW_ENTITIES = 3


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
    added = [n for n in new_ents if n not in known][:MAX_NEW_ENTITIES]
    merged = base_entities + [{"name": n, "type": "", "matched": n} for n in added]
    if added:
        upd["entities"] = merged
        upd["entity_names"] = [e["name"] for e in merged]

    # 改写必须同时落进 sub_queries：retrieve 与 fuse 都优先读 sub_queries，只更新
    # rewritten_query 会被静默忽略——实测「如何养生」已被改写为「中医养生方法」，下游仍按
    # 旧查询检索+精排，置信度停在 0.267 继续拒答；改前同一改写能把置信度抬到 0.55 正常作答。
    # 仅在确有改写/补实体时动它：LLM 失败回落原文时不动，否则多子查询会被追加一条重复查询。
    if new_query != state["rewritten_query"] or added:
        names = [e["name"] for e in merged]
        subs = state.get("sub_queries") or []
        if len(subs) <= 1:
            # 单查询（含未拆分的兜底路径）→ 整体替换，与拆分前「改写即生效」语义一致
            upd["sub_queries"] = [{"query": new_query, "entities": names}]
        else:
            # 多子查询（比较/复合）→ 保留按实体的扇出，另把整体改写追加为一条补充查询：替换会
            # 抹掉本特性赖以存在的实体拆分；fuse 取各子查询精排 max 分，追加只增不损。
            upd["sub_queries"] = [*subs, {"query": new_query, "entities": []}]
    return upd


def _history_block(history: list) -> str:
    if not history:
        return "（无）"
    return "\n".join(f"【{'用户' if m['role'] == 'user' else '助手'}】{m['content']}" for m in history[-8:])
