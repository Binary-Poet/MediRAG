# 查询分解 + 定向多跳图谱检索 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让复合意图问题（多实体比较、多症状→证型→方剂、因果机制、多实体鉴别、合病推理）真正"会查"而不是"全查"。当前 `PLAN_MATRIX` 只回答"开哪几路检索"，不回答"问题要不要拆、拆成几个子查询、每个子查询查什么、图谱怎么走"。本计划把查询分解前移到 understand 节点的结构化输出，检索按子查询扇出并对齐精排，图谱从"无向 1~2 跳泛遍历"升级为"按实体类型走定向路径模板"，并修复非法意图降级时丢弃 LLM 全部输出的问题。

**Architecture:** `understand` 一次 LLM 调用的 JSON 输出从 `{rewritten_query, entities, intent}` 扩展为 `{rewritten_query, sub_queries, entities, intent, graph_hop}`；新增第 5 种意图 `compare`（比较/鉴别类，编排形态与 complex 不同——需按实体分取证）。`retrieve` 的执行单位从"路"改为"子查询×路"，线程池扇出，每条命中打 `sub_query` 标签；图谱路按实体类型选择"定向路径模板"（症状→证候→方剂带共现计数、方剂→药物→功效机制链）或回落到无向邻居，但补上关系白名单与端点过滤。`fuse` 的 rerank 从"整句单一 query"改为"按子查询分别打分取 max"，解决对比型问题证据被系统性压分。`context` 对 compare 意图按实体分组组装证据块。降级路径：非法意图不再整包丢弃 LLM 输出；词典兜底的无实体问题改走 concept 检索而非 chitchat 拒答。

**Tech Stack:** Python 3.12、LangGraph、LangChain tools、Neo4j（neo4j driver）、pytest（monkeypatch mock，不依赖真实网络/DB/LLM）。

**背景诊断（已核验，2026-09-17）:**

| # | 问题 | 现状结论 |
|---|---|---|
| 1 | 意图粒度太粗（无比较/因果/鉴别） | 成立，`VALID_INTENTS` 仅 4 种 |
| 2 | 查询不分解 | 向量/BM25 路成立（单 `rewritten_query`）；图谱路已按实体分查 |
| 3 | 图谱只 1 跳 | **已过时**（`graph_hop=2` 已生效）；残留：硬顶 2 跳、agent 路无关系白名单、无向遍历无路径感 |
| 4 | complex 全查≠会查 | 成立；另发现 rerank 用整句对比问题打分，证据被系统性压分 |
| 5 | 非法意图降级丢输出 | 成立且更糟：intent 不合法 → `_parse_understand` 返回 None → LLM 的 rewritten_query/entities 一并丢弃 |
| 6 | graph_facts 绕过置信度（新发现） | `fuse` 图谱豁免 + `safety` 判定使图谱命中后不再拒答；2 跳全开后噪声事实以高可信身份进生成 |
| 7 | reflect 只改写不补实体（新发现） | 第二轮检索图谱路原样复用旧实体，等于白跑 |

**验收用例（7 个边界例子，回归测试必须覆盖）:**

1. 「麻黄汤和桂枝汤在主治和配伍上有什么区别？」→ 拆 2 个子查询，双方剂图谱事实齐，证据按实体分组
2. 「胸痛、心悸、失眠同时出现，可能是什么证型？该用什么方剂？」→ 定向模板 症状-表现→证候-主治→方剂，证候按共现计数排序
3. 「为什么麻黄汤能治太阳伤寒？配伍如何体现解表发汗？」→ 机制链模板 方剂-组成→中药 + 中药-功效，hop 允许 3
4. 「人参、党参、西洋参在补气方面有什么区别？」→ 拆 3 个子查询，rerank 分子查询打分
5. 「如果患者既有太阳表证又有少阳证，用什么方剂？」→ 证候实体定向到方剂
6. 「逍遥散和加味逍遥散有什么区别？加了什么药？」→ 同例 1
7. LLM 输出 `intent="comparison"`（非法）→ 保留 rewritten_query/entities，意图映射为 compare/complex 继续检索；「如何养生」（无实体健康话题）→ 走检索 + 置信度兜底，不直接 chitchat 拒答

## Global Constraints

- **测试不得依赖真实网络 / MySQL / Neo4j / LLM**：沿用现有 monkeypatch + FakeTool / fake driver 模式（参照 `test_retrieve_fuse.py`、`test_graph_client.py`）。
- **不引入自由 ReAct / 完整 query planner**：医疗可控性是既定约束（`tools.py` 模块注释）；分解是一次结构化输出，执行是确定性编排。
- **意图只做"编排模板选择"**：仅新增 `compare` 一种意图；"怎么拆"归 `sub_queries` 字段管，不搞 7 个意图。
- **向后兼容**：`sub_queries` 缺失/为空时一切回落现状（`[rewritten_query]`）；词典兜底路径、既有测试语义不破坏（`test_plan_matrix_routing` 等需同步更新断言）。
- **子查询数量硬上限 3**：prompt 内约定 + 代码截断，防止扇出失控。
- **图谱查询一律参数化 Cypher**；关系白名单沿用 `VALID_RELATIONS` 唯一真源（`sorted()` 保证文本稳定，参照 `graph_api.py:13` 注释）。
- **无向遍历的 hop 上限维持 2**；hop=3 仅对定向路径模板开放（模板本身约束了 fan-out）。
- **trace 事件向后兼容**：新增字段只增不改，前端 `TraceSteps.vue` 未更新前不报错。
- **性能结论必须实测**（用户既有反馈）：改完跑真实问答对比首 token 时延，不接受的退化要回退优化。

---

## 文件结构

| 文件 | 责任 |
|---|---|
| `backend/app/agent/state.py`（修改） | 新增 `sub_queries` 字段 |
| `backend/app/agent/prompts/query_understand.txt`（修改） | 输出 schema 扩展 + compare 意图判定规则 + 泛健康话题不归 chitchat |
| `backend/app/agent/nodes/understand.py`（修改） | 解析 sub_queries/graph_hop；非法意图保留输出只映射意图；词典兜底无实体 → concept |
| `backend/app/agent/nodes/route.py`（修改） | `PLAN_MATRIX` 加 compare 行 |
| `backend/app/agent/nodes/retrieve.py`（修改） | 子查询扇出 + 命中打标 + 图谱路定向模板选择 |
| `backend/app/agent/nodes/fuse.py`（修改） | rerank 按子查询打分取 max；RRF 合并策略 |
| `backend/app/agent/nodes/context.py`（修改） | compare 意图按实体分组组装证据块 |
| `backend/app/agent/nodes/reflect.py`（修改） | 反思允许携带修正后的实体 |
| `backend/app/graph/neo4j_client.py`（修改） | `neighbors` 补关系白名单；新增 `directed_paths` 定向模板查询 |
| `backend/app/agent/tools.py`（修改） | `graph_search` 透传 hop/模板参数；或新增 `graph_path_search` |
| `backend/app/agent/nodes/safety.py`（确认） | compare 非白名单意图无需改（现有判断只排除 chitchat，已兼容） |
| `backend/tests/test_understand.py`（修改） | schema 解析、非法意图降级、兜底三档 |
| `backend/tests/test_retrieve_fuse.py`（修改） | 子查询扇出、打标、rerank 对齐、定向模板选择 |
| `backend/tests/test_graph_client.py`（修改） | directed_paths Cypher、白名单 |
| `backend/tests/test_context.py`（新建或就近） | compare 分组 |
| `web/src/views/qa/components/TraceSteps.vue`（修改，可选） | understand 步骤展示子查询数 |

---

### Task 1: understand 输出 schema 扩展 + 降级修复

**Files:**
- Modify: `backend/app/agent/prompts/query_understand.txt`、`backend/app/agent/nodes/understand.py`、`backend/app/agent/state.py`
- Test: `backend/tests/test_understand.py`

**Interfaces:**
- Produces: `AgentState.sub_queries: list`（`[{"query": str, "entities": [str]}]`）；`VALID_INTENTS = {"relation", "concept", "complex", "compare", "chitchat"}`；`understand` 返回值多 `sub_queries` 键
- Consumes: 现有 `chat_completion` / `recognize_entities`

- [ ] **Step 1: 写失败测试**（沿用 test_understand.py 现有 mock 模式）
  - LLM 返回含 `sub_queries`（2 个）+ `intent="compare"` → 解析成功，`sub_queries` 原样入 state
  - LLM 返回 `intent="comparison"`（非法）+ 合法 rewritten_query/entities → **不再整包丢弃**：intent 映射 `compare`（含比较词）或 `complex`，rewritten_query/entities 保留（例 7 回归）
  - LLM 无 sub_queries 字段 → `sub_queries` 回落 `[{"query": rewritten_query, "entities": entity_names}]`
  - 词典兜底：无实体 → intent `"concept"`（改！原来是 chitchat）；有实体 → complex；「如何养生」类断言走检索（例 7 回归）
  - `sub_queries` 超 3 个 → 截断前 3
  - prompt 文本断言：含 compare 判定规则与「泛健康/养生话题无实体 → concept，非 chitchat」约束
- [ ] **Step 2: 改 prompt**：schema 模板加 `sub_queries` / `graph_hop`；意图规则加 compare（"两个及以上实体的对比/鉴别/加减比较"）；chitchat 定义收紧为"与中医药及健康完全无关"
- [ ] **Step 3: 改 `_parse_understand` / `understand`**：
  - 非法 intent 但其余字段合法 → 构造 parsed，仅 intent 映射（问题文本含"区别/对比/比较/vs"→compare，否则 complex）
  - `sub_queries` 缺失/非法 → 回落单查询包装；条目结构校验（dict + 非空 query）
  - trace 事件加 `sub_query_n`
- [ ] **Step 4: state.py 加字段 + 跑测试**

### Task 2: PLAN_MATRIX 加 compare + 路由兼容

**Files:**
- Modify: `backend/app/agent/nodes/route.py`
- Test: `backend/tests/test_retrieve_fuse.py`（`test_plan_matrix_routing` 更新）

- [ ] **Step 1: 失败测试**：`PLAN_MATRIX["compare"] == ["vector_search", "keyword_search", "graph_search"]`；`route(compare) == "retrieve"`
- [ ] **Step 2: 加一行矩阵**。`route`/`reflect_edge`/`safety` 的 chitchat 判断天然兼容，确认无遗漏（safety 只在 `intent=="chitchat"` 时直拒）

### Task 3: retrieve 子查询扇出 + 命中打标

**Files:**
- Modify: `backend/app/agent/nodes/retrieve.py`
- Test: `backend/tests/test_retrieve_fuse.py`

**Interfaces:**
- Consumes: `state["sub_queries"]`（Task 1 产出）；`TOOLS` 三工具签名不变
- Produces: `vector_hits`/`keyword_hits` 每条附 `sub_query: int`（下标）；`graph_facts` 每条附 `entity`（来源实体）；trace `retrieve` 事件加 `sub_query_n`

- [ ] **Step 1: 失败测试**
  - `sub_queries=[{q1,[麻黄汤]}, {q2,[桂枝汤]}]` + complex → vector_search 被调 2 次（各子查询一次），keyword 同理；返回 hits 分别带 `sub_query: 0/1`（例 1/4 回归）
  - `sub_queries` 为空 → 回落现状（单查询、无标签），`test_retrieve_invokes_tools_per_plan` 既有断言不破
  - 子查询 `entities` 非空时图谱按子查询实体查询（与全局 entity_names 取并集去重）
- [ ] **Step 2: 实现**：外层 `queries = state.get("sub_queries") or [{query: rewritten_query, entities: entity_names}]`；线程池任务单位改为 (sub_idx × tool)；合并时打标去重（同 chunk_id 不同子查询保留两条，供 Task 4 分数对齐）
- [ ] **Step 3: 性能实测**：子查询×路并行后对比改动前"发送→首个 token"时延（用户既有要求：性能结论实测）

### Task 4: fuse 按子查询对齐精排

**Files:**
- Modify: `backend/app/agent/nodes/fuse.py`
- Test: `backend/tests/test_retrieve_fuse.py`

- [ ] **Step 1: 失败测试**
  - mock rerank 记录收到的 query 序列：2 个子查询 → rerank 被调 2 次，每次一个子查询文本；每条证据 score = 各子查询得分的 max（例 4 回归：讲党参的切片按"党参补气"子查询打分，不再被整句压分）
  - 单子查询 → 行为等同现状（既有 `test_fuse_rrf_and_rerank` 不破）
  - RRF：每子查询的 vector/keyword 各自 RRF 后按 chunk_id 合并取 max rrf_score
- [ ] **Step 2: 实现**：rerank 调用次数 = 子查询数（上限 3，成本可控）；evidence 条目附 `matched_queries: [sub_idx...]` 供 trace 与 Task 6 分组

### Task 5: 图谱——关系白名单 + 端点过滤

**Files:**
- Modify: `backend/app/graph/neo4j_client.py`
- Test: `backend/tests/test_graph_client.py`

- [ ] **Step 1: 失败测试**：`neighbors` 生成的 Cypher 含 `ALL(r IN relationships(p) WHERE type(r) IN [...VALID_RELATIONS])`（fake driver 断言 Cypher 文本）；与 `graph_api.py` 白名单一致
- [ ] **Step 2: 实现**：把 `_RELATIONS_LITERAL` 构造挪进 `neo4j_client`（或共享 helper），agent 路与浏览路同源
- [ ] **Step 3: 失败测试**：retrieve 图谱路对 facts 过滤——保留端点（source/target）∈ 查询实体集合的事实，其余丢弃并计数入 trace（防 2 跳噪声走强证据豁免，问题 #6 配套）

### Task 6: 图谱——定向路径模板（症状→证候→方剂 等）

**Files:**
- Modify: `backend/app/graph/neo4j_client.py`（新增 `directed_paths`）、`backend/app/agent/tools.py`、`backend/app/agent/nodes/retrieve.py`
- Test: `backend/tests/test_graph_client.py`、`backend/tests/test_retrieve_fuse.py`

**Interfaces:**
- Produces: `GraphClient.directed_paths(template: str, params: dict)`，模板枚举：
  - `symptom_to_formula`：`(s:症状)-[:表现]-(d:证候)-[:主治]-(f:方剂)`，`hit = count(DISTINCT s)`，`hit >= 2` 时降序（多症状交集即相关性，例 2/5）
  - `formula_mechanism`：`(f:方剂)-[:组成]->(h:中药)-[:功效*0..1]->(e)`，允许第 3 层（例 3/6 的配伍机制链）
- 模板选择的确定性规则（retrieve 内，不走 LLM）：实体类型全为 `症状` 且意图 complex/compare → symptom_to_formula；实体类型为 `方剂` 且 rewritten_query 含"为什么/机制/配伍/如何"→ formula_mechanism；否则回落无向 neighbors

- [ ] **Step 1: 失败测试**
  - `directed_paths("symptom_to_formula", symptoms=["胸痛","心悸","失眠"])` 生成含 `[:表现]`/`[:主治]` 方向约束与 `count(DISTINCT s)` 的参数化 Cypher（fake driver 断言）
  - retrieve：3 个症状实体 + complex → 走 symptom_to_formula，返回事实带 `hit` 字段；单方剂 + "为什么" → 走 formula_mechanism；`太阳表证`/`少阳证`（证候类型）→ 证候-主治→方剂 2 跳定向
  - 回落路径：类型混杂实体 → 无向 neighbors（现状），断言白名单生效
- [ ] **Step 2: 实现 GraphClient.directed_paths**（模板 Cypher 字典，参数化，只查已发布）
- [ ] **Step 3: retrieve 接线**：模板命中时 facts 打 `path_template` 标签；未命中回落
- [ ] **Step 4: 真实数据实测**：用例 2/3/5 各跑一次真实问答，确认图谱事实里出现期望链路（用户要求：结论实测，Neo4j 起容器跑）

### Task 7: compare 证据分组 + reflect 补实体

**Files:**
- Modify: `backend/app/agent/nodes/context.py`、`backend/app/agent/nodes/reflect.py`
- Test: `backend/tests/test_context.py`（新建）、`backend/tests/test_workflow.py`

- [ ] **Step 1: 失败测试**
  - context：intent=compare + 2 实体 → 证据块按实体分组（`【麻黄汤】…【桂枝汤】…【图谱共同事实】`）；非 compare → 现状平铺不破
  - reflect：LLM 输出改写查询 + 修正实体（JSON 或约定格式）→ state 的 entities/entity_names 更新，第二轮图谱路用新实体
- [ ] **Step 2: 实现**：context 按 evidence 的 `sub_query` 标签/实体交集分组；reflect prompt 约定输出 `改写查询 ||| 实体1,实体2` 或轻量 JSON（与 understand 解析器共用容错）

### Task 8: 7 例回归 + trace/前端展示

**Files:**
- Test: `backend/tests/test_edge_cases_e2e.py`（新建，全 mock）
- Modify（可选）: `web/src/views/qa/components/TraceSteps.vue`

- [ ] **Step 1: 7 个验收用例编成参数化测试**（mock LLM understand 输出 + FakeTool，断言：sub_queries 数、工具调用序列、证据分组、图谱模板选择、降级路径）
- [ ] **Step 2: 全量 `pytest backend/tests` 绿**
- [ ] **Step 3: trace 的 understand 事件带 sub_queries 摘要；TraceSteps 悬浮展示子查询列表（可选，演示可追溯性加分）**
- [ ] **Step 4: 真实环境端到端实测**：7 例 + 「如何养生」逐条跑真实服务，记录回答与 trace 截图入 `docs/verification/`（沿用仓库验收记录惯例），性能对比表（首 token 时延 改前/改后）

---

## 任务顺序与依赖

```
Task 1 (understand schema) ──→ Task 2 (矩阵) ──→ Task 3 (扇出) ──→ Task 4 (对齐精排)
                                                    │
Task 5 (白名单+过滤) ──→ Task 6 (定向模板) ←────────┘
Task 7 (分组+reflect) 依赖 Task 3/4 的打标
Task 8 收尾回归
```

Task 5 可与 Task 1-4 并行。每 Task 独立可验证、可单独提交。

## 明确不做

- ❌ 自由 ReAct / query planner / 意图拆成 7 种
- ❌ 无向遍历 hop 放开到 3（只对模板路径放开）
- ❌ 图谱子查询 embedding 检索（图谱按实体名精确匹配，与现状一致）
