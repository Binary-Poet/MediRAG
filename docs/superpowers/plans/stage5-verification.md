# 阶段 5 运行概览 + 推理配置 + 账户/知识库操作 端到端实测验收记录

- 日期：**2026-09-16**
- 环境：Windows 11 / Python 3.12 / Vue 3 + Vite 5.4.21 / MySQL 容器 `medirag-mysql`（宿主 3307）/ Neo4j 容器 `medirag-neo4j`（宿主 7687）/ DeepSeek 生成 + SiliconFlow embedding/rerank **真实调用**
- 被测对象：commit `ba98315` 工作树（阶段 5 全部 10 个实现任务完成态），**本轮未改任何业务代码**
- 隔离前置状态：MySQL `document` 表 2 条（阶段 4 遗留 `验收语料.md`、`验收PDF.pdf`，均「就绪」）；Neo4j 含阶段 4 遗留候选（5 候选节点 / 9 候选边）；`inference_config`/`retrieval_log`/`feedback`/`user` 四表**首次在真实 MySQL 建表**（本轮后端 startup `init_db()` 建表 + seed 三用户）

> **结论先行：DONE_WITH_CONCERNS。** 阶段 5 的 9 个验收步骤全部真实执行通过：门禁全绿（pytest **169 passed** / type-check exit 0 / build exit 0）、**推理配置→问答生效闭环成立**（`semantic_k=3` 时 `retrieve.vector_n=3`，同一问题 `semantic_k=20` 时 `vector_n=13`，决定性对照）、**运行概览数据与手动操作一一对应**（trend 今日 5、quality useful 2 / useless 1 / fallback 0）、登录守卫/账户增删/改密码重登/知识库详情·下载·重命名/图谱重导入/问答反馈全部实测通过（22 张截图留档）。存在 4 项**非阻断**偏差/限制（§6），其中 2 项为前序阶段已披露事项的延续，2 项为本轮验证手段限制。

---

## 0. 实测口径

| 项 | 值 |
|---|---|
| 后端 | `cd backend && .venv/Scripts/python -m uvicorn app.main:app --host 127.0.0.1 --port 8000`（startup 执行 `init_db()` 建表 + seed） |
| 前端 | `cd web && npm run dev` → **5173** |
| 后端客户端 | httpx（规避 Windows Git Bash 下中文 JSON/查询参数的 body/URL 编码问题） |
| 浏览器 | headless Chrome 152，经 CDP（Node 24 原生 `WebSocket` + 自研最小驱动）真实交互 + 逐页截图；未使用 mock |
| 真实消耗 | 问答流式 ×5（含 1 次负路径无）、embedding/rerank ×5、图谱 reimport ×2 |

**关键设计**：为判定「推理配置真实生效」，对**同一问题**做 `semantic_k` 对照——`semantic_k=3` 与 `semantic_k=20` 各跑一次，比较 SSE `retrieve` 事件的 `vector_n`。

---

## 1. 验收一：起服务 + 门禁 —— ✓ 通过

| 项 | 命令 | 真实结果 |
|---|---|---|
| 后端健康 | `GET /health` | **200** `{"status":"ok","app":"MediRAG","env":"dev"}` |
| 后端回归 | `cd backend && .venv/Scripts/python -m pytest -q` | **`169 passed, 70 warnings in 3.54s`**（exit 0） |
| 类型检查 | `cd web && npm run type-check` | `vue-tsc --noEmit` → **exit 0，零错误** |
| 生产构建 | `cd web && npm run build` | **exit 0**，`✓ 2208 modules transformed`，`✓ built in 25.10s` |
| 前端可达 | `GET http://127.0.0.1:5173/` | **200** |

构建体积（真实）——**仍有 2 个 >500 kB 分块警告**：`echarts-CmtS_fMb.js` **563.00 kB**、`index-C8pU429J.js` **1,209.95 kB**（Element Plus 全量）。详见 §6-D1。

---

## 2. 验收二：图谱重导入 + neighbors 冒烟 —— ✓ 通过

| 步骤 | 请求 | 真实结果 |
|---|---|---|
| 重导入 | `POST /api/graph/import` | **`{"imported":{"nodes":33,"edges":32}}`**（与预期逐字一致） |
| neighbors | `GET /api/graph/neighbors?name=四君子汤&hop=2` | **200**，**12 节点 / 17 边**；`links` **无重复**（`DUP_LINKS=[]`）；全部 `status=已发布` |
| 候选探针 | 同上，检索 `风热犯表-表现->口渴` | **不存在**（`PROBE_LINKS=[]`）——阶段 4 泄漏探针**未**出现在 2-hop 邻居事实中（候选边过滤已生效） |

复核：重导入返回 33/32 为 seed 幂等结果；库中仍保留阶段 4 遗留 5 候选节点 / 9 候选边（reimport 语义为「不覆盖已发布/候选状态」，候选经 `GET /api/graph/candidates` 确认存在），但**候选边不进入 `neighbors` 事实**（本轮探针为证）。

---

## 3. 验收三：推理配置 → 问答生效闭环 —— ✓ 通过（本阶段核心）

| 步骤 | 请求 | 真实结果 |
|---|---|---|
| 读默认 | `GET /api/config` | `20/20/25/5/60`，`model=deepseek-chat`，`answer_temp=0.3`，`query_temp=0.1`（与规格逐字一致） |
| 改配置 | `PUT /api/config {semantic_k:3, …}` | **200**，回显 `semantic_k=3`；再次 `GET` 确认为 3 |
| 问答（semantic_k=3） | `POST /api/chat/stream`（四君子汤问题） | SSE `step:retrieve` → **`vector_n=3`**、`graph_n=8`；`done.metrics.vector_n=3`、`evidence_n=3`；rerank `confidence=0.9967` |
| **对照（semantic_k=20）** | 同一问题再发 | SSE `step:retrieve` → **`vector_n=13`**（同问题、同语料，向量召回数由 3 提升至 13） |
| 恢复 | `PUT /api/config`（原默认） | **200**，`GET` 确认回到 `20/20/25/5/60` |

**判定**：`vector_n` 严格受 `semantic_k` 约束，且同问题两种配置下召回数不同（3 vs 13），证明**推理配置经 DB 落库 → 注入 agent state → 影响检索 top_k** 的链路真实生效，非巧合。

浏览器侧（§5）：推理配置页默认值渲染为 `20/20/25/5/60`、`0.30/0.10`；将「语义召回数」改为 **12** 后点「保存本组」→ toast **「已保存，下一次问答请求生效」**；后端 `GET /api/config` 随即变为 `semantic_k=12`（保存写库确认），随后经 API 复位为 20。

---

## 4. 验收四：运行概览真实数据 —— ✓ 通过

先经 API 产生日志：问答 ×4（1 次配置对照 + 3 次问题），反馈 ×2（1 有用 + 1 无用）。后经浏览器再问答 1 次 + 点「有用」1 次。末次 `GET /api/stats/overview`：

| 键 | 真值 | 与手动操作核对 |
|---|---|---|
| `trend`（2026-09-16） | **count=5** | = 4 次 API 问答 + 1 次浏览器问答 ✓ |
| `quality.total` | **5** | = 上述 5 次 retrieval_log ✓ |
| `quality.fallback_n` | **0** | 无兜底 ✓ |
| `quality.useful` | **2** | = API 1 次 + 浏览器点「有用」1 次 ✓ |
| `quality.useless` | **1** | = API 1 次 ✓ |
| `quality.satisfaction` | **0.667** | = 2/(2+1) ✓ |
| `quality.success_rate` | **1.0** | = 5/5 ✓ |
| `role_dist` | 管理员 / 知识用户 / 中医药从业者 各 **1** | = seed 三用户 ✓ |
| `status_dist` | 就绪 **2** | = 2 条就绪文档 ✓ |
| `topic_dist` | 内科 **2**（切片和） | = 2 文档同内科 ✓ |

浏览器「运行概览」页（截图 `03-overview.png`）：5 卡渲染、4 个 canvas，折线今日有值、环形图三种角色、状态柱「就绪」、检索质量进度条「用户满意度 50% / 完成率 100%」与指标卡 `有用1 无用1 兜底0 正常4`（该截图摄于浏览器反馈之前，故为 1/1，与当时 API 一致）。数据**全部来自真实接口**，无写死。

---

## 5. 浏览器逐页验收 —— ✓ 通过

22 张截图留档于 `.superpowers/sdd/2026-09-16-stage5-overview-config/shots/`（该目录被 gitignore）。

| # | 页面/操作 | 结果 | 截图 |
|---|---|---|---|
| P0-1 | 登录页 | 渲染与规格一致（品牌区 + 表单区 + 体验环境） | `00-login.png` |
| — | 未登录访问 `/qa` → 守卫 | 重定向 **/login**（`localStorage.token=null`） | — |
| — | 点体验账号「管理员」 | 用户名**自动填充为 `admin`**；密码需手填 | `01-login-filled.png` |
| — | 登录成功 | 跳 **/qa**，`medirag_token`/`medirag_user` 落库，用户=`系统管理员/管理员` | `02-mainlayout.png`（含「登录成功」toast） |
| P1 | 运行概览 | 5 卡 + 2+3 网格 + 真实数据 | `03-overview.png` |
| P1 | 推理配置 | 默认 `20/20/25/5/60`、`0.30/0.10`、重置/保存/恢复 | `04-inference.png` |
| — | 改值保存 | 语义召回数 20→**12** → 保存 → toast「已保存，下一次问答请求生效」；后端确认 `semantic_k=12` | `20-inference-saved.png` |
| P2 | 账户管理 | 3 种子用户；admin 行「删除」**禁用**（禁自删） | `05-account.png` |
| — | 新建用户 | 弹窗填 `e2euser/验收测试员/知识用户/…` → 确定 → 列表变 4 行 | `07-account-dialog.png`、`08-account-after-create.png` |
| — | 删除用户 | 确认框「确定删除用户「验收测试员」？」→ 删除 → 列表回 3 行 | `09-account-after-delete.png` |
| P2 | 我的档案 | 账号信息卡（用户名/姓名/角色）+ 修改密码表单 | `06-profile.png` |
| — | 改密码 → 重登 | 改 `admin123→admin1234` → toast「密码已修改」；**旧密码登录 401「用户名或密码错误」**；**新密码登录成功**；再改回 `admin123` | `17/18/19-*.png` |
| P0-6 | 知识库 | 统计卡 + 主题筛选 + 表格（2 文档，操作列 详情·下载·重命名·删除） | `12-library.png` |
| P0-6 | 文档详情 | 弹窗：名称/知识主题/格式/大小/状态/切片数/上传时间/来源文件 | `13-library-detail.png` |
| P0-6 | 重命名 | `验收PDF.pdf` → `验收PDF-renamed.pdf` → 列表刷新 → 再改回原名 | `14-library-after-rename.png` |
| P0-6 | 下载 | 接口层已验证（见 §6-D4） | — |
| P0-5 | 图谱页 | 实体列表 + 关系图 + 候选审核 Tab | `10-graph.png` |
| P0-5 | 重新导入基础数据 | 确认框 → toast **「已导入 33 节点 / 32 关系」** | `11-graph-reimport.png` |
| P0-3 | 问答 | 回答含图谱事实 8 条 + 证据折叠 (5) + 溯源弹窗（13 向量/8 图谱/0 关键词/13 融合） | `15a-chat-trace.png`、`15-chat-answer.png` |
| — | 反馈按钮 | 点「有用」→ 两按钮**均 `disabled=true`**（乐观置位生效） | `16-chat-feedback.png` |

**视觉对照（`docs/前端还原规格.md` P1）**：

- 运行概览——实测网格为「第一行：问答量趋势[宽] + 用户角色分布；第二行：中医药知识主题分布 + 知识库状态分布 + 检索质量统计」，与规格 P1「第一行 2 列、第二行 3 列」**逐字一致**；5 个卡片标题（含「近14天」筛选、「用户满意度/检索完成率」进度条 + 4 指标卡）与规格一致。
- 推理配置——「混合检索组」5 项步进器各带「重置」，「生成模型组」下拉 + 2 滑杆，操作「保存本组 / 恢复全部默认」，底部「变更保存后将立即应用于新的问答请求」，与规格 P1 **逐字一致**。

---

## 6. 缺陷与偏差清单

| 编号 | 级别 | 事项 | 证据 | 性质 |
|---|---|---|---|---|
| **D1** | 低（偏差） | **构建仍有 2 个 >500 kB 分块警告**（`echarts` 563.00 kB、`index` 1,209.95 kB）。计划 Self-Review 写「ECharts 按需（消除 >500kB 警告）」，**实际未完全消除** | §1 build 输出；`task-10-report.md` 已披露 | **前序已披露**：Task 10 将图谱页 513.84→8.66 kB（目标达成），但 rollup 将三消费者 echarts 合并为单块 563 kB，`index` 为 Element Plus 全量，均超 Task 10 范围 |
| **D2** | 低（偏差） | 登录页「体验账号」卡片**仅自动填充用户名**，密码置空需手填。计划 Step 6 写「体验账号 admin 自动填表 → 登录成功」，措辞与实现略有出入 | `Login.vue:25-28` `fillAccount` 将 `form.password=''`；实测点击后用户名=`admin`、密码空 | 实现选择，非缺陷；文案「选择账号后自动填充」亦可理解为仅用户名 |
| **D3** | 极低（外观） | 主布局右上角用户区渲染为「**系统管理员**」+ 角色标签「**管理员**」（两元素），未见「·」分隔符。计划 Step 6 写「系统管理员·管理员」 | `02-mainlayout.png`、`03-overview.png` | 外观细节，「·」或为计划口语化简写 |
| **D4** | 中（验证手段限制） | 「下载」在 **headless Chrome 下无法落盘**（`Browser.setDownloadBehavior`/`Page.setDownloadBehavior` + 真实鼠标点击均无文件生成）。**接口层已充分验证**：`GET /api/documents/2/download` → **200**、`Content-Disposition: attachment; filename*=utf-8''验收PDF.pdf`（原名，PDF `content-type=application/pdf`）；页面内 `fetch('/api/documents/2/download')` → **200, 787 B**（md 为 **405 B**） | §5 表格；下载目录为空 | **环境限制**，非应用缺陷；下载 URL 与按钮接线正确 |
| **D5** | 中（前序缺陷延续） | 图谱实体列表可见阶段 4 **C2**：候选节点（如「升阳举陷」）**无 `type`**，类型标签空白；且候选节点（实体列表计 **39** 个）出现在浏览列表 | `11-graph-reimport.png`（「升阳举陷」类型列空白） | **阶段 4 已归档缺陷**（`stage4-verification.md` §6-C2/C3），非阶段 5 引入，本轮未改代码 |

**有利事实（记录）**：① `reimport` 返回 `33/32` 且**不清理候选**，与其接口注释「幂等，不覆盖已发布/候选状态」一致；② 候选边**不进入** `neighbors`（探针 `风热犯表-表现->口渴` 缺失），阶段 4 泄漏面在「图谱浏览/邻居查询」这一入口已收敛（问答链路的隔离结论见阶段 4 §3，本轮未重复）。

---

## 7. 服务与端口（最终状态）

| 服务 | 状态 |
|---|---|
| 后端 8000 | 本轮启动并实测 → **已停止**（端口已释放） |
| 前端 5173 | 本轮启动并实测 → **已停止**（端口已释放） |
| headless Chrome（CDP 9333） | 本轮启动 → **已停止** |
| MySQL 3307 / Neo4j 7687 | 任务前后均在运行，**未变更** |

后端运行期日志：68 次请求，**0 次 500、0 次 Traceback**；唯一非 2xx 为**主动构造**的 `POST /api/auth/login → 401`（旧密码负路径），符合预期。

**本轮运行态变更（非 git 跟踪，供控制器复用）**：

| 存储 | 变更 |
|---|---|
| MySQL `retrieval_log` | 新增 5 条（今日） |
| MySQL `feedback` | 新增 3 条（useful 2 / useless 1） |
| MySQL `inference_config` | 首次建行，末次值 = 默认 `20/20/25/5/60`、`deepseek-chat`、`0.3/0.1` |
| MySQL `user` | seed 3 用户；`e2euser` 建后已删；`admin` 密码已改回 `admin123` |
| MySQL `document` | `验收PDF.pdf` 经重命名已回原名；2 文档数据未净变 |
| Neo4j | 候选 5 节点 / 9 边（阶段 4 遗留）；已发布 33 节点 / 32 边（reimport 幂等） |

---

## 8. 结论（对照阶段 5 验收口径）

| 验收项 | 结果 | 证据 |
|---|---|---|
| 门禁全绿 | **✓** | §1：pytest 169 passed；type-check/build exit 0 |
| 图谱冒烟（33/32、无候选、无重复 links） | **✓** | §2 |
| 推理配置→问答生效闭环 | **✓** | §3：`semantic_k=3→vector_n=3`，`20→13`；保存写库 |
| 运行概览真实数据（与操作一一对应） | **✓** | §4 |
| 登录守卫/账户增删/改密码重登 | **✓** | §5 |
| 知识库详情/下载/重命名 + 图谱重导入 | **✓**（下载为接口级） | §5 |
| 问答反馈按钮（点击后禁用） | **✓** | §5 |
| 视觉对照 P1 两页布局 | **✓** | §5 |

**总判定：DONE_WITH_CONCERNS。** 阶段 5 全部验收口径实测通过，核心「推理配置生效闭环」与「运行概览真实数据」均以决定性证据成立；非阻断偏差 5 项（2 项为前序阶段已披露延续、2 项为验证手段/外观细节、1 项为环境限制），不影响阶段 5 通过判定。**本轮按规程未改任何业务代码。**
