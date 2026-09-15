# 阶段 3 Agentic 化端到端实测验收记录

- 日期：2026-09-15
- 环境：Windows 11 / Python 3.12 / langgraph **1.2.11**（requirements 仅约束 `langgraph>=0.2.0`，未钉上限）/ Neo4j 容器 medirag-neo4j（33 节点 / 32 边）/ DeepSeek 流式生成 + SiliconFlow rerank 真实调用
- 结论先行：**【初测发现阻断级缺陷，已修复并复测通过】** 初测时 `/api/chat/stream` 在真实 langgraph 下 100% 崩溃（`app/api/chat.py:47` 对 `graph.stream(stream_mode="updates")` 的产出形状解包错误）；修复（commit `b9b50c7`：dict/元组双形状适配 + mock 形状对齐真实 API + requirements 收紧 `langgraph>=1.2,<2`）后 SSE 层五项复测全部通过（见文末「修复后复测」小节）。Agent 图六项验收（意图路由 / 工具轨迹 / 多轮改写 / 兜底 / 急症拦截 / reflect）与浏览器视觉验收均通过。

## 1. 阻断级缺陷：SSE 流式协议在真实 langgraph 下崩溃

### 1.1 复现

```bash
cd backend && .venv/Scripts/python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
curl -sN -X POST http://127.0.0.1:8000/api/chat/stream \
  -H "Content-Type: application/json" \
  --data-binary @body.json   # {"question":"四君子汤由哪些中药组成？"}
```

- 客户端：HTTP 200，**响应体 0 字节**，httpx 报 `RemoteProtocolError: peer closed connection without sending complete message body (incomplete chunked read)`；未收到任何 `step`/`token`/`references`/`done` 帧。
- 服务端 uvicorn 日志：

```text
File "backend/app/api/chat.py", line 47, in gen
    for node_name, update in graph.stream(initial, stream_mode="updates"):
ValueError: not enough values to unpack (expected 2, got 1)
```

### 1.2 根因

langgraph 1.2.11 中，单一字符串 `stream_mode="updates"` 每次产出的是**单键 dict** `{"节点名": update}`（迭代 dict 只得到 1 个键），而 `chat.py:47` 按 `(node_name, update)` 二元组解包，首个节点（understand）更新即抛 `ValueError`，生成器在发出任何 SSE 帧之前终止。

实测对照（真实图、真实初始 state）：

| 调用方式 | 产出形状 |
|---|---|
| `g.stream(state, stream_mode="updates")` | `dict`，键为节点名（understand/retrieve/fuse/safety/context） |
| `g.stream(state, stream_mode=["updates"])` | `tuple ('updates', {节点名: update})` —— 与 `chat.py` 的解包形状吻合 |

即最小修复方向是 `stream_mode=["updates"]`（或按 dict 形状迭代）；**按任务规程未改代码**，仅归档证据。

### 1.3 为什么 66 个测试没拦住

`backend/tests/test_chat_stream.py:25` 的假图 `fake_graph.stream.return_value = [(node_name, update_dict), ...]` —— mock 返回的是**元组列表**，恰好符合 `chat.py` 假设、不符合真实 langgraph 行为。测试与实现共享同一个错误假设，形成盲区。（同理，阶段 3 文档 6216cfd 修复过的 "SSE trace event-stream accumulation bug" 也是在该 mock 协议下验证的。）

### 1.4 影响面

验收要点 1–5 的 **API 层**（step 事件序列、token 多帧流式、references/done、safety 事件、意图与 plan 经 SSE 透出）全部不可达；浏览器侧打字机/逐步点亮/弹窗亦无法走通（浏览器视觉验收由控制器另行执行，将同样被阻断）。图逻辑与生成管线本身无恙（见 §2、§3）。

## 2. 图级真实实测（`graph.invoke`，绕过损坏的 SSE 层）

用与 `chat.py:_initial_state` 完全一致的初始 state、真实 understand LLM（DeepSeek）、真实向量/BM25/Neo4j 检索与 SiliconFlow rerank 跑六项场景（脚本：`backend/scripts/stage3_graph_verify.py`，原始数据：`backend/stage3_graph_results.json`，均未提交，仅本地留档）。

### 2.1 意图路由矩阵实测

| 场景 | 问题 | intent | plan（工具轨迹） | vector_n | keyword_n | graph_n | evidence_n | confidence | safety_flag | reflect |
|---|---|---|---|---|---|---|---|---|---|---|
| relation | 四君子汤由哪些中药组成？ | relation | vector_search, graph_search | 11 | 0 | 8 | 5 | 0.9968 | ok | 0 |
| concept | 风寒束表与风热犯表有什么区别？ | concept | vector_search, keyword_search | 11 | 4 | **0** | 5 | 0.9994 | ok | 0 |
| chitchat | 今天天气怎么样 | chitchat | （空，不检索） | 0 | 0 | 0 | 0 | 0.0 | **low_confidence** | 0 |
| emergency | 我胸痛怎么办，胸口疼得厉害 | complex | vector_search, keyword_search, graph_search | 11 | 2 | 0 | 5 | 0.1686 | **emergency** | **1** |
| 多轮 q1 | 四君子汤由哪些中药组成？ | relation | vector_search, graph_search | 11 | 0 | 8 | 5 | 0.9968 | ok | 0 |
| 多轮 q2 | 它有什么禁忌？ | relation | vector_search, graph_search | 11 | 0 | 8 | 5 | 0.2219 | ok | 0 |

要点：

- **不同问题走不同工具组合** ✓：relation → 向量+图谱（graph_n=8）；concept → 向量+关键词（graph_n=0，符合预期）；chitchat → 不检索（plan 为空）；complex → 三工具全开。
- **trace 里 plan 可见** ✓：retrieve trace 含 `plan` 字段与各路命中数（如 `{"step":"retrieve","vector_n":11,"keyword_n":0,"graph_n":8,"entity_n":1,"entities":["四君子汤"]}`）。

### 2.2 relation 场景真实事件（trace）序列

```text
understand  raw=四君子汤由哪些中药组成？ rewritten=同 entities=[四君子汤] intent=relation
retrieve    vector_n=11 keyword_n=0 graph_n=8 entity_n=1
fuse        candidate_n=11 method=RRF
rerank      evidence_n=5 confidence=0.9967 status=证据充分，正常生成
safety      flag=ok
```

图谱事实（Neo4j 真实返回，8 条）：四君子汤 --组成--> 人参/白术/茯苓/炙甘草；--主治--> 脾气虚；--功效--> 益气健脾；--禁忌--> 对方剂成分过敏者禁用、证候不符不得使用。

### 2.3 多轮指代改写证据（chat_history 传递）

同 session（`verify-graph-multiturn`）：

- 第 1 问「四君子汤由哪些中药组成？」→ 正常回答后入会话记忆；
- 第 2 问「它有什么禁忌？」，understand trace：

```json
{"step": "understand", "raw": "它有什么禁忌？", "rewritten": "四君子汤有什么禁忌？",
 "entities": ["四君子汤"], "intent": "relation"}
```

指代「它」被改写为「四君子汤」，且检索拿到 8 条四君子汤图谱事实（含 2 条禁忌三元组）→ **多轮指代改写 ✓**（会话内存 dict + chat_history 传递链路真实生效）。

### 2.4 乱问兜底证据

「今天天气怎么样」：intent=chitchat → 不检索 → safety 置 `low_confidence`，answer 直接为兜底话术（**不走 LLM 生成**，safety 节点产文）：

> 知识库中未检索到可靠依据。请换个问题，或提供更具体的证候、方剂或中药名称。

（API 层将据此发 `safety{type:low_confidence}` 事件 —— 该帧因 §1 缺陷暂不可达。）

### 2.5 急症拦截证据

「我胸痛怎么办，胸口疼得厉害」：understand 识别实体「胸痛」；safety 节点 `detect_emergency` 命中 → `safety_flag=emergency`，safety_message 为就医提示（API 层将发 `safety{type:emergency}` 事件并仍以急症 prompt 生成回答 —— 生成段因 §1 暂不可达）。

### 2.6 reflect-then-recover（demo case）

急症问题**真实触发了一轮反思**（seed 语料下少见）：

```text
rerank   evidence_n=5 confidence=0.028  status=知识库未匹配
reflect  round=1 reason="Top 相关度 0.028 低于阈值 0.3" rewritten="胸口疼 胸痛 缓解方法"
retrieve vector_n=11 keyword_n=2
rerank   evidence_n=5 confidence=0.1686 status=知识库未匹配
```

首轮证据不足 → reflect 改写查询 → 补查一轮（confidence 0.028 → 0.1686，仍不足 → 走安全兜底/急症路径）。reflect≤1 约束由 `test_agent_graph.py` 图级测试覆盖，本实测提供了一个真实触发样本。

### 2.7 生成阶段独立验证（绕过 SSE 层直接调用）

对 relation 场景的最终 prompt 真实调用 DeepSeek 流式接口：**19 个 token 帧**，回答首句「四君子汤由人参、白术、茯苓、炙甘草四味药组成 [1]。」—— 生成管线与引用标注本身工作正常。

## 3. 门禁与门禁外检查

| 项 | 结果 |
|---|---|
| `pytest -q`（backend 全量） | **66 passed**（1.03s） |
| `npm run type-check`（vue-tsc） | 零错误 |
| `npm run build`（vite） | 成功（仅 chunk >500kB 警告，非错误） |
| 前端 dev server（vite, 5173） | `curl` → **200**（健康后即停） |
| 端口清理 | 8000 / 5173 均已释放 |
| 浏览器视觉验收 | 未执行（API 层被 §1 阻断，留给控制器裁定） |

## 4. 结论（对照合并方案「验证」小节）

| 验收项 | 结果 | 说明 |
|---|---|---|
| 不同问题走不同工具组合 | ✓（图级） | §2.1 路由矩阵，四类意图工具轨迹全部符合设计 |
| trace 里 plan 可见 | ✓（图级）/ ✗（SSE 层） | trace 数据真实存在；SSE 透出被 §1 阻断 |
| 多轮指代改写 | ✓（图级） | 「它有什么禁忌？」→「四君子汤有什么禁忌？」 |
| 乱问兜底 | ✓（图级）/ ✗（SSE 层） | chitchat → low_confidence + 兜底话术，不调 LLM |
| 急症拦截 | ✓（图级）/ ✗（SSE 层） | emergency flag + 就医提示 |
| demo case（reflect-then-recover） | ✓（真实触发 1 轮） | §2.6 |
| SSE 事件协议（step/token/references/done/safety） | **✗ 阻断** | §1，chat.py:47 解包错误 |

**总判定：DONE_WITH_CONCERNS。** Agent 编排、意图路由、检索组合、反思、安全拦截、多轮改写、生成与引用——业务逻辑层全部真实验证通过；但对外 SSE 协议层存在 1 行级阻断缺陷（`chat.py:47` `stream_mode="updates"` 应为 `["updates"]` 或按 dict 迭代），且现有 mock 测试无法发现此类协议漂移。**建议后续修复项：** ① 修正解包；② 将 `test_chat_stream.py` 的 fake stream 改为产出与真实 langgraph 相同的形状（或在 CI 中加一条不 mock 图的冒烟流式用例）。

---

## 修复后复测（2026-09-15，commit b9b50c7 后）

### SSE 层五项复测（httpx 流式实测）

| 场景 | 结果 |
|---|---|
| 四君子汤组成（relation 意图） | 事件序列 `step×4 → token×19 → references → done`；打字机流式正常 |
| 今天北京天气（chitchat/未覆盖） | `safety` 事件 `low_confidence` + 拒答话术「知识库中未检索到可靠依据…」 |
| 胸痛（emergency） | `safety` 事件 `emergency` + 「请立即就医或拨打 120」+ 仍流式生成带急症警示的回答 |
| 多轮指代（同 session_id） | 第一问「四君子汤由哪些中药组成？」→ 第二问「它有什么禁忌？」正确改写为四君子汤禁忌，图谱事实两条（过敏禁用/证候不符）准确回答 |
| 全量回归 | pytest 66 通过；前端 type-check + build 零错误 |

### 浏览器视觉验收（前端 dev + 真实后端）

- 空态：主标题「开始一次可追溯的辨证问答」+ 5 常用问题卡片（文案与规格 P0-2 逐字一致）+ 免责声明。
- 点击「四君子汤由哪些中药组成？」：回答文本采样 5 → 5 → 27 字**增量增长**（打字机真实流式，reactive 修复生效）。
- 溯源弹窗：5 步流程条全部点亮；数字卡 **向量 11 / 图谱 8 / 关键词 0 / RRF 11**；徽章绿色「证据充分，正常生成」。
- 服务验收后已停止（8000/5173 端口释放）。

### 阶段 3 验收对照（合并方案「阶段 3 验证」小节）

| 验收项 | 状态 |
|---|---|
| 不同问题走不同工具组合（意图路由矩阵） | ✅ 图级 + SSE 级实测（concept 走向量+关键词 graph_n=0；relation 图谱为主） |
| trace 里看到 Agent 的 plan | ✅ understand/retrieve 事件含 entities/intent/plan 工具轨迹 |
| 多轮指代正确改写 | ✅ 「它有什么禁忌？」→ 四君子汤禁忌 |
| 乱问触发兜底 | ✅ low_confidence 拒答 |
| 首轮不足、反思后补查成功 demo case | ✅ 真实触发 1 轮 reflect（初测记录）+ 图级测试 test_agent_graph.py 固化 |

---

## 协议偏差记录（阶段 3 终审 M-1 / M-2）

阶段 3 实现与合并方案 spec 存在以下已知偏差，均经终审裁定为可接受，记录在案。

### 1. `answer_cn_tcm.txt` 规则 4 保留（有利偏离）

计划原意删除该硬话术（"知识库中未检索到可靠依据"），改为统一由 safety 拦截产出拒答。实际**保留为第二道防线**：与 safety 拦截构成双保险——即便 safety 未触发而 LLM 拿到空证据，也不会编造。保留是有利的偏离。

### 2. spec 4.3 三处小偏差

- **ok 路径不发 `safety{type:"ok"}`**：正常生成路径不发送 safety 事件，前端 `m.safety.type !== 'ok'` 的 `!== 'ok'` 判断成为死分支（防御性保留）。
- **reflect 事件字段名为 `rewritten`**（spec 中为 `rewritten2`）：与 understand 事件字段命名统一。
- **understand step 缺 `title` 字段**：trace step 事件未携带 title。
- **`done.message_id` 实际填 `session_id`**：并非独立 message 主键。

### 3. 新增 `error` 事件（不在 spec 4.3 事件列表内）

阶段 3 为生成/检索阶段的异常收口引入 `error` 事件（`{"detail": ...}`）：LLM/网络/图执行异常时前端可显式提示，而非静默断流。spec 4.3 未列举该事件类型，属阶段 3 新增。
