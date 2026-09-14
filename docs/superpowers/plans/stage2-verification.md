# 阶段 2 端到端实测验收记录

> 日期：2026-09-14
> 范围：API 侧全部实测（Step 1-4 + 6）；浏览器视觉验收另由控制器执行。
> 结论：核心路径（图谱问答 / 对比类走文献）全部通过；发现 1 处「无关问题兜底」语义缺陷（见「疑虑」）。

## 运行前提

- 后端：`backend/.env` 已配置真实 `DEEPSEEK_API_KEY` 与 `SILICONFLOW_API_KEY`；Neo4j 容器 `medirag-neo4j`（bolt://localhost:7687）、`medirag-mysql` 运行中。
- 向量库：`data/vectorstore/index.json` 已含 **11 条** 1024 维 bge-m3 切片；seed 图谱 **33 节点 / 32 边**已导入。
- 数据事实更正（Ruling R3）：`all_entities()` 返回 **33**（非计划文所写 24）；四君子汤 1 跳边为 **8**。

## Step 1-2：后端启动 + 健康 + 图谱确认

```bash
cd backend && .venv/Scripts/python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

- 启动日志：`Uvicorn running on http://127.0.0.1:8000` ✓
- `GET /health` → `{"status":"ok","app":"MediRAG","env":"dev"}` ✓
- 图谱探针：

```bash
.venv/Scripts/python -c "from app.graph.neo4j_client import get_graph; g=get_graph(); print(len(g.all_entities())); print(len(g.neighbors(['四君子汤'], hop=1)))"
# 33
# 8
```

`all_entities()` = 33 ✓（与 Ruling R3 一致）；四君子汤 1 跳边 = 8 ✓（4 组成 + 主治 + 功效 + 2 禁忌）。

## Step 3：真实问答「四君子汤由哪些中药组成？」

`POST /api/chat/ask`（200），关键字段实测值：

| 字段 | 实测值 | 验收预期 | 结果 |
|---|---|---|---|
| `answer` | 「四君子汤由人参、白术、茯苓、炙甘草四味药组成 [1]。」 | 含人参等组成 | ✓ |
| `trace.understand.entities` | `["四君子汤"]` | 含「四君子汤」 | ✓ |
| `trace.retrieve.graph_n` | **8** | ≥ 4（实际 8 条 1 跳边） | ✓ |
| `trace.retrieve.vector_n` | 11 | — | 记实 |
| `trace.retrieve.keyword_n` | 5 | — | 记实 |
| `trace.fuse.candidate_n` | 11 | — | 记实 |
| `trace.rerank.evidence_n` | 5 | — | 记实 |
| `trace.rerank.confidence` | 0.9967 | — | 记实 |
| `trace.rerank.status` | 「证据充分，正常生成」 | 同 | ✓ |
| `graph_facts` | 8 条（4 组成 + 主治 + 功效 + 2 禁忌），均含 `{"source":"四君子汤","relation":"组成",...}` | 含组成边 | ✓ |
| `references` | 5 条非空，带 `doc_name`/`chapter`/`page_no`；top = 中药方剂学基础#0001《四君子汤》 | 非空 | ✓ |

## Step 4：命中面板数字（溯源弹窗 4 数字卡）

弹窗 4 卡取 `trace.retrieve.vector_n / graph_n / keyword_n` 与 `trace.fuse.candidate_n`。本次三类问题实测数字：

| 问题 | 向量（语义） | 图谱（N 命中实体） | 关键词（BM25） | 证据融合（RRF） | 精排证据 | 状态 |
|---|---|---|---|---|---|---|
| 四君子汤由哪些中药组成？ | 11 | **8**（1 实体） | 5 | 11 | 5 | 证据充分，正常生成 |
| 风寒束表与风热犯表有什么区别？ | 11 | 1（2 实体） | 4 | 11 | 5 | 证据充分，正常生成 |
| 今天天气怎么样 | 11 | 0（0 实体） | 0 | 11 | 5 | ⚠️ 证据充分，正常生成（见疑虑） |

> 说明：向量路 `top_k=20` 大于语料 11 条，故语义召回恒为 11；图谱命中数 = **边条数**（非节点数）——四君子汤 8 条 1 跳边即面板显示 8。

## 对比类问题验证（风寒束表 vs 风热犯表）

- `answer`：正确区分两证（恶寒重/发热轻/无汗/清涕/苔薄白 vs 发热重/恶风轻/有汗不畅/咽痛口渴/苔薄黄），标注 `[1]`，并提及图谱事实「风热犯表可见"发热重微恶风"」 ✓
- `entities` = `["风寒束表","风热犯表"]`（2 个）；`graph_n` = 1（仅风热犯表存在「表现」边，风寒束表无出边）；`confidence` = 0.9994。
- 结论：图谱命中较低、**文献证据为主** —— 与方案「对比类走文献」一致 ✓。

## 无关问题验证（今天天气怎么样）

- `answer`：返回「知识库中未检索到可靠依据。……无法提供天气信息。」（LLM 依据 Prompt 拒绝，文案达标）。
- 但见「疑虑」：`trace.rerank.status` 为「证据充分，正常生成」而非「知识库未匹配」，`references` 非空（5 条 ~0.003 低分噪声）。

## Step 6：全量测试回归

```bash
cd backend && .venv/Scripts/python -m pytest -v
# 34 passed, 2 warnings in 1.42s
```

后端 34 测试全绿 ✓。

## 前端（HTTP 侧，浏览器视觉验收由控制器补做）

- `cd web && npm run dev` 启动 Vite 后 `curl -w "%{http_code}" http://localhost:5173` → **200** ✓
- `npm run build` → ✓ built in 15.29s，零错误（仅 chunksize 500 kB 警告，非错误）。
- 验证后已停 dev server，端口 5173/8000 均清理。

## 疑虑（Concerns）

1. **无关问题兜底未走 `_fallback_response` 代码路径**：`/api/chat/ask` 的兜底条件是 `if not evidence and not graph_facts`。但向量路对任意查询恒返回全部 11 条（`top_k=20 > 11`），`rerank` 又无相关性阈值、恒返 top 5，导致 `evidence` 永非空 → 兜底分支在真实环境中**无法触发**（仅单测 `test_ask_empty_evidence_returns_fallback` 通过打空 store 才覆盖）。
   - 实测「今天天气怎么样」：`trace.rerank.status = "证据充分，正常生成"`、`evidence_n = 5`、`confidence = 0.0031`、`references` 5 条噪声。
   - 影响：浏览器验收 Step 5 期望弹窗状态为「知识库未匹配」（对应前端 `_fallback_response` 的 status），实际将显示绿色「证据充分，正常生成」徽章（TraceDialog 以 `evidence_n ? ok : empty` 定色）；且「证据来源折叠」会展示 5 条无关来源。
   - 修复方向（**本任务未改代码**，供后续任务裁定）：在 rerank 精排后增加最低置信度阈值（如 `confidence < threshold` 视作无证据），或在 `evidence`/`confidence` 判定处接入阈值再触发兜底。

## 归档数字速览（供阶段 6 简历引用）

- 图谱：四君子汤 1 跳 **8 条**边（4 组成 + 主治 + 功效 + 2 禁忌）；seed **33 节点 / 32 边**。
- 混合检索（四君子汤问句）：向量 11 / 图谱 8 / 关键词 5 → RRF 融合 11 → 精排取 5，top 命中《四君子汤》相关度 0.9967。
- 对比类（风寒 vs 风热）：图谱 1 / 文献 top 命中 0.9994，验证「对比类走文献」。
- 后端 34 测试全绿；前端 build 零错误、dev server HTTP 200。

## R7 修复后复测（2026-09-14）

> 范围：R7「置信度兜底 + 图谱强证据豁免 + trace 透传 + 异常收口」修复后的 API 复测与浏览器主链路验收。
> 修复项：`_fallback_response` 透传真实检索数字；rerank 后接入 `evidence_min_score` 阈值；低置信但图谱命中走豁免（剔除低分文献、图谱事实独立支撑）；前端徽章按 status 语义着色。

### 无关问题「今天天气怎么样」—— 拒答路径复测

`POST /api/chat/ask` 返回 **200**，关键字段实测：

| 字段 | 复测值 | 预期 | 结果 |
|---|---|---|---|
| `trace.rerank.confidence` | 0.0001 | 低于 `evidence_min_score=0.3` | ✓ |
| `answer` | 「知识库中未检索到可靠依据。请换个问题或稍后再试。」 | 拒答 | ✓ |
| `references` | `[]` | 清空（低分文献剔除） | ✓ |
| `trace.rerank.status` | 「知识库未匹配」 | 同 | ✓ |
| `trace.rerank.evidence_n` | 1 | 真实数字透传 | ✓ |

- 前端弹窗徽章显示**琥珀「empty」**（按 `status === '知识库未匹配'` 定色），不再误显绿色「证据充分」；文本卡为「1 条证据进入回答上下文」但来源折叠为空。

### 「四君子汤由哪些中药组成？」—— 正常路径复测

| 字段 | 复测值 |
|---|---|
| `trace.retrieve.vector_n` | 11 |
| `trace.retrieve.keyword_n` | 5 |
| `trace.retrieve.graph_n` | 8 |
| `trace.fuse.candidate_n` | 11 |
| `trace.rerank.evidence_n` | 5 |
| `trace.rerank.status` | 「证据充分，正常生成」 |

### 浏览器主链路验收

登录 → 空态 → 回答态 → 溯源弹窗 5 步全链路绿：

1. 登录页渲染 ✓
2. 空态（无消息）提示 + 快捷问句 ✓
3. 回答态：回答卡 + 图谱事实 + 溯源入口 + 证据折叠 ✓
4. 溯源弹窗 5 步流程条全亮（doneKeys 固定 [1-5]）✓
5. 弹窗 4 数字卡显示 **11 / 8（1 命中实体）/ 5 / 11** ✓，精排状态徽章按 status 语义着色 ✓

### 回归

```bash
cd backend && .venv/Scripts/python -m pytest -v   # 37 passed
cd web && npm run type-check                       # 0 报错
cd web && npm run build                            # 0 报错
```