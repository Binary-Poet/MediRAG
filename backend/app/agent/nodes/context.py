"""context 节点：组装最终生成 Prompt（文献 + 图谱），产出宿主流式生成所需输入。"""
from pathlib import Path

from app.agent.state import AgentState

PROMPTS_DIR = Path(__file__).resolve().parents[2] / "agent" / "prompts"
ANSWER_TEMPLATE = PROMPTS_DIR / "answer_cn_tcm.txt"


def context(state: AgentState) -> dict:
    graph_block = "\n".join(
        f"{f['source']} --{f['relation']}--> {f['target']}" for f in state["graph_facts"]) or "（无）"
    evidence_block = "\n\n".join(
        f"[{i + 1}] 《{e['doc_name']}》{e.get('chapter', '')}（序号 {e.get('page_no', '')}）\n{e['title']}：{e['text']}"
        for i, e in enumerate(state["evidence"])) or "（无）"
    template = ANSWER_TEMPLATE.read_text(encoding="utf-8")
    return {"prompt": template.format(graph_facts=graph_block, evidence=evidence_block,
                                     question=state["question"])}
