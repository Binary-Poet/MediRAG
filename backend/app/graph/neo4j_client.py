"""Neo4j 客户端：连接管理与 1~2 跳图谱查询。

只查询 status='已发布' 的节点**与关系**（候选审核闭环：候选节点/候选边均不进问答）。
2 跳遍历收紧为只走语义关系白名单（与浏览接口同源，防 fan-out 噪声）：中间边越白名单
会让「症状→无关证候→无关方剂」这类旁支混进问答证据。
"""
from neo4j import GraphDatabase

from app.config import get_settings
from app.graph.extractor import VALID_RELATIONS

# 关系白名单的唯一真源是抽取侧 VALID_RELATIONS；sorted 保证 Cypher 文本跨进程稳定
# （set 迭代序受 PYTHONHASHSEED 影响）。可信 Python 常量拼接，无注入面。
RELATIONS_LITERAL = ",".join(f"'{r}'" for r in sorted(VALID_RELATIONS))

# 定向路径模板：把「多跳」从无向泛遍历升级为按语义路径走，fan-out 由模板本身约束。
# 端点方向以 startNode/endNode 还原（匹配用无向，兼容图谱里边的实际朝向）；
# 节点与边一律只取 status='已发布'，候选审核闭环不被绕过。
_TEMPLATE_CYPHER = {
    # 症状→证候→方剂：hit = 有多少个查询症状共同指向该证候（多症状联合推理的直接信号）
    "symptom_to_formula": """
        MATCH (s:症状)-[r1:表现]-(d:证候)-[r2:主治]-(f:方剂)
        WHERE s.name IN $names AND s.status = '已发布'
          AND d.status = '已发布' AND f.status = '已发布'
          AND r1.status = '已发布' AND r2.status = '已发布'
        WITH startNode(r2).name AS source, endNode(r2).name AS target,
             count(DISTINCT s.name) AS hit
        RETURN source, '主治' AS relation, target, hit
        ORDER BY hit DESC
    """,
    # 多证候→方剂：hit = 有多少个查询证候共同主治于该方剂（合病/复合证型推理）
    "syndrome_to_formula": """
        MATCH (d:证候)-[r:主治]-(f:方剂)
        WHERE d.name IN $names AND d.status = '已发布'
          AND f.status = '已发布' AND r.status = '已发布'
        WITH startNode(r).name AS source, endNode(r).name AS target,
             count(DISTINCT d.name) AS hit
        RETURN source, '主治' AS relation, target, hit
        ORDER BY hit DESC
    """,
    # 方剂→组成→中药（+ 中药→功效）：配伍机制链；无功效边的中药仍返回组成事实
    "formula_mechanism": """
        MATCH (f:方剂)-[r1:组成]-(h:中药)
        WHERE f.name IN $names AND f.status = '已发布'
          AND h.status = '已发布' AND r1.status = '已发布'
        OPTIONAL MATCH (h)-[r2:功效]-(e:功效)
        WHERE r2.status = '已发布' AND e.status = '已发布'
        RETURN startNode(r1).name AS source, endNode(r1).name AS target,
               startNode(r2).name AS eff_source, endNode(r2).name AS eff_target
    """,
}


class GraphClient:
    def __init__(self, uri: str, user: str, password: str, driver=None) -> None:
        """driver 参数供测试注入 fake；缺省创建真实驱动。"""
        self._driver = driver or GraphDatabase.driver(uri, auth=(user, password))

    def close(self) -> None:
        if self._driver is not None:
            self._driver.close()

    def execute_write(self, cypher: str, **params) -> None:
        with self._driver.session() as session:
            session.run(cypher, **params).consume()

    def run_read(self, cypher: str, **params) -> list[dict]:
        """只读查询，返回行列表（业务 API 用，避免外部访问私有驱动）。"""
        with self._driver.session() as session:
            return session.run(cypher, **params).data()

    def all_entities(self) -> list[dict]:
        """全部已发布节点，供实体识别构建词表。"""
        cypher = """
        MATCH (n) WHERE n.status = '已发布'
        RETURN n.name AS name, n.alias AS alias, n.type AS type
        """
        with self._driver.session() as session:
            rows = session.run(cypher).data()
        return [{"name": r["name"], "alias": r["alias"] or "", "type": r["type"]} for r in rows]

    def neighbors(self, names: list[str], hop: int = 1) -> list[dict]:
        """指定实体的 1~hop 跳关系（无向遍历，去重后的有向事实边）。"""
        if not names:
            return []
        hop = min(max(int(hop), 1), 2)
        cypher = f"""
        MATCH p = (a)-[*1..{hop}]-(b)
        WHERE a.name IN $names AND a.status = '已发布' AND b.status = '已发布'
        AND ALL(r IN relationships(p) WHERE type(r) IN [{RELATIONS_LITERAL}])
        UNWIND relationships(p) AS r
        WITH r WHERE r.status = '已发布'
        RETURN DISTINCT startNode(r).name AS source, type(r) AS relation,
               endNode(r).name AS target,
               startNode(r).type AS source_type, endNode(r).type AS target_type,
               r.status AS status
        """
        with self._driver.session() as session:
            return session.run(cypher, names=names).data()

    def directed_paths(self, template: str, names: list[str]) -> list[dict]:
        """按模板查询定向多跳链路（症状→证候→方剂 / 方剂→组成→中药→功效）。

        返回扁平事实边列表，事实带 path_template；共现类模板附 hit（共同指向的查询实体数）。
        未知模板或空实体直接返回空列表。
        """
        if not names or template not in _TEMPLATE_CYPHER:
            return []
        with self._driver.session() as session:
            rows = session.run(_TEMPLATE_CYPHER[template], names=list(names)).data()
        facts: list[dict] = []
        for r in rows:
            fact = {"source": r["source"], "relation": r["relation"], "target": r["target"],
                    "path_template": template}
            if r.get("hit") is not None:
                fact["hit"] = r["hit"]
            facts.append(fact)
            if r.get("eff_target"):
                facts.append({"source": r["eff_source"], "relation": "功效",
                              "target": r["eff_target"], "path_template": template})
        return facts


_client: GraphClient | None = None


def get_graph() -> GraphClient:
    """进程级单例。"""
    global _client
    if _client is None:
        s = get_settings()
        _client = GraphClient(s.neo4j_uri, s.neo4j_user, s.neo4j_password)
    return _client