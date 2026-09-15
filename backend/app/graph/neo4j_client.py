"""Neo4j 客户端：连接管理与 1~2 跳图谱查询。

只查询 status='已发布' 的节点**与关系**（候选审核闭环：候选节点/候选边均不进问答）。
"""
from neo4j import GraphDatabase

from app.config import get_settings


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
        UNWIND relationships(p) AS r
        WITH r WHERE r.status = '已发布'
        RETURN DISTINCT startNode(r).name AS source, type(r) AS relation,
               endNode(r).name AS target,
               startNode(r).type AS source_type, endNode(r).type AS target_type,
               r.status AS status
        """
        with self._driver.session() as session:
            return session.run(cypher, names=names).data()


_client: GraphClient | None = None


def get_graph() -> GraphClient:
    """进程级单例。"""
    global _client
    if _client is None:
        s = get_settings()
        _client = GraphClient(s.neo4j_uri, s.neo4j_user, s.neo4j_password)
    return _client