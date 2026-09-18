# 辨证问答页「问答会话」侧栏 + 会话持久化 设计文档

**Goal:** 补齐《前端还原规格.md》P0-2 已规定但未实现的左侧「问答会话」列表——新建对话、全部/已收藏筛选、历史会话项（标题 / 相对时间 / 条数 / 收藏 / 更多操作），并为其提供后端会话持久化与列表 API，使会话可跨进程重启保留、按用户隔离、点开可完整回放。

**Spec:** `docs/前端还原规格.md`（P0-2 第 96-99 行）、`docs/MediRAG-合并改造方案.md`（7.2 目录结构、第八节 API 清单）。

---

## 1. 背景与现状缺口

规格把左侧会话列表作为 P0-2 的一部分定死了，但当前实现里这条链路整条缺失：

| 侧 | 现状 | 缺口 |
|---|---|---|
| 后端 | `app/agent/memory.py` 用进程内 `_sessions: dict` 存会话，重启即失 | 无持久化、不区分用户、无列举/收藏能力 |
| 后端 | session_id 由前端 `crypto.randomUUID()` 生成，后端不认识 | 会话无法归属、无法可靠列举 |
| 后端 | `/api/chat/stream` 未挂 `current_user` | 拿不到当前用户，会话无法按用户隔离 |
| 前端 | `Chat.vue` 单栏，无 `SessionList.vue` | 无会话列表、无收藏、无历史回放 |

会话条目现在唯一的下游消费者是 `understand` / `reflect` 节点的 `chat_history`（多轮改写与自反思的上下文），因此持久化改造必须同时保证「恢复出的历史」与「喂给 LLM 的历史」是同一份数据。

## 2. 数据模型

新增 `backend/app/models/chat.py`，并在 `app/db.py` 的 `init_db()` 模型导入列表中注册。

```
chat_session
  id          String(32)   PK            # uuid4().hex，沿用现有形态
  user_id     Integer      index         # 归属用户，来自 current_user
  title       String(500)                # 首条提问原文，前端 CSS 截断显示
  favorite    Boolean      default False
  created_at  DateTime     default utcnow
  updated_at  DateTime     default utcnow

chat_message
  id          Integer      PK
  session_id  String(32)   index
  seq         Integer                    # 会话内序号，保证回放顺序
  role        String(16)                 # user / assistant
  content     Text
  payload     JSON         nullable      # 助手消息：{trace, references, graph_facts, safety}
  created_at  DateTime     default utcnow
```

- `payload` 用 `sqlalchemy.JSON`：MySQL 8 原生 JSON 列，测试用的 `sqlite:///:memory:` 同样支持，无需方言分支。
- 用户消息 `payload` 为 `null`。
- 表间不做数据库级外键，删除会话时由 service 层显式删除其消息（与既有 `Document` 的表风格一致，避免 sqlite 测试的外键开关差异）。

## 3. 后端接口

新增 `backend/app/services/chat_session.py` 承载业务语义；`app/api/chat.py` 只做协议映射与接线（AGENTS.md：API 层不拥有业务语义）。

| 方法 | 路径 | 鉴权 | 说明 |
|---|---|---|---|
| GET | `/api/chat/sessions?favorite=` | ✔ | 当前用户会话列表（`updated_at` 倒序）+ `total` / `favorite_total` |
| PATCH | `/api/chat/sessions/{sid}` | ✔ | 收藏 / 取消收藏，请求体 `{"favorite": bool}` |
| DELETE | `/api/chat/sessions/{sid}` | ✔ | 删除会话，级联删除其消息 |
| GET | `/api/chat/sessions/{sid}/messages` | ✔ | 完整回放数据（按 `seq` 升序） |
| POST | `/api/chat/stream` | **新增** ✔ | 主问答，落库 |

**越权处理**：四个会话接口均校验 `sid` 归属当前用户，不匹配返回 **404** 而非 403——403 会泄露「该 id 存在」。`/chat/stream` 请求体里传入的 `session_id` 同样要校验归属，否则可以用别人的会话 id 往其会话里灌消息。

**`seq` 赋值**：取该会话当前最大 `seq` 加一（会话内并发提问的场景不在范围内，不做额外加锁）。

**`/chat/stream` 落库时序**（相对现状的唯一实质变化）：

现状在生成结束后才 `upsert_message`，改造后改为请求开始时即建会话并写入 user 消息。理由是生成阶段抛错时仍能保住提问、且不会产生没有任何消息的空壳会话。**顺序必须是**：

```
建会话（若 body.session_id 为空）
  → get_history(session_id)      # 必须先读历史
  → 写入 user 消息
  → 跑图
  → 生成结束后写入 assistant 消息（含 payload）
  → 更新 session.title / updated_at
```

若把「写入 user 消息」提到 `get_history` 之前，当前问题会被重复塞进 `chat_history`，污染多轮上下文。

`done` 事件已返回 `message_id: session_id`，前端据此认领会话 id，无需改协议。

## 4. `memory.py` 改为 DB 支撑

`get_history(session_id)` 改为查询该会话最近 `_HISTORY_CAP`（8）条消息，**签名不变**，因此 `understand` / `reflect` 节点零改动。

理由：既然回放要完整，一致性就是这次改动的全部价值。若维持内存实现，进程重启后点开历史会话再追问，UI 上有历史而 LLM 拿不到上下文，演示时一眼可见；且内存 dict 与 DB 会形成两套 id 空间。

- `MAX_SESSIONS` 逐出逻辑由「按用户列举」取代，删除。
- `new_session()` 由 service 层的建会话取代，删除。
- 代价是每次问答多一次本地 DB 读（<5ms，相对上游 ~3.2s 的 API 往返可忽略）。

## 5. 前端结构

`SessionList.vue` 是规格点名的组件；Chat.vue 从单栏改为规格 P0-2 的「左约 280px 会话列表 + 右弹性问答区」。

| 文件 | 责任 |
|---|---|
| `web/src/api/chat.ts`（修改） | 新增 4 个会话接口；`streamChat` 补 `Authorization` 头 |
| `web/src/stores/session.ts`（新建） | 会话列表 / `activeId` / fetch / toggleFavorite / remove（方案 7.2 已规划 `stores/` 放 session） |
| `web/src/views/qa/components/SessionList.vue`（新建） | 规格 P0-2 的列表区 |
| `web/src/views/qa/Chat.vue`（修改） | 左右分栏布局 + 历史会话灌入 `messages` |
| `web/src/types/chat.ts`（修改） | `SessionSummary` / `StoredMessage` 类型 |
| `web/src/utils/time.ts`（新建） | 相对时间格式化（"14小时前"） |

**为什么用 store 而不是 props/emit**：会话列表与问答区存在双向共享状态——「+ 新对话」要清空问答区、点击会话要把消息灌进问答区、提问完成后要刷新列表项标题/时间/条数。单靠父子传参会形成环形依赖。

## 6. 交互闭合

- **「+ 新对话」** → 清空问答区、`activeId = null`，**不预建空会话**。
- **首次提问** → 后端建会话，前端从 `done` 事件认领 `session_id`，刷新列表并激活该项。
- **点击历史项** → 拉 `/messages`，把 `payload` 还原成现有 `QA` 结构（`answer` / `references` / `graphFacts` / `safety` / `trace`），复用同一套卡片渲染，不新增渲染分支。
- **「N条」** → 消息条数（user + assistant 各一条）。与截图中 1 轮问答显示「2条」的算术吻合。
- **「2 个历史会话 · 0 个收藏」** → 取自接口返回的 `total` / `favorite_total`。
- **收藏** → PATCH 后「已收藏」页签过滤显示。
- **删除** → 二次确认后移除；若删的是当前激活会话，回到空态。

## 7. 测试策略

遵循 AGENTS.md：pytest 不得依赖真实网络 / MySQL / Neo4j / LLM。

- **新增** `backend/tests/test_chat_sessions.py`：列表、收藏与取消、删除级联、**越权返回 404**、回放 payload 完整性。
- **修改** `backend/tests/test_chat_stream.py`：7 个既有用例补 Bearer 头（照 `test_feedback.py` 既有模式登录 admin 取 token），并新增「落库」断言。
- **修改** `backend/tests/test_memory.py`：4 个用例从内存 dict 改为 sqlite 夹具。
- **前端**：`npm run type-check` + 浏览器实跑（提问 → 会话项出现 → 收藏 → 切页签 → 点开回放 → 删除）。

## 8. 验收标准

1. 侧栏四要素与截图一致：区块标题+统计、`+ 新对话`（绿色填充）、`全部 N`/`已收藏 N` 页签、会话项（截断标题 + `相对时间 · N条` + 悬停 `⋯`）。
2. 提问后会话出现在列表；进程重启后仍在；`memory.py` 恢复的上下文与列表显示一致。
3. 点开历史会话，正文 / 图谱依据 / 证据来源 / 思考过程四项与当时一致。
4. 收藏可切换且「已收藏」页签正确过滤；删除生效。
5. 未登录调用 `/api/chat/stream` 返回 401；越权访问他人会话返回 404。
6. `pytest` 全绿，`npm run type-check` 通过。

## 9. 明确不做

- 会话重命名（方案 7.4 划为 P2 边角）。
- 导出 / 下载会话。
- Redis 会话记忆（方案列为 P1，当前 `docker-compose.yml` 中 Redis 未启用，且 MySQL 已是既有依赖）。
- 跨会话搜索。

## 10. 一处刻意偏离方案文档

方案第八节 API 清单写了 `POST /api/chat/session`（新建会话）。本设计**不实现该接口**：前端走 lazy 建会话后它是死接口，而预建会在列表里留下没有消息的空壳会话。方案优先级低于 AGENTS.md 与源码，此偏离已经用户确认。
