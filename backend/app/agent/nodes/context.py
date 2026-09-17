"""context 节点：组装最终生成 Prompt（文献 + 图谱），产出宿主流式生成所需输入。

compare 意图（多实体对比/鉴别）按子查询分组呈现证据：让模型在「实体A证据块 / 实体B证据块」
的对齐材料上逐项对照，而不是从混合列表里自己找配对。编号始终取证据在整体列表中的下标，
保证回答里的 [1][2] 与前端证据面板一一对应；被多个子查询命中的共同证据会在各块中重复出现
（对比场景下正是需要对照的那部分）。
"""
from pathlib import Path

from app.agent.state import AgentState

PROMPTS_DIR = Path(__file__).resolve().parents[2] / "agent" / "prompts"
ANSWER_TEMPLATE = PROMPTS_DIR / "answer_cn_tcm.txt"


def _fmt(e: dict, idx: int) -> str:
    return (f"[{idx}] 《{e['doc_name']}》{e.get('chapter', '')}（序号 {e.get('page_no', '')}）\n"
            f"{e['title']}：{e['text']}")


def _evidence_block(state: AgentState) -> str:
    ev = state["evidence"]
    if not ev:
        return "（无）"
    subs = state.get("sub_queries") or []
    # 仅多子查询的 compare 分组；其余（含单查询 compare）保持平铺，编号与既有行为不变
    if state.get("intent") != "compare" or len(subs) < 2:
        return "\n\n".join(_fmt(e, i + 1) for i, e in enumerate(ev))
    used: set[int] = set()
    blocks: list[str] = []
    for i, sq in enumerate(subs):
        idxs = [n for n, e in enumerate(ev) if i in (e.get("matched_queries") or [])]
        if not idxs:
            continue
        label = "、".join(sq.get("entities") or []) or sq.get("query", "")
        blocks.append(f"【{label}】\n" + "\n\n".join(_fmt(ev[n], n + 1) for n in idxs))
        used.update(idxs)
    rest = [n for n in range(len(ev)) if n not in used]
    if rest:
        blocks.append("【其他证据】\n" + "\n\n".join(_fmt(ev[n], n + 1) for n in rest))
    return "\n\n".join(blocks)


def context(state: AgentState) -> dict:
    graph_block = "\n".join(
        f"{f['source']} --{f['relation']}--> {f['target']}" for f in state["graph_facts"]) or "（无）"
    evidence_block = _evidence_block(state)
    template = ANSWER_TEMPLATE.read_text(encoding="utf-8")
    return {"prompt": template.format(graph_facts=graph_block, evidence=evidence_block,
                                     question=state["question"])}
