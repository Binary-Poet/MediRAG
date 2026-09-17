"""问句理解节点：一次 LLM 调用输出 改写查询/子查询/实体/意图（结构化 JSON），失败降级到词典识别。"""
import json
import re
from pathlib import Path

from app.agent.state import AgentState
from app.graph.entity_recognizer import recognize_entities
from app.graph.neo4j_client import get_graph
from app.llm.chat import chat_completion

PROMPTS_DIR = Path(__file__).resolve().parents[2] / "agent" / "prompts"

VALID_INTENTS = {"relation", "concept", "complex", "compare", "chitchat"}

# 意图映射（LLM 输出非法意图时）：问题含比较词 → compare，否则 complex
COMPARE_WORDS = ("区别", "对比", "比较", "差异", "不同")
MAX_SUB_QUERIES = 3


def _parse_sub_queries(raw) -> list | None:
    """子查询列表结构校验与归一；非法返回 None（由调用方回落单查询包装）。"""
    if not isinstance(raw, list) or not raw:
        return None
    subs = []
    for item in raw[:MAX_SUB_QUERIES]:
        if not isinstance(item, dict) or not str(item.get("query") or "").strip():
            continue
        ents = item.get("entities")
        subs.append({"query": str(item["query"]).strip(),
                     "entities": [str(e) for e in ents if isinstance(e, str) and e]
                     if isinstance(ents, list) else []})
    return subs or None


def _parse_understand(raw: str) -> dict | None:
    """从 LLM 输出容忍提取 JSON；结构非法返回 None。

    意图不在 VALID_INTENTS 时**不丢弃整个输出**（rewritten_query/entities 可能都是对的），
    仅把 intent 置 None，由 understand 按问题文本映射——修「comparison 等近义词整包丢弃」。
    """
    text = raw.strip()
    text = re.sub(r"^```(?:json)?|```$", "", text, flags=re.MULTILINE).strip()
    try:
        d = json.loads(text)
    except (json.JSONDecodeError, ValueError):
        m = re.search(r"\{.*\}", text, flags=re.DOTALL)
        if not m:
            return None
        try:
            d = json.loads(m.group(0))
        except (json.JSONDecodeError, ValueError):
            return None
    if not isinstance(d, dict):
        return None
    ents = d.get("entities")
    if not isinstance(ents, list):
        return None
    intent = d.get("intent") if d.get("intent") in VALID_INTENTS else None
    return {"rewritten_query": str(d.get("rewritten_query") or ""),
            "sub_queries": _parse_sub_queries(d.get("sub_queries")),
            "entities": [e for e in ents if isinstance(e, dict) and e.get("name")],
            "intent": intent}


def _map_intent(question: str) -> str:
    """LLM 意图非法时的确定性映射：比较词 → compare，否则 complex。"""
    return "compare" if any(w in question for w in COMPARE_WORDS) else "complex"


def understand(state: AgentState) -> dict:
    """理解节点：结构化 LLM；失败则用词典识别兜底（保证链路不因格式问题中断）。"""
    history_block = _history_block(state.get("chat_history") or [])
    prompt = (PROMPTS_DIR / "query_understand.txt").read_text(encoding="utf-8").format(
        history=history_block, question=state["question"])

    try:
        cfg = state.get("inference") or {}
        query_temp = float(cfg.get("query_temp", 0.1))
        # vendor/model 仅在有值时透传（兼容既有三参 mock；无值即回落 settings）
        llm_kw = {k: v for k, v in (("vendor", cfg.get("vendor")),
                                    ("model", cfg.get("model"))) if v}
        raw = chat_completion(system="你是中医药问句理解器，只输出 JSON。", user=prompt,
                              temperature=query_temp, **llm_kw)
    except RuntimeError:
        raw = ""
    parsed = _parse_understand(raw) if raw else None

    if parsed is None:
        vocab = get_graph().all_entities()
        ents = recognize_entities(state["question"], vocab)
        parsed = {
            "rewritten_query": state["question"],
            "sub_queries": None,
            "entities": ents,
            # 词典兜底三档：有实体 → complex；无实体但问题在健康范围 → concept 放行检索
            # （「如何养生」不再误归 chitchat 拒答；真闲聊由置信度兜底拦下）
            "intent": "complex" if ents else "concept",
        }
    if parsed["intent"] is None:
        parsed["intent"] = _map_intent(state["question"])

    entities = [{"name": e["name"], "type": e.get("type", ""), "matched": e.get("matched", e["name"])}
                for e in parsed["entities"]]
    entity_names = [e["name"] for e in entities]
    # 子查询缺失（单实体问题/兜底路径）→ 包装为单查询，下游扇出逻辑零特判
    sub_queries = parsed["sub_queries"] or [
        {"query": parsed["rewritten_query"] or state["question"], "entities": entity_names}]
    trace_evt = {
        "step": "understand",
        "raw": state["question"],
        "rewritten": parsed["rewritten_query"] or state["question"],
        "entities": entity_names,
        "intent": parsed["intent"],
        "sub_query_n": len(sub_queries),
    }
    return {
        "rewritten_query": parsed["rewritten_query"] or state["question"],
        "sub_queries": sub_queries,
        "entities": entities,
        "entity_names": entity_names,
        "intent": parsed["intent"],
        "trace": [trace_evt],
    }


def _history_block(history: list) -> str:
    if not history:
        return "（无）"
    lines = []
    for m in history[-8:]:
        who = "用户" if m["role"] == "user" else "助手"
        lines.append(f"【{who}】{m['content']}")
    return "\n".join(lines)
