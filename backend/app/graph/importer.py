"""图谱 seed 导入：data/graph/seed_tcm_graph.json → Neo4j（幂等 MERGE）。

seed 节点一律 status='已发布'（meta.status_note 约定）；LLM 抽取的候选
三元组属阶段 4 审核闭环（status='候选'），问答只查已发布。
CLI（backend/ 下）：python -m app.graph.importer
"""
import json
from pathlib import Path

from app.graph.neo4j_client import get_graph

SEED_PATH = Path(__file__).resolve().parents[3] / "data" / "graph" / "seed_tcm_graph.json"


def load_seed(path: Path = SEED_PATH) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def import_seed(graph=None, path: Path = SEED_PATH) -> dict:
    """幂等导入：节点 2 条 MERGE（type 作 label 并冗余为属性），边按 id->name 映射 MERGE。"""
    graph = graph or get_graph()
    seed = load_seed(path)
    nodes, edges = seed["nodes"], seed["edges"]

    for n in nodes:
        graph.execute_write(
            "MERGE (n:`" + n["type"].replace("`", "``") + "` {name: $name}) "
            "SET n.alias = $alias, n.desc = $desc, n.source = $source, "
            "n.type = $type, n.status = '已发布'",
            name=n["name"], alias=n["alias"], desc=n["desc"],
            source=n["source"], type=n["type"],
        )

    id_to_name = {n["id"]: n["name"] for n in nodes}
    for e in edges:
        graph.execute_write(
            "MATCH (a {name: $s}), (b {name: $t}) "
            "MERGE (a)-[r:`" + e["relation"].replace("`", "``") + "`]->(b) "
            "SET r.note = $note, r.status = '已发布'",
            s=id_to_name[e["source"]], t=id_to_name[e["target"]], note=e.get("note", ""),
        )

    return {"nodes": len(nodes), "edges": len(edges)}


if __name__ == "__main__":
    stats = import_seed()
    print(f"[graph] 导入 {stats['nodes']} 节点 / {stats['edges']} 关系")