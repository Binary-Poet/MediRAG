"""context 节点：组装最终生成 Prompt（文献 + 图谱），产出宿主流式生成所需输入。

compare 意图（多实体对比/鉴别）按子查询分组呈现证据：让模型在「实体A证据块 / 实体B证据块」
的对齐材料上逐项对照，而不是从混合列表里自己找配对。编号始终取证据在整体列表中的下标，
保证回答里的 [1][2] 与前端证据面板一一对应；被多个子查询命中的共同证据会在各块中重复出现
（对比场景下正是需要对照的那部分）。

某个实体确实没有过阈证据时，显式写出「未检索到依据」，而不是让该块凭空消失——缺口写明
比让模型从「块不存在」去推断更可靠。
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
    # 覆盖度以 fuse 的按子查询精排分为准：没有过阈证据的实体显式写「未检索到依据」。
    # 不能靠 matched_queries 判断——演示库仅 13 条切片，任何子查询都命中全库，
    # matched 恒为全部子查询；也不能靠「这个块没出现」让模型自己推断缺口。
    covered = state.get("sub_query_covered") or []
    used: set[int] = set()
    blocks: list[str] = []
    for i, sq in enumerate(subs):
        idxs = [n for n, e in enumerate(ev) if i in (e.get("matched_queries") or [])]
        label = "、".join(sq.get("entities") or []) or sq.get("query", "")
        has_evidence = covered[i] if i < len(covered) else bool(idxs)
        if not has_evidence:
            blocks.append(f"【{label}】\n（知识库中未检索到与「{label}」相关的可靠依据）")
            continue
        if not idxs:
            continue
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
