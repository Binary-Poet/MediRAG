"""图谱 API：搜索/邻居/详情 + 候选审核（规格 P0-5，方案 6.5/第八节）。"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.api.auth import current_user
from app.graph.importer import import_seed
from app.graph.neo4j_client import RELATIONS_LITERAL, get_graph
from app.models.user import User

router = APIRouter()

# 2-hop 语义关系白名单与问答路（GraphClient.neighbors）同源，统一在 neo4j_client 构造。
_RELATIONS_LITERAL = RELATIONS_LITERAL


def _read(cypher: str, **params) -> list[dict]:
    """只读查询（GraphClient.run_read；测试注入 fake 客户端）。"""
    return get_graph().run_read(cypher, **params)


@router.get("/graph/search")
def search_entities(entity: str = "", type: str = "") -> dict:
    where, params = ["n.status IN ['已发布','候选']"], {}
    if entity:
        where.append("n.name CONTAINS $entity")
        params["entity"] = entity
    if type:
        where.append("n.type = $type")
        params["type"] = type
    rows = _read(
        f"MATCH (n) WHERE {' AND '.join(where)} "
        "RETURN n.name AS name, n.type AS type, n.alias AS alias, n.status AS status "
        "ORDER BY n.name LIMIT 200",
        **params,
    )
    return {"items": rows}


@router.get("/graph/neighbors")
def neighbors(name: str, hop: int = 2) -> dict:
    hop = min(max(int(hop), 1), 2)
    # 阶段 5：2-hop 扩展收紧——中间边只允许语义关系白名单（由 VALID_RELATIONS 构造，无注入风险）
    rows = _read(
        f"MATCH p = (a)-[*1..{hop}]-(b) WHERE a.name = $name "
        f"AND ALL(r IN relationships(p) WHERE type(r) IN [{_RELATIONS_LITERAL}]) "
        "UNWIND relationships(p) AS r "
        "RETURN DISTINCT startNode(r).name AS source, type(r) AS relation, endNode(r).name AS target, "
        "startNode(r).type AS source_type, endNode(r).type AS target_type, "
        "startNode(r).status AS source_status, endNode(r).status AS target_status, "
        "r.status AS status",
        name=name,
    )
    # 阶段 5：候选边不进入浏览结果（API 层兜底，不依赖 Cypher 细节，测试可注入 fake 验证）
    rows = [r for r in rows if r.get("status") == "已发布"]
    nodes: dict[str, dict] = {}
    links: list[dict] = []
    seen: set[tuple] = set()
    for r in rows:
        # links 按 (source, relation, target) 去重
        key = (r["source"], r["relation"], r["target"])
        if key in seen:
            continue
        seen.add(key)
        for n, t, s in ((r["source"], r["source_type"], r["source_status"]),
                        (r["target"], r["target_type"], r["target_status"])):
            nodes.setdefault(n, {"id": n, "name": n, "category": t, "status": s})
        # links 的 status 取「边状态」（r.status），与节点状态区分
        links.append({"source": r["source"], "target": r["target"],
                      "relation": r["relation"], "status": r["status"]})
    return {"nodes": list(nodes.values()), "links": links}


@router.post("/graph/import")
def reimport(_: User = Depends(current_user)) -> dict:
    """重新导入基础数据（幂等 MERGE，不破坏已发布/候选状态）。"""
    return {"imported": import_seed()}


@router.get("/graph/entities/{name}")
def entity_detail(name: str) -> dict:
    rows = _read(
        "MATCH (n {name: $name}) RETURN n.name AS name, n.type AS type, n.alias AS alias, "
        "n.desc AS desc, n.source AS source, n.status AS status LIMIT 1",
        name=name,
    )
    if not rows:
        raise HTTPException(status_code=404, detail="实体不存在")
    return rows[0]


@router.get("/graph/candidates")
def list_candidates() -> dict:
    edges = _read(
        "MATCH (a)-[r]->(b) WHERE r.status = '候选' "
        "RETURN a.name AS source, type(r) AS relation, b.name AS target, "
        "a.type AS source_type, b.type AS target_type, r.source_doc AS source_doc LIMIT 500"
    )
    node_rows = _read(
        "MATCH (n) WHERE n.status = '候选' "
        "RETURN n.name AS name, n.type AS type, n.source AS source_doc LIMIT 500"
    )
    return {"nodes": node_rows, "edges": edges}


class ApproveBody(BaseModel):
    kind: str                     # "node" | "edge"
    name: str = ""
    source: str = ""
    relation: str = ""
    target: str = ""


@router.post("/graph/candidates/approve")
def approve(body: ApproveBody) -> dict:
    graph = get_graph()
    if body.kind == "node":
        if not body.name:
            raise HTTPException(status_code=422, detail="node 需提供 name")
        graph.execute_write("MATCH (n {name: $name}) SET n.status = '已发布'", name=body.name)
        return {"approved": "node", "name": body.name}
    if body.kind == "edge":
        if not (body.source and body.relation and body.target):
            raise HTTPException(status_code=422, detail="edge 需提供 source/relation/target")
        graph.execute_write(
            "MATCH (a {name: $s})-[r]->(b {name: $t}) WHERE type(r) = $rel "
            "SET r.status = '已发布'",
            s=body.source, t=body.target, rel=body.relation,
        )
        return {"approved": "edge", "source": body.source, "relation": body.relation, "target": body.target}
    raise HTTPException(status_code=422, detail="kind 取值为 node|edge")


@router.post("/graph/candidates/reject")
def reject(body: ApproveBody) -> dict:
    graph = get_graph()
    if body.kind == "node":
        if not body.name:
            raise HTTPException(status_code=422, detail="node 需提供 name")
        refs = _read(
            "MATCH (n {name: $name})-[r]-() WHERE r.status = '已发布' RETURN count(r) AS n",
            name=body.name,
        )
        if refs and refs[0]["n"] > 0:
            raise HTTPException(status_code=409, detail="该实体被已发布关系引用，请先驳回相关关系")
        graph.execute_write("MATCH (n {name: $name}) WHERE n.status = '候选' DETACH DELETE n",
                           name=body.name)
        return {"rejected": "node", "name": body.name}
    if body.kind == "edge":
        if not (body.source and body.relation and body.target):
            raise HTTPException(status_code=422, detail="edge 需提供 source/relation/target")
        graph.execute_write(
            "MATCH (a {name: $s})-[r]->(b {name: $t}) WHERE type(r) = $rel AND r.status = '候选' DELETE r",
            s=body.source, t=body.target, rel=body.relation,
        )
        return {"rejected": "edge", "source": body.source, "relation": body.relation, "target": body.target}
    raise HTTPException(status_code=422, detail="kind 取值为 node|edge")