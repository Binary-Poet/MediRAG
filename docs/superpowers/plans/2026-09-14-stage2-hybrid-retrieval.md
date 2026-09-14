# 阶段 2：三路混合检索 + RRF + Rerank 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把阶段 1 的"单路向量检索"升级为"向量 + BM25 关键词 + Neo4j 图谱"三路混合检索，RRF 融合后经 bge-reranker 精排，前端上线溯源弹窗展示三路命中数（复现截图「0/22/0」式命中面板）。

**Architecture:** 图谱检索接入真实 Neo4j（Docker 已运行，bolt://localhost:7687，`data/graph/seed_tcm_graph.json` 幂等导入，仅查询 `status='已发布'` 节点）；BM25 用 jieba 分词 + rank-bm25 内存索引（构建自现有 vector store 的 11 条切片）；向量 + 关键词两路结果 RRF 融合，图谱证据独立汇合不参与 RRF（合并方案 3.1 约定）；融合候选经 SiliconFlow `/rerank` 精排取最终证据；`/api/chat/ask` 响应扩展 `graph_facts` + `trace` 字段，前端弹窗据此渲染 5 步溯源。

**Tech Stack:** Python 3.12、FastAPI、neo4j driver、rank-bm25、jieba、httpx、Vue 3 + Element Plus + TypeScript。

**Spec:** `docs/MediRAG-合并改造方案.md`（阶段 2、6.2 工具签名语义、6.3 RRF 伪码、6.5 图谱 schema）+ `docs/前端还原规格.md`（P0-3 回答态、P0-4 溯源弹窗）

## Global Constraints

- 测试不得依赖真实网络 / Neo4j / LLM：所有外部调用 monkeypatch 或注入 fake（沿用 `backend/tests/` 既有模式）。
- RRF 公式：`score += w * 1/(k + rank + 1)`，k 默认 60（方案 6.3）。
- 图谱检索只返回 `status = '已发布'` 的节点/边；谱边用中文关系类型（组成/主治/功效/禁忌/表现）。
- 前端设计 token 一律取 `web/src/styles/theme.ts`，组件内不得写死色值。
- 文案以《前端还原规格.md》为准，不得自造。
- 不新增原图不存在的能力面板；Agent 轨迹/反思收纳于既有溯源弹窗（阶段 3 才涉及）。
- `data/vectorstore/index.json` 已有 11 条 1024 维向量（bge-m3），`backend/.env` 已配置 SiliconFlow key。Neo4j 容器 `medirag-neo4j` 已运行（neo4j/medirag123）。
- 推理配置默认值（20/20/25/5/60）先入 `config.py`，阶段 5 再改为用户级存储。

## 文件结构

| 文件 | 责任 |
|---|---|
| `backend/app/graph/neo4j_client.py`（新建） | Neo4j 连接单例：`all_entities` / `neighbors` / `execute_write` |
| `backend/app/graph/importer.py`（新建） | seed JSON → Neo4j 幂等导入（CLI） |
| `backend/app/graph/entity_recognizer.py`（新建） | 词典最长匹配实体识别（阶段 3 被 LLM 理解取代） |
| `backend/app/retrieval/keyword.py`（新建） | jieba + rank-bm25 内存关键词索引 |
| `backend/app/retrieval/rrf.py`（新建） | RRF 融合 |
| `backend/app/llm/rerank.py`（新建） | SiliconFlow `/rerank` 客户端 |
| `backend/app/config.py`（修改） | 追加检索参数默认值 |
| `backend/app/api/chat.py`（修改） | ask 改造为三路汇聚 + trace |
| `backend/app/agent/prompts/answer_cn_tcm.txt`（修改） | 增加【图谱事实】段与约束 |
| `backend/requirements.txt`（修改） | +neo4j +rank-bm25 +jieba |
| `backend/tests/test_graph_client.py` 等（新建/修改） | 各模块无网络测试 |
| `web/src/types/chat.ts`、`web/src/api/chat.ts`（修改） | GraphFact / Trace 类型 |
| `web/src/views/qa/components/TraceDialog.vue`（新建） | 溯源弹窗（规格 P0-4） |
| `web/src/views/qa/Chat.vue`（修改） | 回答态（规格 P0-3）+ 弹窗集成 |

---

### Task 1: 依赖 + Neo4j 客户端

**Files:**
- Modify: `backend/requirements.txt`
- Create: `backend/app/graph/__init__.py`（空）
- Create: `backend/app/graph/neo4j_client.py`
- Test: `backend/tests/test_graph_client.py`

**Interfaces:**
- Produces: `GraphClient(uri, user, password, driver=None)`，方法
  `all_entities() -> list[dict{name, alias, type}]`、
  `neighbors(names: list[str], hop: int = 1) -> list[dict{source, relation, target, source_type, target_type}]`、
  `execute_write(cypher: str, **params) -> None`、`close()`
  模块级 `get_graph() -> GraphClient`（进程级单例）

- [ ] **Step 1: 追加依赖**

修改 `backend/requirements.txt`，在 numpy 行后追加：

```
neo4j>=5.20,<6
rank-bm25>=0.2.2,<1
jieba>=0.42.1,<1
```

安装：`cd backend && .venv/Scripts/python -m pip install neo4j rank-bm25 jieba`

- [ ] **Step 2: 写失败测试** `backend/tests/test_graph_client.py`

```python
"""图谱客户端测试：driver 注入 fake，不连真实 Neo4j。"""
from unittest.mock import MagicMock

import pytest

from app.graph.neo4j_client import GraphClient


def _rx(*rows):
    m = MagicMock(name="result")
    m.data.return_value = list(rows)
    return m


def _fake_driver(rx):
    driver = MagicMock()
    session = MagicMock()
    session.run.return_value = rx
    driver.session.return_value.__enter__.return_value = session
    return driver


def test_all_entities_returns_name_alias_type():
    driver = _fake_driver(_rx({"name": "人参", "alias": "园参、山参", "type": "中药"}))
    c = GraphClient("bolt://x", "u", "p", driver=driver)

    ents = c.all_entities()

    assert ents == [{"name": "人参", "alias": "园参、山参", "type": "中药"}]
    session = driver.session.return_value.__enter__.return_value
    cypher = session.run.call_args.args[0]
    assert "status = '已发布'" in cypher


def test_neighbors_returns_facts_and_filters_status():
    driver = _fake_driver(_rx({"source": "四君子汤", "relation": "组成",
                               "target": "人参", "source_type": "方剂", "target_type": "中药"}))
    c = GraphClient("bolt://x", "u", "p", driver=driver)

    facts = c.neighbors(["四君子汤"], hop=1)

    assert facts[0]["relation"] == "组成"
    session = driver.session.return_value.__enter__.return_value
    kwargs = session.run.call_args.kwargs
    assert kwargs["names"] == ["四君子汤"]


def test_neighbors_empty_names_returns_empty():
    c = GraphClient("bolt://x", "u", "p", driver=MagicMock())
    assert c.neighbors([], hop=1) == []


def test_neighbors_clamps_hop_to_1_2():
    driver = _fake_driver(_rx())
    c = GraphClient("bolt://x", "u", "p", driver=driver)
    c.neighbors(["人参"], hop=5)
    cypher = driver.session.return_value.__enter__.return_value.run.call_args.args[0]
    assert "[*1..2]" in cypher
```

- [ ] **Step 3: 运行确认失败**

Run: `cd backend && .venv/Scripts/python -m pytest tests/test_graph_client.py -v`
Expected: FAIL（`ModuleNotFoundError: app.graph.neo4j_client`）

- [ ] **Step 4: 实现** `backend/app/graph/neo4j_client.py`

```python
"""Neo4j 客户端：连接管理与 1~2 跳图谱查询。

只查询 status='已发布' 的节点（候选审核闭环：候选节点不进问答）。
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
        RETURN DISTINCT startNode(r).name AS source, type(r) AS relation,
               endNode(r).name AS target,
               startNode(r).type AS source_type, endNode(r).type AS target_type
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
```

- [ ] **Step 5: 运行确认通过**

Run: `cd backend && .venv/Scripts/python -m pytest tests/test_graph_client.py -v`
Expected: PASS（4 passed）

- [ ] **Step 6: 提交**

```bash
git add backend/requirements.txt backend/app/graph __pycache__ 2>/dev/null; git add backend/requirements.txt backend/app/graph && git commit -m "feat(graph): Neo4j client with published-only 1-2 hop queries"
```

（若项目根尚未 `git init`，先执行 `git init` 并确认 `.gitignore` 已排除 `.venv/`、`__pycache__/`、`.env`，再提交。）

---

### Task 2: 图谱 seed 导入器

**Files:**
- Create: `backend/app/graph/importer.py`
- Test: `backend/tests/test_graph_importer.py`

**Interfaces:**
- Consumes: `get_graph()`（Task 1）、`GraphClient.execute_write(cypher, **params)`
- Produces: `load_seed(path: Path = SEED_PATH) -> dict`、`import_seed(graph, path: Path = SEED_PATH) -> dict{nodes, edges}`、CLI `python -m app.graph.importer`

- [ ] **Step 1: 写失败测试** `backend/tests/test_graph_importer.py`

```python
"""图谱导入测试：注入 fake client，验证 MERGE 计数与哨兵字段。"""
import json
from pathlib import Path

import pytest

from app.graph.importer import import_seed


class FakeGraph:
    def __init__(self):
        self.calls: list[tuple[str, dict]] = []

    def execute_write(self, cypher: str, **params) -> None:
        self.calls.append((cypher, params))


def _seed(tmp_path: Path, nodes: int = 2, edges: int = 1) -> Path:
    p = tmp_path / "seed.json"
    p.write_text(json.dumps({
        "nodes": [
            {"id": "n1", "name": "人参", "type": "中药", "alias": "园参、山参",
             "desc": "补气", "source": "内置数据"},
            {"id": "n2", "name": "四君子汤", "type": "方剂", "alias": "",
             "desc": "益气健脾", "source": "内置数据"},
        ],
        "edges": [{"source": "n2", "relation": "组成", "target": "n1", "note": "组成之一"}],
    }, ensure_ascii=False), encoding="utf-8")
    return p


def test_import_seed_merges_nodes_and_edges(tmp_path):
    g = FakeGraph()
    seed_path = _seed(tmp_path)

    stats = import_seed(g, path=seed_path)

    assert stats == {"nodes": 2, "edges": 1}
    node_calls = [c for c in g.calls if "MERGE" in c[0]]
    edge_calls = [c for c in g.calls if "MATCH (a" in c[0]]
    assert len(node_calls) == 2 and len(edge_calls) == 1
    # 节点哨兵：status=已发布 且带 type 属性
    assert "status='已发布'" in node_calls[0][0]
    assert node_calls[0][1]["name"] == "人参"
    # 边端点用 name 关联（seed 边以 id 引用，导入前需映射 id -> name）
    assert edge_calls[0][1] == {"s": "四君子汤", "t": "人参", "note": "组成之一"}
```

- [ ] **Step 2: 运行确认失败**

Run: `cd backend && .venv/Scripts/python -m pytest tests/test_graph_importer.py -v`
Expected: FAIL（模块不存在）

- [ ] **Step 3: 实现** `backend/app/graph/importer.py`

```python
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
            "MERGE (n:`" + n["type"] + "` {name: $name}) "
            "SET n.alias = $alias, n.desc = $desc, n.source = $source, "
            "n.type = $type, n.status = '已发布'",
            name=n["name"], alias=n["alias"], desc=n["desc"],
            source=n["source"], type=n["type"],
        )

    id_to_name = {n["id"]: n["name"] for n in nodes}
    for e in edges:
        graph.execute_write(
            "MATCH (a {name: $s}), (b {name: $t}) "
            "MERGE (a)-[r:`" + e["relation"] + "`]->(b) SET r.note = $note",
            s=id_to_name[e["source"]], t=id_to_name[e["target"]], note=e.get("note", ""),
        )

    return {"nodes": len(nodes), "edges": len(edges)}


if __name__ == "__main__":
    stats = import_seed()
    print(f"[graph] 导入 {stats['nodes']} 节点 / {stats['edges']} 关系")
```

> 注：label 与关系类型拼接自本地受控的 seed JSON（反引号包裹防注入），非用户输入。

- [ ] **Step 4: 运行确认通过**

Run: `cd backend && .venv/Scripts/python -m pytest tests/test_graph_importer.py -v`
Expected: PASS

- [ ] **Step 5: 真实导入 + 验证**

Run: `cd backend && .venv/Scripts/python -m app.graph.importer`
Expected: `[graph] 导入 24 节点 / 27 关系`

再跑一遍确认幂等：重复执行输出不变、无报错。

- [ ] **Step 6: 提交**

```bash
git add backend/app/graph/importer.py backend/tests/test_graph_importer.py
git commit -m "feat(graph): idempotent seed importer (24 nodes / 27 edges to Neo4j)"
```

---

### Task 3: 实体识别器（词典最长匹配）

**Files:**
- Create: `backend/app/graph/entity_recognizer.py`
- Test: `backend/tests/test_entity_recognizer.py`

**Interfaces:**
- Consumes: `GraphClient.all_entities()` 返回词表（shape `[{'name','alias','type'}]`，alias 以顿号分隔）
- Produces: `recognize_entities(question: str, vocab: list[dict]) -> list[dict{name, type, matched}]`（按原文出现顺序，主名去重）

- [ ] **Step 1: 写失败测试** `backend/tests/test_entity_recognizer.py`

```python
"""实体识别测试：词典匹配 / 别名命中 / 最长优先 / 去重 / 跳过重叠。"""
from app.graph.entity_recognizer import recognize_entities

VOCAB = [
    {"name": "四君子汤", "alias": "", "type": "方剂"},
    {"name": "当归", "alias": "", "type": "中药"},
    {"name": "鹿角胶", "alias": "", "type": "中药"},
    {"name": "人参", "alias": "园参、山参", "type": "中药"},
    {"name": "发热重微恶风", "alias": "", "type": "症状"},
]


def test_matches_exact_name():
    hits = recognize_entities("四君子汤由哪些中药组成？", VOCAB)
    assert hits == [{"name": "四君子汤", "type": "方剂", "matched": "四君子汤"}]


def test_matches_alias_and_dedups():
    hits = recognize_entities("园参有什么功效？", VOCAB)
    assert hits == [{"name": "人参", "type": "中药", "matched": "园参"}]


def test_longest_match_wins():
    hits = recognize_entities("发热重微恶风怎么缓解", VOCAB)
    assert [h["matched"] for h in hits] == ["发热重微恶风"]


def test_multiple_entities_in_order():
    hits = recognize_entities("当归和人参一起用", VOCAB)
    assert [h["name"] for h in hits] == ["当归", "人参"]


def test_overlapping_terms_take_first_longest():
    # "鹿角胶" 覆盖后，内部不重复命中
    hits = recognize_entities("鹿角胶补什么", VOCAB)
    assert len(hits) == 1 and hits[0]["name"] == "鹿角胶"


def test_no_match_returns_empty():
    assert recognize_entities("今天的天气怎么样", VOCAB) == []
```

- [ ] **Step 2: 运行确认失败**

Run: `cd backend && .venv/Scripts/python -m pytest tests/test_entity_recognizer.py -v`
Expected: FAIL（模块不存在）

- [ ] **Step 3: 实现** `backend/app/graph/entity_recognizer.py`

```python
"""实体识别：基于图谱词表的词典最长匹配（阶段 3 由 LLM query_understand 取代）。

vocab 来自 GraphClient.all_entities()：每个 {name, alias, type}，
alias 以顿号分隔（如 "园参、山参"）。
"""
from collections.abc import Iterable


def recognize_entities(question: str, vocab: Iterable[dict]) -> list[dict]:
    terms: list[tuple[str, dict]] = []
    for v in vocab:
        cands = [v["name"], *(p.strip() for p in (v["alias"] or "").split("、") if p.strip())]
        terms.extend((c, v) for c in cands if c)
    # 最长优先，避免短词先占位截断长词（如"发热重微恶风" vs "发热"）
    terms.sort(key=lambda t: -len(t[0]))

    hits: list[dict] = []
    covered = [False] * len(question)
    for term, v in terms:
        start = 0
        while True:
            idx = question.find(term, start)
            if idx < 0:
                break
            if not any(covered[idx: idx + len(term)]):
                for i in range(idx, idx + len(term)):
                    covered[i] = True
                hits.append({"name": v["name"], "type": v["type"], "matched": term})
            start = idx + 1

    seen: set[str] = set()
    ordered: list[dict] = []
    for h in hits:  # 按原文顺序归并（别名命中归顺到主名）
        if h["name"] not in seen:
            seen.add(h["name"])
            ordered.append(h)
    return ordered
```

- [ ] **Step 4: 运行确认通过**

Run: `cd backend && .venv/Scripts/python -m pytest tests/test_entity_recognizer.py -v`
Expected: PASS（6 passed）

- [ ] **Step 5: 提交**

```bash
git add backend/app/graph/entity_recognizer.py backend/tests/test_entity_recognizer.py
git commit -m "feat(graph): dictionary longest-match entity recognizer"
```

---

### Task 4: BM25 关键词检索

**Files:**
- Create: `backend/app/retrieval/keyword.py`
- Test: `backend/tests/test_keyword.py`

**Interfaces:**
- Consumes: `get_store().chunks`（`backend/app/retrieval/vector_store.py`）
- Produces: `KeywordIndex`（`build(chunks) -> int`、`search(query, top_k=20) -> list[dict]`，结果 dict 含原 metadata + `score`）、模块级 `get_keyword_index()`

- [ ] **Step 1: 写失败测试** `backend/tests/test_keyword.py`

```python
"""关键词检索测试：jieba + rank-bm25 排序与过滤。"""
from app.retrieval.keyword import KeywordIndex

CHUNKS = [
    {"chunk_id": "a", "title": "四君子汤", "text": "由人参、白术、茯苓、炙甘草组成，益气健脾", "doc_name": "x", "chapter": "c", "page_no": 1, "topic": "综合典籍"},
    {"chunk_id": "b", "title": "人参", "text": "大补元气、补脾益肺，为补气要药", "doc_name": "y", "chapter": "c", "page_no": 2, "topic": "综合典籍"},
    {"chunk_id": "c", "title": "茯苓", "text": "利水渗湿、健脾宁心", "doc_name": "z", "chapter": "c", "page_no": 3, "topic": "综合典籍"},
]


def test_search_returns_ranked_hits():
    idx = KeywordIndex()
    assert idx.build(CHUNKS) == 3

    hits = idx.search("四君子汤 人参", top_k=3)

    assert hits and hits[0]["chunk_id"] == "a"  # 同时命中两个词
    assert all("score" in h for h in hits)
    assert all(h["doc_name"] for h in hits)  # metadata 完整透传


def test_search_zero_score_filtered():
    idx = KeywordIndex()
    idx.build(CHUNKS)

    hits = idx.search("天气", top_k=3)  # 完全不相关的词，jieba 无命中词

    assert hits == []


def test_search_unbuilt_returns_empty():
    assert KeywordIndex().search("人参") == []
```

- [ ] **Step 2: 运行确认失败**

Run: `cd backend && .venv/Scripts/python -m pytest tests/test_keyword.py -v`
Expected: FAIL（模块不存在）

- [ ] **Step 3: 实现** `backend/app/retrieval/keyword.py`

```python
"""关键词检索：jieba 分词 + rank-bm25 内存索引（语料为百级切片，性能足够）。

索引构建自 vector store 的同一批切片（get_store().chunks），保证
向量/关键词两路元数据与 chunk_id 一致性，供 RRF 按 chunk_id 去重融合。
"""
import jieba
from rank_bm25 import BM25Okapi

from app.retrieval.vector_store import get_store


class KeywordIndex:
    def __init__(self) -> None:
        self._bm25: BM25Okapi | None = None
        self._chunks: list[dict] = []

    def build(self, chunks: list[dict]) -> int:
        """全量重建索引，返回切片数。"""
        self._chunks = list(chunks)
        corpus = [jieba.lcut(f"{c['title']}：{c['text']}") for c in self._chunks]
        self._bm25 = BM25Okapi(corpus)
        return len(self._chunks)

    def search(self, query: str, top_k: int = 20) -> list[dict]:
        if self._bm25 is None or not self._chunks:
            return []
        scores = self._bm25.get_scores(jieba.lcut(query))
        order = sorted(range(len(scores)), key=lambda i: -scores[i])[:top_k]
        return [
            {**self._chunks[i], "score": float(scores[i])}
            for i in order if scores[i] > 0.0
        ]


_index: KeywordIndex | None = None


def get_keyword_index() -> KeywordIndex:
    """进程级单例：懒构建，语料来自向量库已入库切片。"""
    global _index
    if _index is None:
        _index = KeywordIndex()
        _index.build(get_store().chunks)
    return _index
```

- [ ] **Step 4: 运行确认通过**

Run: `cd backend && .venv/Scripts/python -m pytest tests/test_keyword.py -v`
Expected: PASS（3 passed）

- [ ] **Step 5: 提交**

```bash
git add backend/app/retrieval/keyword.py backend/tests/test_keyword.py
git commit -m "feat(retrieval): jieba + rank-bm25 keyword search"
```

---

### Task 5: RRF 融合

**Files:**
- Create: `backend/app/retrieval/rrf.py`
- Test: `backend/tests/test_rrf.py`

**Interfaces:**
- Produces: `rrf_fuse(rank_lists: list[list[dict]], k: int = 60, weights: list[float] | None = None) -> list[dict]`（按 `rrf_score` 降序，同一 chunk_id 只保留一条并附带该 chunk）

- [ ] **Step 1: 写失败测试** `backend/tests/test_rrf.py`

```python
"""RRF 测试：去重 / 排序 / 权重 / 跨路同分。"""
from app.retrieval.rrf import rrf_fuse


def _chunk(cid):
    return {"chunk_id": cid, "title": cid, "text": cid, "score": 0.5}


def test_fuse_dedup_shared_chunk_and_rank_above_single():
    a, b, c = _chunk("a"), _chunk("b"), _chunk("c")
    fused = rrf_fuse([[a, b], [b, c]], k=60)

    ids = [d["chunk_id"] for d in fused]
    assert ids == ["b", "a", "c"]  # b 双路命中居首，随后按融合分
    assert len(fused) == 3
    assert fused[0]["rrf_score"] > fused[1]["rrf_score"] + 1e-9


def test_fuse_weights_shift_ranking():
    a, b = _chunk("a"), _chunk("b")
    # 路 1 权重 10 > 路 2 权重 1：a 双分仍应超过 b 单分？此处验证权重放大路面排名
    fused = rrf_fuse([[a], [b]], k=60, weights=[10.0, 1.0])
    assert fused[0]["chunk_id"] == "a"
    double = rrf_fuse([[a, b], [b, c := _chunk("c")]], k=60, weights=[1.0, 1.0])
    assert double[0]["chunk_id"] == "b"


def test_fuse_empty_and_empty_lists():
    assert rrf_fuse([], k=60) == []
    assert rrf_fuse([[], []], k=60) == []
```

- [ ] **Step 2: 运行确认失败**

Run: `cd backend && .venv/Scripts/python -m pytest tests/test_rrf.py -v`
Expected: FAIL（模块不存在）

- [ ] **Step 3: 实现** `backend/app/retrieval/rrf.py`

```python
"""RRF（Reciprocal Rank Fusion）：向量 + 关键词两路按 chunk_id 去重累加。

公式与合并方案 6.3 伪码一致：score += w * 1 / (k + rank + 1)。
k 对应推理配置页「融合平衡系数 60」。
"""


def rrf_fuse(rank_lists: list[list[dict]], k: int = 60,
             weights: list[float] | None = None) -> list[dict]:
    if not rank_lists:
        return []
    ws = weights or [1.0] * len(rank_lists)
    scores: dict[str, float] = {}
    by_id: dict[str, dict] = {}
    for docs, w in zip(rank_lists, ws):
        for rank, d in enumerate(docs):
            cid = d["chunk_id"]
            scores[cid] = scores.get(cid, 0.0) + w * (1.0 / (k + rank + 1))
            by_id[cid] = d
    return [
        {**by_id[cid], "rrf_score": s}
        for cid, s in sorted(scores.items(), key=lambda x: -x[1])
    ]
```

- [ ] **Step 4: 运行确认通过**

Run: `cd backend && .venv/Scripts/python -m pytest tests/test_rrf.py -v`
Expected: PASS

> 若 `test_fuse_weights_shift_ranking` 中 `c := _chunk("c")` 写法有兼容性问题，改为在调用前单独构造变量。

- [ ] **Step 5: 提交**

```bash
git add backend/app/retrieval/rrf.py backend/tests/test_rrf.py
git commit -m "feat(retrieval): RRF fusion with weights"
```

---

### Task 6: SiliconFlow Rerank 客户端

**Files:**
- Create: `backend/app/llm/rerank.py`
- Test: `backend/tests/test_rerank.py`

**Interfaces:**
- Produces: `rerank(query: str, documents: list[str], top_n: int = 5) -> list[dict{index, score}]`（按相关度降序；documents 为空返回 `[]`；key 未配置抛 RuntimeError）

- [ ] **Step 1: 写失败测试** `backend/tests/test_rerank.py`

```python
"""Rerank 测试：monkeypatch httpx，无网络。"""
import httpx
import pytest

import app.llm.rerank as rerank_mod
from app.llm.rerank import rerank


def _fake_post_ok(monkeypatch, results=None):
    resp = httpx.Response(200, json={"id": "x", "results": results or [
        {"index": 1, "relevance_score": 0.90},
        {"index": 0, "relevance_score": 0.70},
    ]})
    monkeypatch.setattr(rerank_mod.httpx, "post", lambda *a, **k: resp)


def test_rerank_returns_top_n_sorted(monkeypatch):
    _fake_post_ok(monkeypatch)

    out = rerank("人参的功效", ["文本a", "文本b"])

    assert out == [{"index": 1, "score": 0.90}, {"index": 0, "score": 0.70}]


def test_rerank_empty_documents_returns_empty():
    assert rerank("问题", []) == []


def test_rerank_no_key_raises(monkeypatch):
    class FakeSettings:
        siliconflow_api_key = ""

    monkeypatch.setattr(rerank_mod, "get_settings", lambda: FakeSettings())
    with pytest.raises(RuntimeError, match="SILICONFLOW_API_KEY"):
        rerank("q", ["d"])
```

- [ ] **Step 2: 运行确认失败**

Run: `cd backend && .venv/Scripts/python -m pytest tests/test_rerank.py -v`
Expected: FAIL（模块不存在）

- [ ] **Step 3: 实现** `backend/app/llm/rerank.py`

```python
"""Rerank 客户端：SiliconFlow /rerank（BAAI/bge-reranker-v2-m3，OpenAI 兼容网关）。"""
import httpx

from app.config import get_settings


def rerank(query: str, documents: list[str], top_n: int = 5) -> list[dict]:
    """按相关度降序返回 [{'index': i, 'score': s}]，index 指向原 documents 下标。"""
    if not documents:
        return []
    s = get_settings()
    if not s.siliconflow_api_key:
        raise RuntimeError("SILICONFLOW_API_KEY 未配置，请在 backend/.env 填入")
    resp = httpx.post(
        f"{s.siliconflow_base_url}/rerank",
        headers={"Authorization": f"Bearer {s.siliconflow_api_key}"},
        json={"model": s.rerank_model, "query": query,
              "documents": documents, "top_n": min(top_n, len(documents))},
        timeout=60,
    )
    resp.raise_for_status()
    results = resp.json()["results"]
    return [{"index": r["index"], "score": r["relevance_score"]} for r in results]
```

- [ ] **Step 4: 运行确认通过**

Run: `cd backend && .venv/Scripts/python -m pytest tests/test_rerank.py -v`
Expected: PASS（3 passed）

- [ ] **Step 5: 提交**

```bash
git add backend/app/llm/rerank.py backend/tests/test_rerank.py
git commit -m "feat(llm): SiliconFlow rerank client"
```

---

### Task 7: ask 接口三路汇聚 + Prompt 图谱事实

**Files:**
- Modify: `backend/app/config.py`（追加检索参数）
- Modify: `backend/app/agent/prompts/answer_cn_tcm.txt`
- Modify: `backend/app/api/chat.py`
- Test: `backend/tests/test_chat_api.py`（更新既有 3 个用例 + 新增三路汇聚用例）

**Interfaces:**
- Consumes: `get_store()`、`get_keyword_index()`、`get_graph()`、`recognize_entities(question, vocab)`、`rrf_fuse(rank_lists, k, weights)`、`rerank(query, documents, top_n)`、`embed_texts`
- Produces: `AskResponse{answer, references, graph_facts, trace}`，其中
  `trace = {understand: {raw, rewritten, entities}, retrieve: {vector_n, keyword_n, graph_n, entity_n}, fuse: {candidate_n, method}, rerank: {evidence_n, confidence, status}}`
- 常量（config）：`semantic_k=20, keyword_k=20, fuse_candidate=25, final_evidence=5, rrf_k=60`

- [ ] **Step 1: config 追加检索默认值**

`backend/app/config.py` 在 `vector_store` 段后追加：

```python
    # ===== 混合检索（阶段 2；阶段 5 改为用户级推理配置存储）=====
    semantic_k: int = 20        # 语义召回数
    keyword_k: int = 20         # 关键词召回数
    fuse_candidate: int = 25    # 融合候选数
    final_evidence: int = 5     # 最终证据数
    rrf_k: int = 60             # 融合平衡系数
    rerank_top_n: int = 5       # 精排取前 N（与 final_evidence 联动）
```

同步 `backend/.env.example` 追加同名注释行（不给值，用默认）。

- [ ] **Step 2: Prompt 增加图谱事实段**

`backend/app/agent/prompts/answer_cn_tcm.txt` 全文替换为：

```
你是中医药知识助手「本草智问」，面向知识科普场景回答问题。请严格遵守：

1. 只依据下方【文献证据】与【图谱事实】中的内容回答，不得编造或添加证据之外的药材、方剂、功效。
2. 组成、禁忌类结论只能引用【图谱事实】，不得加减药材或给出证据之外的禁忌。
3. 引用文献证据时在相应句子末尾标注编号，格式如 [1]、[2]。
4. 若证据不足以回答问题，直接说明"知识库中未检索到可靠依据"，不要猜测。
5. 回答仅提供中医药知识科普，不替代辨证、诊断或个体化处方。

【图谱事实】
{graph_facts}

【文献证据】
{evidence}

【问题】
{question}
```

- [ ] **Step 3: 写失败测试（既有用例更新 + 新增汇聚用例）**

`backend/tests/test_chat_api.py` 全文替换为：

```python
"""问答接口闭环测试：monkeypatch 向量库/关键词/图谱/LLM/rerank，无网络。

验证：三路召回 → RRF → 精排 → 证据组装 → 图谱事实独立汇入 → trace 返回。
"""
from unittest.mock import MagicMock

import app.api.chat as chat_module
from app.retrieval.keyword import KeywordIndex
from app.retrieval.vector_store import LocalVectorStore

SAMPLE_CHUNK = {
    "chunk_id": "中药方剂学基础#0001",
    "title": "四君子汤",
    "doc_name": "中药方剂学基础",
    "chapter": "第1节",
    "page_no": 1,
    "topic": "综合典籍",
    "text": "四君子汤由人参、白术、茯苓、炙甘草四味药组成",
    "embedding": [1.0, 0.0],
}


def _fake_store(tmp_path) -> LocalVectorStore:
    store = LocalVectorStore(str(tmp_path / "idx.json"))
    store.upsert([SAMPLE_CHUNK])
    return store


def _fake_graph():
    g = MagicMock()
    g.all_entities.return_value = [
        {"name": "四君子汤", "alias": "", "type": "方剂"},
        {"name": "人参", "alias": "", "type": "中药"},
    ]
    g.neighbors.return_value = [
        {"source": "四君子汤", "relation": "组成", "target": "人参",
         "source_type": "方剂", "target_type": "中药"},
    ]
    return g


def _patch_all(client, monkeypatch, tmp_path, graph=None):
    monkeypatch.setattr(chat_module, "get_store", lambda: _fake_store(tmp_path))
    monkeypatch.setattr(chat_module, "get_keyword_index", lambda: KeywordIndex().build([]) or KeywordIndex())
    monkeypatch.setattr(chat_module, "get_graph", lambda: graph if graph is not None else _fake_graph())
    monkeypatch.setattr(chat_module, "embed_texts", lambda texts: [[1.0, 0.0]])
    monkeypatch.setattr(
        chat_module,
        "rerank",
        lambda query, docs, top_n: [{"index": i, "score": 0.9 - i * 0.1} for i in range(min(top_n, len(docs)))],
    )
    monkeypatch.setattr(
        chat_module,
        "chat_completion",
        lambda system, user, temperature=0.3: "四君子汤由人参、白术、茯苓、炙甘草组成 [1]",
    )


def test_ask_full_loop_with_trace(client, monkeypatch, tmp_path) -> None:
    idx = KeywordIndex()
    idx.build([SAMPLE_CHUNK])
    monkeypatch.setattr(chat_module, "get_keyword_index", lambda: idx)
    _patch_all(client, monkeypatch, tmp_path)

    resp = client.post("/api/chat/ask", json={"question": "四君子汤由哪些中药组成？"})

    assert resp.status_code == 200
    body = resp.json()
    assert "人参" in body["answer"]
    assert len(body["references"]) == 1

    # 图谱事实独立返回
    assert body["graph_facts"] == [{
        "source": "四君子汤", "relation": "组成", "target": "人参",
        "source_type": "方剂", "target_type": "中药",
    }]

    # trace 全链路数字
    t = body["trace"]
    assert t["understand"]["raw"] == "四君子汤由哪些中药组成？"
    assert "四君子汤" in t["understand"]["entities"]
    assert t["retrieve"]["vector_n"] == 1
    assert t["retrieve"]["keyword_n"] == 1
    assert t["retrieve"]["graph_n"] == 1
    assert t["fuse"]["candidate_n"] == 1
    assert t["fuse"]["method"] == "RRF"
    assert t["rerank"]["evidence_n"] == 1
    assert t["rerank"]["status"] == "证据充分，正常生成"


def test_ask_empty_evidence_returns_fallback(client, monkeypatch, tmp_path) -> None:
    empty_graph = MagicMock()
    empty_graph.all_entities.return_value = []
    empty_graph.neighbors.return_value = []
    idx = KeywordIndex()
    idx.build([SAMPLE_CHUNK])
    # 向量命中 0：让 fake store 为空
    monkeypatch.setattr(chat_module, "get_store",
                        lambda: LocalVectorStore(str(tmp_path / "e.json")))
    monkeypatch.setattr(chat_module, "get_keyword_index", lambda: idx)
    monkeypatch.setattr(chat_module, "get_graph", lambda: empty_graph)
    monkeypatch.setattr(chat_module, "embed_texts", lambda texts: [[1.0, 0.0]])

    resp = client.post("/api/chat/ask", json={"question": "今天天气怎么样"})

    assert resp.status_code == 200
    body = resp.json()
    assert "未检索到可靠依据" in body["answer"]
    assert body["references"] == []
    assert body["graph_facts"] == []
    assert body["trace"]["rerank"]["evidence_n"] == 0
    assert body["trace"]["rerank"]["status"] == "知识库未匹配"


def test_ask_rejects_empty_question(client) -> None:
    resp = client.post("/api/chat/ask", json={"question": ""})
    assert resp.status_code == 422
```

> 注意：`_patch_all` 中的 keyword monkeypatch 会被 `test_ask_full_loop_with_trace` 里显式构造的 idx 覆盖（monkeypatch 同键后设生效），无需移除。

- [ ] **Step 4: 运行确认失败**

Run: `cd backend && .venv/Scripts/python -m pytest tests/test_chat_api.py -v`
Expected: FAIL（AskResponse 缺 graph_facts/trace 字段，422/500）

- [ ] **Step 5: 实现 ask 改造**

`backend/app/api/chat.py` 全文替换为：

```python
"""API 路由层：三路混合检索 + RRF + Rerank 问答（阶段 3 换 SSE /api/chat/stream）。"""
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.config import get_settings
from app.graph.entity_recognizer import recognize_entities
from app.graph.neo4j_client import get_graph
from app.llm.chat import chat_completion
from app.llm.embedding import embed_texts
from app.llm.rerank import rerank
from app.retrieval.keyword import get_keyword_index
from app.retrieval.rrf import rrf_fuse
from app.retrieval.vector_store import get_store

router = APIRouter()

PROMPT_PATH = Path(__file__).resolve().parents[1] / "agent" / "prompts" / "answer_cn_tcm.txt"


class AskBody(BaseModel):
    question: str = Field(min_length=1, max_length=500)


class Reference(BaseModel):
    chunk_id: str
    title: str
    doc_name: str
    chapter: str
    page_no: int
    score: float


class GraphFact(BaseModel):
    source: str
    relation: str
    target: str
    source_type: str
    target_type: str


class TraceUnderstand(BaseModel):
    raw: str
    rewritten: str
    entities: list[str]


class TraceRetrieve(BaseModel):
    vector_n: int
    keyword_n: int
    graph_n: int
    entity_n: int


class TraceFuse(BaseModel):
    candidate_n: int
    method: str = "RRF"


class TraceRerank(BaseModel):
    evidence_n: int
    confidence: float
    status: str


class Trace(BaseModel):
    understand: TraceUnderstand
    retrieve: TraceRetrieve
    fuse: TraceFuse
    rerank: TraceRerank


class AskResponse(BaseModel):
    answer: str
    references: list[Reference]
    graph_facts: list[GraphFact]
    trace: Trace


def _fallback_response(question: str) -> AskResponse:
    return AskResponse(
        answer="知识库中未检索到可靠依据。请换个问题或稍后再试。",
        references=[],
        graph_facts=[],
        trace=Trace(
            understand=TraceUnderstand(raw=question, rewritten=question, entities=[]),
            retrieve=TraceRetrieve(vector_n=0, keyword_n=0, graph_n=0, entity_n=0),
            fuse=TraceFuse(candidate_n=0),
            rerank=TraceRerank(evidence_n=0, confidence=0.0, status="知识库未匹配"),
        ),
    )


@router.post("/chat/ask", response_model=AskResponse)
def ask(body: AskBody) -> AskResponse:
    """三路混合检索问答：实体识别 → 向量+关键词+图谱 → RRF → Rerank → 生成。"""
    s = get_settings()
    question = body.question.strip()

    # 1. 问句理解：实体识别（词表来自图谱已发布节点；LLM 改写随阶段 3）
    vocab = get_graph().all_entities()
    entities = recognize_entities(question, vocab)
    entity_names = [e["name"] for e in entities]

    # 2. 三路并行召回（图谱证据独立，不参与 RRF）
    try:
        q_emb = embed_texts([question])[0]
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e)) from e
    vector_hits = get_store().search(q_emb, top_k=s.semantic_k)
    keyword_hits = get_keyword_index().search(question, top_k=s.keyword_k)
    graph_facts = get_graph().neighbors(entity_names, hop=1)

    # 3. RRF 融合（向量 + 关键词）
    fused = rrf_fuse([vector_hits, keyword_hits], k=s.rrf_k)[: s.fuse_candidate]

    # 4. 精排取最终证据
    ranked = rerank(
        question,
        [f"{c['title']}：{c['text']}" for c in fused],
        top_n=s.rerank_top_n,
    )
    evidence = [
        {**fused[r["index"]], "score": r["score"]} for r in ranked
    ]

    # 5. 置信度兜底（双重条件：文献证据与图谱事实都没有才拒答）
    if not evidence and not graph_facts:
        return _fallback_response(question)

    # 6. 组装 Prompt：图谱事实 + 文献证据
    graph_block = "\n".join(
        f"{f['source']} --{f['relation']}--> {f['target']}" for f in graph_facts
    ) or "（无）"
    evidence_block = "\n\n".join(
        f"[{i + 1}] 《{h['doc_name']}》{h['chapter']}（序号 {h['page_no']}）\n{h['title']}：{h['text']}"
        for i, h in enumerate(evidence)
    )
    template = PROMPT_PATH.read_text(encoding="utf-8")
    prompt = template.format(graph_facts=graph_block, evidence=evidence_block, question=question)

    # 7. 生成
    try:
        answer = chat_completion(system="你是中医药知识助手「本草智问」。", user=prompt)
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e)) from e

    confidence = evidence[0]["score"] if evidence else 0.0
    return AskResponse(
        answer=answer,
        references=[
            Reference(
                chunk_id=h["chunk_id"], title=h["title"], doc_name=h["doc_name"],
                chapter=h["chapter"], page_no=h["page_no"], score=h["score"],
            )
            for h in evidence
        ],
        graph_facts=[GraphFact(**f) for f in graph_facts],
        trace=Trace(
            understand=TraceUnderstand(raw=question, rewritten=question, entities=entity_names),
            retrieve=TraceRetrieve(
                vector_n=len(vector_hits), keyword_n=len(keyword_hits),
                graph_n=len(graph_facts), entity_n=len(entity_names),
            ),
            fuse=TraceFuse(candidate_n=len(fused)),
            rerank=TraceRerank(
                evidence_n=len(evidence), confidence=confidence,
                status="证据充分，正常生成",
            ),
        ),
    )
```

- [ ] **Step 6: 运行确认通过**

Run: `cd backend && .venv/Scripts/python -m pytest -v`
Expected: PASS（全部用例，含既有 health/vector_store/ingestion 用例）

- [ ] **Step 7: 提交**

```bash
git add backend/app/config.py backend/.env.example backend/app/agent/prompts/answer_cn_tcm.txt backend/app/api/chat.py backend/tests/test_chat_api.py
git commit -m "feat(api): three-way hybrid retrieval with RRF+rerank and trace"
```

---

### Task 8: 前端溯源弹窗 + 回答态

**Files:**
- Modify: `web/src/types/chat.ts`
- Modify: `web/src/api/chat.ts`
- Create: `web/src/views/qa/components/TraceDialog.vue`
- Modify: `web/src/views/qa/Chat.vue`
- 验证：`web` 下 `npm run build`

**Interfaces:**
- Consumes: `AskResponse{answer, references, graph_facts, trace}`（Task 7 协议）
- Produces: `TraceDialog` props：`visible`、`trace`、`graphFacts`；Chat.vue 回答卡含图谱事实区 + 证据折叠 + 「检索溯源」按钮

- [ ] **Step 1: 类型扩展** `web/src/types/chat.ts`

```ts
export interface Reference {
  chunk_id: string
  title: string
  doc_name: string
  chapter: string
  page_no: number
  score: number
}

export interface GraphFact {
  source: string
  relation: string
  target: string
  source_type: string
  target_type: string
}

export interface Trace {
  understand: { raw: string; rewritten: string; entities: string[] }
  retrieve: { vector_n: number; keyword_n: number; graph_n: number; entity_n: number }
  fuse: { candidate_n: number; method: string }
  rerank: { evidence_n: number; confidence: number; status: string }
}
```

- [ ] **Step 2: API 类型扩展** `web/src/api/chat.ts`

```ts
import type { GraphFact, Reference, Trace } from '../types/chat'

export interface AskResponse {
  answer: string
  references: Reference[]
  graph_facts: GraphFact[]
  trace: Trace
}
```

（`askQuestion` 实现不变，响应结构由后端补齐。）

- [ ] **Step 3: 溯源弹窗** `web/src/views/qa/components/TraceDialog.vue`

按《前端还原规格》P0-4：5 步流程条（问句理解→多路检索→证据融合→相关性排序→生成回答）+ 步骤详情（原始 vs 改写、4 数字卡、最终证据数 + 状态徽章）。阶段 2 数据一次到位（阶段 3 换 SSE 逐步点亮）。

```vue
<script setup lang="ts">
// 检索溯源弹窗 —— 规格 P0-4。阶段 2：响应一次返回后渲染全部步骤；阶段 3 换 SSE 逐步点亮。
import { computed } from 'vue'
import type { Trace } from '../../../types/chat'

const props = defineProps<{
  visible: boolean
  trace: Trace | null
}>()

const emit = defineEmits<{ (e: 'update:visible', v: boolean): void }>()

const steps = [
  { key: 1, label: '问句理解', desc: '实体识别' },
  { key: 2, label: '多路检索', desc: '向量 / 图谱 / 关键词' },
  { key: 3, label: '证据融合', desc: 'RRF 互惠排名融合' },
  { key: 4, label: '相关性排序', desc: 'BGE-reranker 精排' },
  { key: 5, label: '生成回答', desc: 'SSE 流式输出' },
]

// 阶段 2 数据完整返回：全部步骤视为已完成（阶段 3 按 event 推进）
const doneKeys = computed(() => [1, 2, 3, 4, 5])

function card(record: Record<string, number> | null, key: string, zero: number) {
  return record ? (record[key] ?? zero) : zero
}
</script>

<template>
  <el-dialog
    :model-value="visible"
    :title="`知识检索与图谱溯源`"
    width="640px"
    @update:model-value="(v: boolean) => emit('update:visible', v)"
  >
    <!-- 5 步流程条 -->
    <div class="trace-steps">
      <div
        v-for="s in steps"
        :key="s.key"
        class="step"
        :class="{ done: doneKeys.includes(s.key) }"
      >
        <div class="step-dot">{{ s.key }}</div>
        <div class="step-label">{{ s.label }}</div>
      </div>
    </div>

    <template v-if="trace">
      <!-- 步骤 1：原始 vs 改写 -->
      <div class="section">
        <div class="section-title">① 问句理解</div>
        <div class="pair">
          <div class="pair-item">
            <div class="pair-label">原始问题</div>
            <div class="pair-text">{{ trace.understand.raw }}</div>
          </div>
          <div class="pair-item">
            <div class="pair-label">检索查询（改写）</div>
            <div class="pair-text">{{ trace.understand.rewritten }}</div>
          </div>
        </div>
        <div class="entity-line">
          识别实体：
          <el-tag v-for="e in trace.understand.entities" :key="e" size="small" class="tag">{{ e }}</el-tag>
          <span v-if="!trace.understand.entities.length" class="muted">（未识别）</span>
        </div>
      </div>

      <!-- 步骤 2-3：4 数字卡 -->
      <div class="section">
        <div class="section-title">② 多路检索 · ③ 证据融合</div>
        <div class="num-cards">
          <div class="num-card">
            <div class="num">{{ trace.retrieve.vector_n }}</div>
            <div class="num-label">向量检索（语义）</div>
          </div>
          <div class="num-card">
            <div class="num">{{ trace.retrieve.graph_n }}</div>
            <div class="num-label">中医药图谱（{{ trace.retrieve.entity_n }} 命中实体）</div>
          </div>
          <div class="num-card">
            <div class="num">{{ trace.retrieve.keyword_n }}</div>
            <div class="num-label">关键词检索（BM25）</div>
          </div>
          <div class="num-card">
            <div class="num">{{ trace.fuse.candidate_n }}</div>
            <div class="num-label">证据融合（{{ trace.fuse.method }}）</div>
          </div>
        </div>
      </div>

      <!-- 步骤 4：最终证据 + 状态徽章 -->
      <div class="section">
        <div class="section-title">④ 相关性精排</div>
        <div class="final-line">
          <span class="evidence-n">{{ trace.rerank.evidence_n }} 条证据进入回答上下文</span>
          <span class="badge" :class="trace.rerank.evidence_n ? 'ok' : 'empty'">
            {{ trace.rerank.status }}
          </span>
        </div>
      </div>
    </template>
  </el-dialog>
</template>

<style scoped>
.trace-steps {
  display: flex;
  justify-content: space-between;
  gap: 6px;
  margin-bottom: 18px;
}
.step {
  flex: 1;
  text-align: center;
  opacity: 0.45;
}
.step.done {
  opacity: 1;
}
.step-dot {
  width: 26px;
  height: 26px;
  border-radius: 50%;
  background: #e5e7eb;
  color: #6b7280;
  display: flex;
  align-items: center;
  justify-content: center;
  margin: 0 auto 4px;
  font-size: 13px;
  font-weight: 600;
}
.step.done .step-dot {
  background: #2d6a4f;
  color: #fff;
}
.step-label {
  font-size: 12px;
  color: #1f2937;
}
.section {
  border: 1px solid #e5e7eb;
  border-radius: 8px;
  padding: 12px 14px;
  margin-bottom: 12px;
  background: #fafbfa;
}
.section-title {
  font-size: 13px;
  font-weight: 600;
  color: #1f2937;
  margin-bottom: 8px;
}
.pair {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 10px;
}
.pair-item {
  background: #fff;
  border: 1px solid #e5e7eb;
  border-radius: 6px;
  padding: 8px 10px;
}
.pair-label {
  font-size: 12px;
  color: #6b7280;
  margin-bottom: 4px;
}
.pair-text {
  font-size: 13px;
  color: #1f2937;
}
.entity-line {
  margin-top: 8px;
  font-size: 13px;
  color: #374151;
  display: flex;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;
}
.tag {
  margin-right: 0;
}
.muted {
  color: #9ca3af;
}
.num-cards {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 10px;
}
.num-card {
  background: #fff;
  border: 1px solid #e5e7eb;
  border-radius: 8px;
  text-align: center;
  padding: 12px 4px;
}
.num {
  font-size: 22px;
  font-weight: 600;
  color: #2d6a4f;
  line-height: 1.2;
}
.num-label {
  font-size: 12px;
  color: #6b7280;
  margin-top: 4px;
  line-height: 1.4;
}
.final-line {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
}
.evidence-n {
  font-size: 13px;
  color: #1f2937;
}
.badge {
  font-size: 12px;
  border-radius: 999px;
  padding: 3px 12px;
}
.badge.ok {
  background: #dcfce7;
  color: #166534;
}
.badge.empty {
  background: #fef3c7;
  color: #92400e;
}
</style>
```

- [ ] **Step 4: Chat.vue 集成回答态**

在现有 Chat.vue 的 `<script setup>` 中追加导入与状态：

```ts
import { ref, nextTick } from 'vue'
import { askQuestion } from '../../api/chat'
import type { Reference, Trace } from '../../types/chat'
import TraceDialog from './components/TraceDialog.vue'

interface QA {
  question: string
  answer: string
  references: Reference[]
  graphFacts: { source: string; relation: string; target: string }[]
  trace: Trace | null
}

const traceVisible = ref(false)
const currentTrace = ref<Trace | null>(null)

async function send(q?: string) {
  // ... 既有逻辑保留，push 时补默认字段：
  // messages.value.push({ question, answer: '', references: [], graphFacts: [], trace: null })
  // 成功后：
  // messages.value[messages.value.length - 1] = {
  //   question,
  //   answer: resp.answer,
  //   references: resp.references,
  //   graphFacts: resp.graph_facts,
  //   trace: resp.trace,
  // }
  // currentTrace.value = resp.trace
  // traceVisible.value = true          // 规格 P0-4：提问后默认弹开
}

function openTrace(t: Trace | null) {
  currentTrace.value = t
  traceVisible.value = true
}
```

模板中回答卡替换为（对齐规格 P0-3 结构）：

```vue
<el-card class="a" shadow="never">
  <div class="answer-text">{{ m.answer || '正在生成…' }}</div>

  <!-- 绿色安全提示框（有图谱事实时显示，文案以规格为准） -->
  <div v-if="m.graphFacts.length" class="safety-box">
    注意：以上组成信息严格依据图谱事实，不包含加减变化或现代制剂衍变；实际临床应用须经中医师辨证后使用，不可自行套方。
  </div>

  <!-- 图谱事实区 -->
  <div v-if="m.graphFacts.length" class="graph-facts">
    <div class="gf-title">图谱依据：</div>
    <div v-for="(f, k) in m.graphFacts" :key="k" class="gf-item">
      【图谱事实{{ k + 1 }}】 {{ f.source }} --{{ f.relation }}--> {{ f.target }}
    </div>
  </div>

  <!-- 检索溯源按钮 -->
  <div class="trace-entry">
    <el-button link type="primary" :disabled="!m.trace" @click="openTrace(m.trace)">
      知识检索与图谱溯源
    </el-button>
  </div>

  <el-collapse v-if="m.references.length" class="refs">
    <el-collapse-item :title="`证据来源 (${m.references.length})`">
      <div v-for="(r, j) in m.references" :key="r.chunk_id" class="ref-item">
        <span class="ref-tag graph">文献</span>
        [{{ j + 1 }}] {{ r.title }} —— {{ r.doc_name }} · {{ r.chapter }} · 序号 {{ r.page_no }}
      </div>
    </el-collapse-item>
  </el-collapse>
</el-card>

<p class="disclaimer">本草智问仅提供中医药知识科普，不替代辨证、诊断或个体化处方。如有紧急情况请拨打 120。</p>

<TraceDialog v-model:visible="traceVisible" :trace="currentTrace" />
```

新增样式（颜色取自 `theme.ts` 语义值，禁写死新色值）：

```css
.safety-box {
  margin-top: 12px;
  background: #dcfce7;      /* safetyBg */
  color: #166534;           /* safetyText */
  border-radius: 8px;
  padding: 10px 14px;
  font-size: 13px;
  line-height: 1.6;
}
.graph-facts {
  margin-top: 12px;
  font-size: 13px;
  color: #374151;
}
.gf-title {
  font-weight: 600;
  margin-bottom: 4px;
}
.gf-item {
  padding: 2px 0;
}
.trace-entry {
  margin-top: 10px;
}
.ref-tag {
  display: inline-block;
  font-size: 11px;
  border-radius: 4px;
  padding: 1px 6px;
  margin-right: 6px;
  background: #e6f1ea;
  color: #24553e;
}
```

- [ ] **Step 5: 构建验证**

Run: `cd web && npm run build`
Expected: `vite v5.x build` 成功，无 TypeScript 报错（`web/dist/` 重新生成）

- [ ] **Step 6: 提交**

```bash
git add web/src/types/chat.ts web/src/api/chat.ts web/src/views/qa/components/TraceDialog.vue web/src/views/qa/Chat.vue
git commit -m "feat(web): trace dialog with 5-step retrieval panel and answer card"
```

---

### Task 9: 端到端实测验收（阶段 2 验收标准）

**Files:**
- 无代码改动（仅验收与记录）

**验收脚本（对照合并方案阶段 2 验证项）：**

- [ ] **Step 1: 启动后端**

Run: `cd backend && .venv/Scripts/python -m uvicorn app.main:app --host 127.0.0.1 --port 8000`（后台）
Expected: `Uvicorn running on http://127.0.0.1:8000`

- [ ] **Step 2: 健康 + 图谱确认**

Run: `curl -s http://localhost:8000/health` 与
`curl -s "http://localhost:8000/api/graph/__probe"`（无此路由）——改验证方式：
Run: `cd backend && .venv/Scripts/python -c "from app.graph.neo4j_client import get_graph; g=get_graph(); print(len(g.all_entities())); print(len(g.neighbors(['四君子汤'], hop=1)))"`
Expected: `24` 与 `8`（四君子汤 1 跳边：4 组成 + 主治 + 功效 + 2 禁忌）

- [ ] **Step 3: 实测「四君子汤由哪些中药组成？」**

Run:
```bash
curl -s -X POST http://localhost:8000/api/chat/ask \
  -H "Content-Type: application/json" \
  -d '{"question":"四君子汤由哪些中药组成？"}' | python -m json.tool
```
Expected（抽查关键字段，数值为本次实测真值）：
- `trace.retrieve.graph_n >= 4`（组成边必中，实际 8 条 1 跳）
- `trace.understand.entities` 含 `四君子汤`
- `graph_facts` 含 `{"source":"四君子汤","relation":"组成",...}` 若干条
- `trace.rerank.status == "证据充分，正常生成"`
- `references` 非空且带 doc_name/chapter/page_no

- [ ] **Step 4: 复现命中面板数字**

对比截图「0/22/0」式命中卡：向量 / 图谱 8 / 关键词 / RRF 融合 4 数字卡与本次响应 `trace.retrieve.*` 及 `trace.fuse.candidate_n` 一致（解释道：图谱命中数 = 边条数，非节点数）。

- [ ] **Step 5: 前端浏览器验收**

Run: `cd web && npm run dev`（后台），浏览器打开 http://localhost:5173
对每条建议问题提问，核对：
- 回答卡：正文 → 绿色安全框（有图谱事实时）→ 图谱事实列表 → 「知识检索与图谱溯源」入口 → 证据来源折叠
- 弹窗：5 步流程条全绿、步骤 1 显示原始问题与识别实体、4 数字卡为真实命中数、步骤 4 状态徽章
- 对比类问题（风寒束表 vs 风热犯表）：图谱命中较低、文献证据为主 —— 与方案阶段 2 验证「对比类走文献」一致
- 无关问题（今天天气）：触发兜底文案「知识库中未检索到可靠依据」，弹窗状态为「知识库未匹配」

- [ ] **Step 6: 全量测试回归**

Run: `cd backend && .venv/Scripts/python -m pytest -v`
Expected: 全部 PASS

- [ ] **Step 7: 记录验收结果到 docs**

在 `docs/superpowers/plans/` 同目录追加 `stage2-verification.md`（实测数字：图谱 8 条/向量 N/关键词 N/RRF 候选），作为阶段 6 简历数字来源之一。

- [ ] **Step 8: 提交**

```bash
git add docs/superpowers/plans/stage2-verification.md
git commit -m "docs: stage 2 verification record"
```

---

## Self-Review 检查

- **Spec 覆盖**：BM25（Task 4）、Neo4j 接入 + seed 导入（Task 1/2）、RRF（Task 5）、Rerank（Task 6）、溯源弹窗命中数面板（Task 8）、验证「四君子汤走图谱 / 对比类走文献 / 兜底」（Task 9）—— 合并方案阶段 2 全部条目覆盖。图谱证据不参与 RRF（方案 3.1）在 Task 7 步骤 3 落实。hop 参数支持 1~2（方案 6.5）在 Task 1 `neighbors` 落实，问答默认 hop=1。
- **无占位**：每个任务含完整实现代码与测试代码；Task 8 中 Chat.vue 为增量说明 + 完整模板/样式片段，无 TBD。
- **类型一致**：`rrf_fuse(rank_lists, k, weights)`、`rerank(query, documents, top_n)`、`recognize_entities(question, vocab)`、`neighbors(names, hop)` 前后任务签名一致；`AskResponse` graph_facts/trace 字段 Task 7 定义、Task 8 前端消费一致。