"""问句理解节点：一次 LLM 调用输出 改写查询/实体/意图（结构化 JSON），失败降级到词典识别。"""
import json
import re
from pathlib import Path

from app.agent.state import AgentState
from app.graph.entity_recognizer import recognize_entities
from app.graph.neo4j_client import get_graph
from app.llm.chat import chat_completion

PROMPTS_DIR = Path(__file__).resolve().parents[2] / "agent" / "prompts"

VALID_INTENTS = {"relation", "concept", "complex", "chitchat"}


def _parse_understand(raw: str) -> dict | None:
    """从 LLM 输出容忍提取 JSON；非法/字段缺失返回 None。"""
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
    if not isinstance(d, dict) or d.get("intent") not in VALID_INTENTS:
        return None
    ents = d.get("entities")
    if not isinstance(ents, list):
        return None
    return {"rewritten_query": str(d.get("rewritten_query") or ""),
            "entities": [e for e in ents if isinstance(e, dict) and e.get("name")],
            "intent": d["intent"]}


def understand(state: AgentState) -> dict:
    """理解节点：结构化 LLM；失败则用词典识别兜底（保证链路不因格式问题中断）。"""
    history_block = _history_block(state.get("chat_history") or [])
    prompt = (PROMPTS_DIR / "query_understand.txt").read_text(encoding="utf-8").format(
        history=history_block, question=state["question"])

    try:
        raw = chat_completion(system="你是中医药问句理解器，只输出 JSON。", user=prompt, temperature=0.1)
    except RuntimeError:
        raw = ""
    parsed = _parse_understand(raw) if raw else None

    if parsed is None:
        vocab = get_graph().all_entities()
        ents = recognize_entities(state["question"], vocab)
        parsed = {
            "rewritten_query": state["question"],
            "entities": ents,
            "intent": "complex" if ents else "chitchat",
        }

    entities = [{"name": e["name"], "type": e.get("type", ""), "matched": e.get("matched", e["name"])}
                for e in parsed["entities"]]
    entity_names = [e["name"] for e in entities]
    trace_evt = {
        "step": "understand",
        "raw": state["question"],
        "rewritten": parsed["rewritten_query"] or state["question"],
        "entities": entity_names,
        "intent": parsed["intent"],
    }
    return {
        "rewritten_query": parsed["rewritten_query"] or state["question"],
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