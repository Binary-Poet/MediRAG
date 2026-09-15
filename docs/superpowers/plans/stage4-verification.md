# 阶段 4 知识库管理 + 图谱审核闭环 端到端实测验收记录

- 日期：**2026-09-15**
- 环境：Windows 11 / Python 3.12 / Vue 3 + Vite 5.4.21 / MySQL 容器 `medirag-mysql`（宿主 3307）/ Neo4j 容器 `medirag-neo4j`（宿主 7687）/ DeepSeek 生成与抽取 + SiliconFlow embedding/rerank **真实调用**
- 被测对象：commit `1dd2ae7` 工作树（阶段 4 全部任务实现完成态），**本轮未改任何业务代码**
- 隔离前置状态：MySQL `document` 表空；Neo4j **33 节点 / 32 边**，全部 `status='已发布'`；向量库无新上传切片

> **结论先行：DONE_WITH_CONCERNS。** 五项验收全部执行完毕：上传→就绪→可检索闭环 ✓、抽取→候选→审核→发布闭环 ✓、前端门禁与全量回归 ✓（**123 passed**）。但第 3 项「候选不污染问答」**实测发现真实泄漏**——候选边在**两端节点均为已发布**时会进入问答图谱事实（§3）；另有审核发布产生的新节点缺 `type` 属性（§6-C2）。二者均为图谱侧数据契约问题，**按规程未改代码，仅归档证据**。

---

## 0. 实测口径

| 项 | 值 |
|---|---|
| 后端 | `cd backend && .venv/Scripts/python -m uvicorn app.main:app --host 127.0.0.1 --port 8000`（startup 执行 `init_db()` 建表） |
| 客户端 | httpx（规避 Windows Git Bash 下 curl 中文 JSON 的 body 解析问题） |
| 上传语料 | `验收语料.md`（topic=内科，含四君子汤/归脾汤/**补中益气汤**）+ `验收PDF.pdf`（ASCII 最小 PDF，验证 PDF 解析路径） |
| 抽取语料 | `补中益气汤由黄芪、人参、白术、陈皮、升麻、柴胡、当归、炙甘草组成，功用补中益气、升阳举陷，主治脾胃气虚下陷证。风热犯表可见口渴。` |
| 真实消耗 | 抽取 LLM ×1（2.39s）；问答流式 ×10；embedding（两次上传入库） |

**语料设计说明（关键）**：既有 seed 图谱已含 `四君子汤/归脾汤/酸枣仁汤` 三方剂及其组成、主治、功效、禁忌共 32 条已发布边。若直接照计划示例抽取「四君子汤由人参…组成」，其边已存在且为已发布，`save_candidates` 的 `ON MATCH` 语义会**保留已发布**，候选列表不会出现新条，无法演示审核闭环。故本轮改用 seed 图谱**不存在**的方剂「补中益气汤」（候选边两端至少一端为新节点）作为闭环载体，并另设 `风热犯表--表现-->口渴`（两端节点均已在图谱中且已发布）作为**隔离探针**。

---

## 1. 验收一：上传 → 就绪 → 可检索闭环 —— ✓ 通过

### 1.1 上传与状态机（真实 multipart）

| 步骤 | 请求 | 结果 |
|---|---|---|
| 上传 md | `POST /api/documents`（files=`验收语料.md`，data=`topic=内科`） | **200**，`{id:1, name:"验收语料.md", status:"上传中"}` |
| 状态轮询 | `GET /api/documents/1/parse-status` ×3（1s 间隔） | **`status=就绪`, `chunk_count=1`, `error_message=""`** |
| 列表统计 | `GET /api/documents` | `total=1, total_chunks=1`，`topic=内科` |
| 上传 PDF | `POST /api/documents`（files=`验收PDF.pdf`，`application/pdf`） | **200**，`{id:2}` → 轮询 3 次 → **`status=就绪`, `chunk_count=1`, `file_type=pdf`** |
| 列表统计（PDF 后） | `GET /api/documents` | `total=2, total_chunks=2` |

负路径（协议校验）：

| 场景 | 结果 |
|---|---|
| 缺 `topic` | **422** `知识主题必选，取值：内科/外科/儿科/妇科/情志脑病/筋骨伤科/皮肤病证/五官病证`（8 类枚举与规格逐字一致） |
| 不支持格式 `.exe` | **400** `不支持的文件格式：.exe` |

结论：多格式（md + pdf）解析 → 切片 → 向量化 → BM25 重建 → 状态机 `上传中 → 处理中 → 就绪` 全链路真实跑通，`chunk_count ≥ 1` 达标。

### 1.2 新文档可被问答检索（入库→检索闭环）

新上传文档含 seed 语料**完全没有**的「补中益气汤」，据此可做**决定性**判定：

| 问题 | references（doc_name） | 回答 | 判定 |
|---|---|---|---|
| 归脾汤主治什么？ | 中药方剂学基础 / 中医诊断学基础 / **验收语料.md** / 中药方剂学基础 / 中药学基础 | 「归脾汤主治**心脾两虚**证 [1][3]…」 | ✓ 新文档进入 top-5 证据 |
| 补中益气汤主治什么？ | **验收语料.md（第 1 位）** / 中药方剂学基础 / 中药学基础 / 中药方剂学基础 / 《金匮要略》虚劳篇 | 「补中益气汤主治**脾胃气虚下陷证** [1]。」 | ✓✓ 答案只能来自新上传文档 |

`补中益气汤` 在 seed 语料与 seed 图谱中均不存在，而回答准确命中且 references 首位即 `验收语料.md` —— **入库 → 向量+关键词召回 → RRF → rerank → 生成** 闭环成立。

---

## 2. 验收二：抽取 → 候选 → 审核 → 发布闭环 —— ✓ 通过

### 2.1 真实 LLM 抽取

```
extract_triples(EXTRACT_TEXT)  →  2.39s, 12 条三元组（全部通过 relation/type 白名单校验）
save_candidates(triples, source_doc="验收语料.md")  →  返回 12（写入边数）
```

抽取结果（12 条，全部 relation ∈ {组成,主治,功效}、type ∈ {方剂,中药,证候,功效}）：

```
补中益气汤 -组成-> 黄芪 / 人参 / 白术 / 陈皮 / 升麻 / 柴胡 / 当归 / 炙甘草   （8）
补中益气汤 -功效-> 补中益气 / 升阳举陷                                   （2）
补中益气汤 -主治-> 脾胃气虚下陷证                                        （1）
风热犯表   -表现-> 口渴                                                （1，隔离探针，见 §3）
```

### 2.2 候选列表（发布前）

`GET /api/graph/candidates` → **edges=12, nodes=7**，`source_doc` 全部为 `验收语料.md`

- 候选节点：`补中益气汤 / 陈皮 / 升麻 / 柴胡 / 补中益气 / 升阳举陷 / 脾胃气虚下陷证`
- 候选边状态经直连 Neo4j 复核：`r.status='候选'`（如 `风热犯表-表现->口渴`：edge_status=**候选**, source_doc=验收语料.md）

### 2.3 审核流转（approve / reject）

| 操作 | 请求 | 结果 |
|---|---|---|
| 发布边 | `POST /api/graph/candidates/approve` `{kind:edge, source:补中益气汤, relation:组成, target:黄芪}` | **200** `{approved:"edge",…}` |
| 发布节点 | `POST /api/graph/candidates/approve` `{kind:node, name:补中益气汤}` | **200** `{approved:"node",…}` |
| 驳回边 | `POST /api/graph/candidates/reject` `{kind:edge, source:补中益气汤, relation:组成, target:人参}` | **200** `{rejected:"edge",…}` |
| 驳回被引用的节点 | `POST /api/graph/candidates/reject` `{kind:node, name:补中益气汤}` | **409** `该实体被已发布关系引用，请先驳回相关关系` ✓ 守卫生效 |
| 驳回纯候选节点 | `POST /api/graph/candidates/reject` `{kind:node, name:升麻}` | **200**；候选边 10 → **9**，节点与其余候选边一并消失 |
| 非法 kind | `POST /api/graph/candidates/approve` `{kind:bogus}` | **422** `kind 取值为 node|edge` |

复核（`GET /api/graph/candidates`）：

| 判定项 | 结果 |
|---|---|
| 已发布边仍出现在候选中？ | **否**（`approved_still_in_candidates=false`） |
| 已驳回边仍出现在候选中？ | **否**（`rejected_still_in_candidates=false`；Neo4j `count(r)=0`，边已删除） |
| 候选边数（上表全部操作后） | 12 → **9**（发布 1 + 驳回 1 + 驳回纯候选节点连带删 1） |

直连 Neo4j 复核状态落库：

```
已发布边   补中益气汤 -组成-> 黄芪 :  r.status=已发布, a.status=已发布, b.status=已发布   ✓
已驳回边   补中益气汤 -组成-> 人参 :  count(r)=0（已删除）                              ✓
已发布节点 补中益气汤             :  n.status=已发布                                     ✓
```

### 2.4 发布后图谱页可见

- `GET /api/graph/search?entity=补中益气汤` → `[{name:补中益气汤, status:已发布}]` ✓
- `GET /api/graph/neighbors?name=补中益气汤` → 13 节点 / 16 边，含 `补中益气汤-组成->黄芪(已发布)` ✓

### 2.5 已发布知识不被降级（反向安全）

对**已存在且已发布**的三元组重复执行 `save_candidates`（模拟重复抽取）：

| 判定项 | 结果 |
|---|---|
| `四君子汤-组成->人参` 复核 status | **已发布**（未被降级为候选） |
| 候选边数变化 | 10 → **10**（未新增候选） |

即 `extractor.py` 的 `ON MATCH SET … CASE WHEN n.status='已发布' THEN '已发布' ELSE '候选' END` 语义正确，**重复抽取不会把已发布知识打回候选**。

---

## 3. 验收三：候选不污染问答（隔离验证）—— ✗ **实测发现真实泄漏**

方案 6.5 要求「问答链路只查 `已发布`」。本轮用两个问题分别验证**节点门**与**边门**：

| 时点 | Q_new「补中益气汤由哪些中药组成？」graph_n | Q_leak「风热犯表有哪些表现？」graph_n |
|---|---|---|
| **T0** 抽取前 | 0 | **1** |
| **T1** 抽取后、审核前（候选待审） | **0** ✓ | **2**  **泄漏** |
| **T2** 发布后 | **4** ✓（`补中益气汤-组成->白术/炙甘草/黄芪/当归`） | 2 |

### 3.1 节点门有效（✓）

`补中益气汤` 作为**新节点**处于 `候选` 时，其全部候选边在 T1 均**未**进入问答图谱事实（`graph_n` 保持 0）；发布节点 + 一条组成边后，T2 的 `graph_n` 变为 **4**。可见**新实体的候选知识不污染问答**。

### 3.2 边门缺失（✗ 泄漏，确认）

隔离探针 `风热犯表 --表现--> 口渴`：**两端节点 `风热犯表` / `口渴` 均已在 seed 图谱中且为 `已发布`**，而该边是候选。

- T0（抽取前）：`graph_n=1`，事实 = `风热犯表-表现->发热重微恶风`
- **T1（抽取后、发布前）：`graph_n=2`**，事实 = **`风热犯表-表现->口渴`** + `风热犯表-表现->发热重微恶风`
- 直连 Neo4j 复核该边：`r.status = 候选`，`source_doc = 验收语料.md`，`a.status = 已发布`，`b.status = 已发布`

即**一条未经人工审核的候选边，在发布前已进入问答图谱事实并参与生成**（T1 回答「风热犯表的表现有：发热重、微恶风 [1]，**口渴** [1]」）。

**根因**（`backend/app/graph/neo4j_client.py:43-50`，`GraphClient.neighbors`）：

```cypher
MATCH p = (a)-[*1..{hop}]-(b)
WHERE a.name IN $names AND a.status = '已发布' AND b.status = '已发布'
UNWIND relationships(p) AS r
RETURN DISTINCT startNode(r).name AS source, type(r) AS relation, endNode(r).name AS target, …
```

**只过滤端点节点状态，完全没有 `r.status` 条件**。因此：

- 候选三元组**引入了新节点** → 新节点为 `候选` → 被端点过滤拦住（§3.1 成立）；
- 候选三元组**两端都是既有已发布节点** → 端点过滤全部通过 → 候选边直接进入问答（§3.2 泄漏）。

**影响**：违反方案 6.5 与计划 Global Constraint「问答链路只查 `已发布`，禁止放开」。LLM 从文档抽出的、未经人工审核的关系，只要落在两个既有实体之间，就会立刻影响回答（本例中回答确实多出了「口渴」这一图谱事实）。

---

## 4. 验收四：前端与门禁 —— ✓ 通过

| 项 | 命令 | 结果 |
|---|---|---|
| 类型检查 | `cd web && npm run type-check`（vue-tsc --noEmit） | **exit 0，零错误** |
| 生产构建 | `npm run build`（vite） | **exit 0**，`✓ built in 20.70s`（仅 chunk >500kB 警告，非错误） |
| Dev server | `npm run dev` | `ready in 833ms`；5173 被占用时自动改用 **5174** |
| 页面可达 | `curl 127.0.0.1:5174/`、`/library`、`/graph` | 全部 **200** |
| 全量回归 | `cd backend && .venv/Scripts/python -m pytest -q` | **123 passed, 11 warnings in 5.57s** |

> 说明：5173 端口在本任务开始前**已有**一个 MediRAG vite dev server 在运行（node PID 42424，`curl → 200`），非本任务启动，故未停用（浏览器视觉验收由控制器另行执行）。本任务新起的 dev server 落在 **5174**，验证 200 后已停止。

后端运行期日志（`uvicorn`）全程**无 500、无 Traceback**；唯二非 200 为上文主动构造的 `409`（节点被已发布关系引用）与 `422`（非法 kind）协议校验，均符合预期。

---

## 5. 结论（对照《MediRAG-合并改造方案》阶段 4「验证」小节）

方案原文验证口径：**「上传 PDF 后状态变就绪、可被检索；抽取的三元组审核后出现在图谱页。」**

| 验收项 | 结果 | 证据 |
|---|---|---|
| 上传 PDF 后状态变就绪 | **✓** | §1.1：`验收PDF.pdf` → `status=就绪, chunk_count=1`（3 次轮询）；另测 md 同样就绪 |
| 上传后可被检索 | **✓** | §1.2：`references` 首位命中 `验收语料.md`；问答回答含新文档独有事实「脾胃气虚下陷证」 |
| 抽取的三元组审核后出现在图谱页 | **✓** | §2：12 条候选 → approve 边+节点 → `search`/`neighbors` 返回 `status=已发布`；驳回边从候选与图谱中消失 |
| （计划增补）候选不污染问答 | **✗ 泄漏** | §3：候选边（两端节点已发布）在发布前即进入问答图谱事实，`graph_n` 1→2 |
| （计划增补）前端门禁 + 全量回归 | **✓** | §4：type-check / build 零错误；pytest **123 passed** |

**总判定：DONE_WITH_CONCERNS。** 阶段 4 的两条方案级验证口径全部通过，上传/检索/审核闭环真实成立，门禁与回归全绿；但**候选隔离只在「新节点」路径成立，在「既有节点之间的新关系」路径上失效**（§3.2），属图谱查询契约缺陷，需在后续修复。

---

## 6. 缺陷与偏差清单（仅归档，本轮未改代码）

| 编号 | 级别 | 问题 | 证据位置 | 根因 |
|---|---|---|---|---|
| **C1** | **高（阻断隔离语义）** | **候选边污染问答**：候选边在两端节点均为已发布时进入问答图谱事实，未经审核即参与生成 | §3.2；`graph_n` 1→2，事实含 `风热犯表-表现->口渴`（`r.status=候选`） | `backend/app/graph/neo4j_client.py:45` `neighbors()` 的 `WHERE` 只判 `a.status`/`b.status`，**缺 `r.status='已发布'`** |
| **C2** | 中 | **审核发布产生的新节点缺 `type` 属性**。`补中益气汤` 的 Neo4j `keys(n) = [status, source, name]`，`type=null`（label 正确为 `方剂`） | §6 附：`GET /api/graph/search?type=方剂` 只返回 seed 三方剂，**不含** `补中益气汤`；`search`/`entities`/`neighbors` 对新节点返回 `type`/`category` 均为 `null` | `backend/app/graph/extractor.py:63-65` `save_candidates` 只 `MERGE (n:\`{label}\` …)` 设 Neo4j **标签**，未写 `n.type` 属性；seed `importer.py:29` 则写 `n.type` |
| **C3** | 中 | **`neighbors` 的 link `status` 取的是「源节点状态」而非「边状态」**；且该查询**完全不过滤边状态**（候选边无差别出现在图谱浏览图中） | §2.4：`补中益气汤-组成->陈皮` 的 link `status=已发布`，而该边实为 `r.status=候选`（目标节点 `陈皮` 亦为 `候选`） | `backend/app/graph/graph_api.py:51` `links.append({…, "status": r["status"]})`，而 `r["status"]` 即 `graph_api.py:41` 的 `startNode(r).status`；同查询（`graph_api.py:37-41`）无 `r.status` 条件。**注**：`nodes[].status` 是对的（`graph_api.py:47-49` 分别取 `startNode`/`endNode` 各自的 status，第 41 行的 `target_status` 即为此用） |

**C2 影响面（前端）**：`web/src/views/graph/GraphExplore.vue` 用 `TYPE_COLOR[e.type]` 给节点着色、用 `TYPES.indexOf(n.category)` 取 ECharts 分类色。新发布节点的 `type`/`category` 为 `null` → 颜色回退灰、分类为 `-1`，即**「6 类节点色」对审核发布产生的新节点不生效**（seed 节点不受影响）。因控制器将另行执行浏览器视觉验收，此处一并记录。

**C3 影响面**：`links[].status` 目前前端未参与渲染（`GraphExplore.vue` 仅用 `nodes[].status` 决定候选虚线边框），故**视觉**影响有限；但接口契约上有两点问题——（a）无法由 `neighbors` 取得「边的真实状态」；（b）**候选边会无差别出现在图谱浏览图中**（`neighbors` 无 `r.status` 过滤，与 C1 同源），即未审核知识在浏览图里已可见。

**有利偏差（记录）**：`save_candidates` 的 `ON MATCH` 语义确保重复抽取**不会把已发布知识降级**（§2.5 实测），方向安全。

---

## 7. 本轮遗留运行态（供控制器浏览器验收复用）

实测数据保留在库中（未清理），以便控制器执行浏览器视觉验收时「典籍知识库页 / 候选审核 Tab」有真实数据：

| 存储 | 遗留内容 |
|---|---|
| MySQL `document` | 2 条：`验收语料.md`（内科，就绪，1 切片）、`验收PDF.pdf`（内科，就绪，1 切片） |
| Neo4j 节点 | **39**（34 已发布 + **5 候选**：`陈皮 / 柴胡 / 补中益气 / 升阳举陷 / 脾胃气虚下陷证`） |
| Neo4j 边 | **42**（33 已发布 + **9 候选**） |
| 候选审核 Tab 可见 | 9 条待审边 + 5 个待审实体（其中 1 条为 §3.2 的泄漏探针边 `风热犯表-表现->口渴`） |
| 向量库 | `data/vectorstore/index.json` 已含 2 条新文档切片（`验收语料.md#0000`、`验收PDF.pdf#0000`） |

> 注意：`data/vectorstore/index.json` 为**已被 git 跟踪**的文件，本轮因上传实测被修改（工作树 `M`）；`data/uploads/` 为运行数据（`.gitignore:20` 已忽略）。本记录提交**仅含本文件**，不包含上述运行数据改动。

## 8. 服务与端口

| 服务 | 状态 |
|---|---|
| 后端 8000 | 已启动并实测 → **已停止**（端口已释放） |
| dev server 5174（本轮新起） | 已启动并实测 200 → **已停止**（端口已释放） |
| dev server 5173 | **非本轮启动**（任务开始前即存在），未停用 |
| MySQL 3307 / Neo4j 7687 | 任务前后均在运行，未变更 |

实测脚本与原始输出（本地留档，未提交）：`C:/tmp/accept_a.py|json`、`accept_b.py|json`、`accept_c.py|json`、`accept_d.json`、`accept_pdf.py|json`、`final_state.json`、`medirag_backend*.log`、`vite_dev.log`。

---

## 9. 范围收窄记录

规格 P0-6「典籍知识库」登记的操作列为 **「详情 · 下载 · 重命名」** 三项；阶段 4 本阶段仅实现 **「删除」** 一项。原因与递延安排如下：

1. **详情 / 下载 / 重命名**依赖规格 P2 属性（更完整的文档元数据与检索入口）与《合并改造方案》阶段 5 的页面还原方案，本阶段不实现，避免在库表与接口上先行固化契约。
2. 三项操作按规格与合并方案**阶段 5 递延**，在阶段 5「逐屏还原」时补齐，届时与本阶段已落地的列表 / 上传 / 状态轮询 / 删除一并成为完整的知识库管理界面。
3. 本阶段的验收口径（§5）不含上述三项，故不影响阶段 4 的通过判定。