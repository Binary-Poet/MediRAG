"""LLM 实体关系抽取 → Neo4j 候选（方案 6.5 审核闭环）。

抽取的三元组一律 status='候选'；问答链路只查 '已发布'，故候选不会污染回答。
"""
import json
import re
from pathlib import Path

from app.llm.chat import chat_completion

PROMPT_PATH = Path(__file__).resolve().parents[1] / "agent" / "prompts" / "entity_extract.txt"

VALID_RELATIONS = {"组成", "主治", "功效", "禁忌", "表现"}
VALID_TYPES = {"方剂", "中药", "证候", "症状", "功效", "禁忌"}


def extract_triples(text: str) -> list[dict]:
    """调用 LLM 抽取三元组；任何失败（网络/格式/非法值）返回 []。"""
    try:
        prompt = PROMPT_PATH.read_text(encoding="utf-8").format(text=text[:2000])
        raw = chat_completion(system="你是中医药知识图谱抽取器。", user=prompt, temperature=0.0)
        match = re.search(r"\[.*?\]", raw, re.DOTALL)
    except Exception:
        return []

    if not match:
        return []
    try:
        data = json.loads(match.group(0))
    except json.JSONDecodeError:
        return []
    if not isinstance(data, list):
        return []

    triples: list[dict] = []
    for item in data:
        if not isinstance(item, dict):
            continue
        if not all(k in item for k in ("source", "relation", "target", "source_type", "target_type")):
            continue
        if item["relation"] not in VALID_RELATIONS:
            continue
        if item["source_type"] not in VALID_TYPES or item["target_type"] not in VALID_TYPES:
            continue
        triples.append({k: str(item[k]).strip() for k in
                        ("source", "relation", "target", "source_type", "target_type")})
    return triples


def save_candidates(triples: list[dict], source_doc: str, graph=None) -> int:
    """写入候选节点/边（MERGE 幂等）。返回写入边数。"""
    if not triples:
        return 0
    if graph is None:
        from app.graph.neo4j_client import get_graph

        graph = get_graph()

    edges = 0
    for t in triples:
        for name, label in ((t["source"], t["source_type"]), (t["target"], t["target_type"])):
            graph.execute_write(
                f"MERGE (n:`{label.replace('`', '``')}` {{name: $name}}) "
                "ON CREATE SET n.status = '候选', n.source = $source_doc "
                "ON MATCH SET n.status = CASE WHEN n.status = '已发布' THEN '已发布' ELSE '候选' END",
                name=name, source_doc=source_doc,
            )
        graph.execute_write(
            f"MATCH (a {{name: $s}}), (b {{name: $t}}) "
            f"MERGE (a)-[r:`{t['relation'].replace('`', '``')}`]->(b) "
            "ON CREATE SET r.status = '候选', r.source_doc = $source_doc "
            "ON MATCH SET r.status = CASE WHEN r.status = '已发布' THEN '已发布' ELSE '候选' END",
            s=t["source"], t=t["target"], source_doc=source_doc,
        )
        edges += 1
    return edges