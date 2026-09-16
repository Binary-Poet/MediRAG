# 问答会话侧栏 + 会话持久化 端到端实测验收记录

- 日期：**2026-09-16**
- 分支：`feat/chat-session-list`（BASE `418c223`，**13 个提交** `9d4af1b..6dcbc43`，17 文件 **+1131/-79**）
- 环境：Windows 11 / Python 3.12 / Vue 3 + Vite 5.4.21 / MySQL 8.4 容器 `medirag-mysql`（宿主 3307）/ Neo4j 5.20 / DeepSeek 生成 + SiliconFlow embedding·rerank **真实调用**
- 被测对象：上述分支工作树，**本轮未改任何业务代码**

> **结论先行：DONE。** 门禁全绿（pytest **197 passed**、type-check exit 0、build exit 0）；API 级 9 组断言全部实测通过，其中「收藏筛选下 `total` 仍回报全部会话数」用两个会话（只收藏其中一个）做出**决定性对照**（`favorite=true` → `total=2 / n=1`）；「重启不丢」用**真实进程重启**验证（10/10 项一致，且新进程把追问「它有哪些禁忌？」改写为「四君子汤有哪些禁忌」——历史只能来自 DB）；浏览器内以真实点击跑通侧栏全部交互。存在 3 项**非阻断**限制（§5）。

> **本文档已随终审修复轮更新（终审 4 Important + 1 Minor，6 个提交 `daf04db..6dcbc43`）。**
> §1 门禁数字、§4 的侧栏视觉与回放行为均为**修复终点重测值**，非 Task 8 当时的旧值。
> 修复内容见 §4-A；相应地 pytest 由 195 升至 **197**、`def test_` 由 178 升至 **180**。

---

## 0. 实测口径

| 项 | 值 |
|---|---|
| 后端 | `cd backend && .venv/Scripts/python -m uvicorn app.main:app --host 127.0.0.1 --port 8000`（无 `--reload`，确保测的是工作树而非陈旧进程） |
| 前端 | `cd web && npm run dev`（5173 被另一会话占用，本轮另起 5175） |
| 后端客户端 | httpx（规避 Windows Git Bash 下中文 JSON 的 body 编码损坏） |
| 浏览器 | 预览面板桌面 Chrome，`preview_click` 真实点击；未使用 mock |
| 真实消耗 | 问答流式 **7 轮**（建 2 会话 + 3 次追问 + 重启前后各 1 次）+ 1 次图谱/向量检索 |

**关键设计**：两条主张刻意做成可判别对照，避免「跑通了」的假象——
1. **筛选语义**：只造一个会话时 `total` 与 `favorite_total` 恒等，「筛选下 `total` 是不是全部会话数」无法判别；故造两个会话、只收藏其一。
2. **持久化**：只查库不足以证明「历史真的来自 DB」；故**杀掉后端进程并重启**，再让新进程处理一次省略主语的追问。

---

## 1. 门禁 —— ✓ 通过

> 下表中的数字为**终审修复轮之后的修复终点（HEAD `6dcbc43`）重测值**；Task 8 当时的旧值列在末列以便对照。

| 项 | 命令 | 修复终点重测 | （Task 8 旧值） |
|---|---|---|---|
| 后端回归 | `cd backend && .venv/Scripts/python -m pytest -q` | **`197 passed, 463 warnings in 6.92s`**（exit 0） | 195 passed, 10.92s |
| 类型检查 | `cd web && npm run type-check` | `vue-tsc --noEmit` → **exit 0，零错误** | exit 0 |
| 生产构建 | `cd web && npm run build` | **exit 0**，`✓ built in 20.51s` | exit 0, 27.96s |

阶段 5 基线 169 → **新增 28 条收集用例**，`def test_` 函数 162 → **180**。

构建体积：`index-j7ChDM3d.js` **1210.03 kB**（阶段 5 基线 1209.95 kB，**+0.08 kB**）、`echarts-CmtS_fMb.js` 563.00 kB——两个 >500 kB 警告为**既有基线**，非本分支引入；本分支新增的 `Chat-BYivvf-p.js` 为 **17.40 kB**（含侧栏组件；Task 8 时为 17.12 kB，+0.28 kB 来自本轮侧栏图标的 `::before`/`::after` 规则）。

新增测试文件 3 个（`test_chat_models.py` 1 例、`test_chat_sessions_api.py` **7 例**、`test_chat_sessions_service.py` 7 例），改写 3 个既有文件（`test_chat_stream.py` 7→**11** 例、`test_memory.py` 4→3 例、`test_retrieval_log.py` 4→4 例）。

---

## 2. API 级验收 —— ✓ 全部通过

脚本 `.superpowers/sdd/2026-09-16-chat-session-list/api-acceptance.py` 实跑原文输出：

```
[0] 前置 清空后 total=0
[1] 鉴权  no-auth: /chat/stream=401 /chat/sessions=401 | with-auth: /chat/sessions=200
[2] SSE  steps=4 轨迹=['understand', 'retrieve', 'fuse', 'rerank']
    retrieve: vector_n=13 keyword_n=0 graph_n=8 | done.metrics={'vector_n': 13, 'graph_n': 8, 'evidence_n': 5, 'reflect_count': 0}
[3] 追问  session_id 复用=True | raw='它有哪些禁忌？' rewritten='四君子汤有哪些禁忌？'  -> 历史进 LLM
[4] 列表  total=2 favorite_total=0 | 每会话 [id8, 条数, 时区后缀]=[('7117b841', 2, 'Z'), ('1e8367f7', 4, 'Z')]
    条数=[2, 4]（2 问 2 答）| 全部 updated_at 以 Z 结尾=True | 最新在前=True
[5] 收藏筛选  favorite=true: total=2 n=1 | favorite=false: total=2 n=2
    -> 筛选下 total 仍为全部会话数=True（若把 total 改成 len(sessions) 会退化成 1）
    已收藏项=['1e8367f7']，且 favorite_total=1
[6] 回放  n=4 seq/role=[(1, 'user'), (2, 'assistant'), (3, 'user'), (4, 'assistant')] | user payload=None | assistant payload keys=['graph_facts', 'references', 'safety', 'trace']
    正文全非空=True | 图谱事实=8 条 | 参考文献=5 条 | 思考步骤=4 步 | safety=None
[7] 越权  user1 GET=404 PATCH=404 DELETE=404 | admin 该会话仍收藏=True（越权未生效）
[8] 删除  DELETE=200 重复 DELETE=404 再读消息=404 | 列表 total=1 n=1（另一会话不受影响=True）
[9] 级联  已删会话的会话行=0 消息行=0 | 全库孤儿消息=0
[清] 清掉收尾会话 1 条 -> 剩余 total=0
```

逐条对应规格要求：

| # | 规格要求 | 实测 |
|---|---|---|
| [1] | `/api/chat/stream` 强制鉴权 | 无凭证 **401**，带凭证 200；`/api/chat/sessions` 同 |
| [2] | 问答落库 + `done` 回执会话 id | 4 步轨迹，`done.metrics` 与 SSE `retrieve` 事件一致；`done.message_id` 即后端建会话 id |
| [3] | 追问复用同一会话、历史进 LLM | 同一 `session_id`；改写把「它」补成「四君子汤」 |
| [4] | 列表：总数 / 收藏数 / 条数 / 倒序 | `total=2 favorite_total=0`；`message_count` 2/4；最新在前 |
| [5] | 收藏筛选下 `total` 语义 | **决定性**：`favorite=true` 时 `total=2` 而 `n=1` |
| [6] | 回放四段完整 | `payload` 键 = `graph_facts / references / safety / trace`；用户消息 `payload=None` |
| [7] | 跨用户隔离 | 读/改/删三种路径**全部 404**，且被攻击会话收藏标记未被改动 |
| [8] | 删除幂等 | 首次 200、重复 404、再读消息 404，另一会话不受影响 |
| [9] | 级联删除 | 会话行 0、消息行 0、**全库孤儿消息 0** |

时间戳时区：`updated_at` 一律以 `Z` 结尾（`2026-09-16T12:22:12Z`）。这一点在浏览器侧有强佐证——侧栏渲染出「1分钟前」，若 `Z` 被剥掉，本地 UTC+8 会读成 8 小时偏差。

> **[6] 的 `safety=None` 说明**：本轮两问均为知识库命中路径，`safety_flag` 非 emergency/low_confidence，故按设计不落 safety 载荷。低置信兜底话术（「知识库未检索到可靠依据」）与急症强制就医提示属阶段 3/4 既有行为，本分支未改动；早前一轮追问命中 `rerank.status=知识库未匹配`（docs=0 / graph_facts=8）时，前端以框渲染兜底话术并**未编造**，行为与本分支无关，此处仅作观察记录。

---

## 3. 重启持久化 —— ✓ 通过（本分支核心主张）

脚本 `.superpowers/sdd/2026-09-16-chat-session-list/restart-check.py`（两阶段，中间**真实杀掉进程**：`Stop-Process -Id 71888` → 确认端口释放 → 重新拉起 uvicorn）。

重启后 10/10 项一致：

```
  会话仍在列表                     OK
  收藏标记仍在                     OK
  消息条数一致                     OK
  回放条数一致                     OK
  payload 四段键一致              OK
  图谱事实数一致                    OK
  参考文献数一致                    OK
  思考步骤数一致                    OK
  正文可回放(首条含四君子汤)             OK
  重启后追问仍复用该会话                OK
```

**决定性证据**（`.superpowers/sdd/…/rewrite-after-restart.py`，新进程、无内存）：

```
重启后追问  session=d1f59687abdd4a7892a3c0d13ec2ed68
  raw       = '它有哪些禁忌？'
  rewritten = '四君子汤有哪些禁忌'
  entities  = ['四君子汤']
  -> 历史来自 DB：True
```

新进程对省略主语的追问仍能补出「四君子汤」，而该信息只能取自 DB 里的历史消息——设计文档的核心主张成立。

---

## 4. 浏览器实测 —— ✓ 通过（真实点击）

| 检查项 | 实测结果 |
|---|---|
| 分栏几何 | 侧栏 282px / 问答区 884px / 间距 14px / **无横向溢出**（958px 面板宽度下） |
| 规格文案 | 区标题「问答会话」、统计「N 个历史会话 · M 个收藏」、「+ 新对话」绿色填充、页签「全部 N」「已收藏 M」 |
| 会话项 | 标题超长省略、元信息「1分钟前 · 4条」、★ 取 `theme.colorWarning`、⋯ 与 ☆ **静止态均可见**（与参考截图一致）；每项最左为**圆形描边气泡图标**（见 §4-A） |
| 筛选页签形态 | **浅灰分段轨道 + 白色选中药丸**（整体满宽、贴卡片内缘），而非绿边绿字独立按钮（见 §4-A） |
| **历史回放** | 点会话项 → `qaItems=2`、空态消失、`.sl-item.on` 高亮 1 项；**四段齐备**：思考过程 2 块、图谱依据 2 块（共 16 行）、证据来源 1 块（5 行）、safety 框 2 个、反馈按钮 2 组、溯源按钮可用。**回放与实时的两条一致性规则见 §4-A** |
| 收藏切换 | 点 ☆：★→☆，统计「1 个历史会话 · **0 个收藏**」，页签计数同步；再点回 ★ 恢复 |
| 收藏筛选 | 点「已收藏」→ 页签 ON、列表仍 1 条、**问答区与选中高亮保留**（切筛选不打断回放） |
| 「+ 新对话」 | `qaItems=0`、空态引导出现、**侧栏历史仍在**、无选中高亮 |
| ⋯ 菜单文案 | 已收藏会话显示「取消收藏」、未收藏会话显示「收藏」（随状态动态） |
| 删除确认 | 弹窗标题「删除确认」、正文「确定删除会话「四君子汤由哪些中药组成？」？该操作不可恢复。」、按钮「取消 / 删除」 |
| 删除生效 | 行消失、统计「0 个历史会话 · 0 个收藏」、页签归零 |
| **删除当前激活会话** | 问答区复位为空态引导（`onDeleted` → `newSession()`），高亮清除——本条是 Task 7 接线里唯一无法靠 API 覆盖的分支 |
| 空态文案两分支 | 「全部」下 =「暂无历史会话」；「已收藏」下 =「暂无收藏的会话」（两分支均实测） |
| 控制台 | **error 级 0 条**（仅既存的 `el-link` 弃用警告，属未触碰页面） |
| 网络 | 全程 200、无失败请求；序列：`?favorite=false` 首屏 → `/{id}/messages` 选中 → `PATCH ×2`（收藏开/关）→ `DELETE` → 每次变更后 `refresh()`，切页签触发 `?favorite=true` |

---

## 4-A. 终审修复轮的实机复测 —— ✓ 通过

终审（全分支）判 **With fixes**：0 Critical / 4 Important / 7 Minor。4 项 Important 加 1 项 Minor 以 6 个提交修复（`daf04db` I-1/I-2、`3c3d8c8` I-4、`1253f9c` I-3/M-1、`26171ef` 图标补三点、`77fb7cb` 图标按比例缩小、`6dcbc43` 轨道改满宽），定点复审裁决 **CLEAN**。

### 被修的两个缺陷（均为「回放 ≠ 实时」）

| # | 缺陷 | 根因 |
|---|---|---|
| I-1 | 低置信兜底话术在回放时**渲染两遍** | 后端把兜底话术**同时**写进 `content` 与 `safety.message`；实时态靠「无 token → `answer` 为空」抑制正文，而回放态直接 `answer: a?.content`，无此判据 |
| I-2 | 回放时流程条第 5 步「生成回答」**永远不亮** | 实时态在首个 token 到达时合成 `{step:'generate'}` 推入 `trace`；后端**没有任何节点发该步**，落库 `payload.trace` 只有 4 步 |

### 复测方法（决定性对照，非「跑通了」）

用 `replay-fixture.py` 建**两条可判别会话**——A 知识库命中（有正文、`payload.trace` 4 步且**不含** `generate`）、B 低置信拒答（`safety.type='low_confidence'`，且 `content == safety.message`，正是会被渲染两遍的那句）。后端以**修复后的代码**重启（先杀掉跑着修复前代码的 8000 进程），前端临时 5175 dev server，浏览器内以 `preview_click` **真实点击**侧栏会话项。

| 检查项 | 实测结果 | 修复前的表现 |
|---|---|---|
| **I-2** 打开会话 A → 展开思考过程 | `.trace-steps .step` = **5 个**：「问句理解[done] / 多路检索[done] / 证据融合[done] / 相关性排序[done] / **生成回答[active]**」 | 只有 4 个，第 5 步永远灰 |
| **I-1** 打开会话 B → 统计兜底话术出现次数 | 全 `.chat-wrap` 文本中出现 **1 次**；`.answer-text` 节点数 = **0**；该 1 次位于 `.safety-box.warn` | 出现 **2 次**（安全框 + 正文各一次） |
| 正常路径未被误伤 | 会话 A 的 `.answer-text` = 「四君子汤由人参、白术、茯苓、炙甘草四味药组成 [1][2]。」 | — |
| **I-4** 气泡图标 | `.sl-item-icon` 16×16（描边 1.5px）/ 圆内三枚 2px 点 · `box-shadow` 偏移 3px、6px / 左下尾巴 4×4 · `left:1px` · `bottom:-1.5px`；实渲染读作「圆环 + ⋯ + 左下小尾巴」 | 无该图标 |
| **I-4** 分段页签 | `.sl-tabs` 计算值 `padding:10px` / `margin:0 0 10px` / `gap:6px` / `border-radius:0`，底色 `rgb(245,247,245)` = `theme.pageBg`；实测轨道 **x=241..521**，卡片 x=240 宽 282（含 1px 边框）⇒ **左右各距卡片内缘 0px（满宽）**；选中药丸底色 `theme.cardBg` | `margin: 0 14px`（左右各 14px 白边）、绿边绿字独立按钮 |
| 控制台 / 网络 | error 级 **0 条**；失败请求 **0 条** | — |

**几何取值依据**：气泡图标尺寸与页签轨道几何不是目测定的，而是先用**卡片宽度**标定参考截图的缩放（侧栏白区 223 截图 px ↔ 本项目 `session-list` 280 CSS px ⇒ **缩放 1.256**），再把截图实测值换算成 CSS 目标值。该模型用两项**未参与标定**的量做了交叉验证（标题墨迹 10px→12.6px vs 实现 13px 字号；元信息 9px→11.3px vs 实现 12px 字号），误差均在 0.5px 内。图标 16px 由截图 13×10px → 16.3×12.6px 得出，实现者另用实机 14/16/18px 三档对比独立确认 16px 是「圆内三点仍清晰可辨的最小值」。

### 本轮未采纳的复审观察（已在 SDD 台账逐条裁决）

- **I-1/I-2 无自动化测试覆盖，且当前做不了**——`web/package.json` 无前端测试框架。为一个 10 行渲染分支引入 vitest 基建超出本任务范围；本轮改以浏览器实机给出决定性对照（1 次 vs 2 次）。**这是一个已知的回归缺口**，已记入 §5 而非静默放过。
- 合成 `generate` 的判据现以并行条件式存在于实时（`Chat.vue:125-129`）与回放（`:69`）两处，未抽公共 helper：两处**触发时机**不同（首个 token 到达 vs 构建 QA 对象），抽取需引入上下文参数，反而耦合两条独立时序。
- `test_chat_stream.py` 的 `_done_session_id` 助手与另一用例的内联 done 解析重复（3 行测试代码），未合并以免扩大 diff。

---

## 5. 未覆盖与限制（非阻断）

**L1 — 文本框输入发送路径本轮未在浏览器复验。** 预览面板的 `preview_fill` 只写 DOM `value` 而不派发 Vue 的 `input` 事件，`send()` 因 `input.value` 为空而早退（工具侧副作用，非应用缺陷）。本轮浏览器内的会话创建与流式渲染未再走该路径；流式协议本身已在 §2 以 API 级完整覆盖，回放渲染已由 §4 覆盖。**若需闭环，请在浏览器手动键入一次问题确认。**

**L2 — 极窄视口下布局塌陷。** 预览面板宽度一度降至 279px：应用自身左导航占满后，侧栏项落在 x=251..511（超出可视区），问答区被 `.session-list`（固定 281.6px，`flex-shrink:0`）压成 1.6px。这是**桌面控制台设计目标的既有假设**（规格与参考截图均为 1440 宽），非本分支引入，且不影响 958px 及以上宽度的渲染。本轮以 `document.body.style.zoom='0.5'` 把布局压进可视区后完成真实点击。

**L3 — 流式进行中删除「当前激活会话」的边界**（台账 Task 7 minor 已裁为可接受）：需在流式期间完成二次确认弹窗，不损坏落库数据，下次 select / 新对话自愈。本轮未复现该竞态。

**L4 — 回放的「实时一致性」两条规则无自动化测试兜底（已知回归缺口）。** I-1（低置信抑制正文）与 I-2（合成 `generate` 步）修的是「同一份落库数据在实时态与回放态渲染不一致」，但 `web/package.json` 只有 `dev`/`build`/`preview`/`type-check`，**没有前端测试框架**，因此这两条规则只能靠 §4-A 的浏览器实机对照守住，无法在 CI 里自动变红。将来若有人重构 `Chat.vue` 的 `openSession`，两条规则可能再次漂移而**不会触发任何红灯**。补测需要先引入前端测试基建（vitest + 组件测试），超出本分支范围。**已显式记账，非遗漏。**

---

## 6. 复现方式

```bash
cd backend && .venv/Scripts/python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

```bash
cd backend && .venv/Scripts/python -m pytest -q
```

```bash
PYTHONIOENCODING=utf-8 .venv/Scripts/python ../.superpowers/sdd/2026-09-16-chat-session-list/api-acceptance.py
```

```bash
PYTHONIOENCODING=utf-8 .venv/Scripts/python ../.superpowers/sdd/2026-09-16-chat-session-list/restart-check.py before
```

§4-A 的回放对照（造 A 正常命中 / B 低置信两条会话后，在浏览器里各点一次）：

```bash
PYTHONIOENCODING=utf-8 .venv/Scripts/python ../.superpowers/sdd/2026-09-16-chat-session-list/replay-fixture.py
```

> 脚本位于 `.superpowers/sdd/2026-09-16-chat-session-list/`（git-ignored 临时工作区）。`api-acceptance.py` 会在开头清空 admin 的历史会话、结尾清理残留，可重复跑；`restart-check.py before` 与 `after` 之间须手动重启后端进程；`replay-fixture.py` 同样先清场、并打印两条会话各自的 `content` / `trace` / `safety`，用于在浏览器里核对「A 有 5 步、B 只出现 1 次兜底话术」。

**环境已还原**：验收与复测产生的会话全部删除（`total=0 / favorite_total=0`），`.claude/launch.json` 的临时 5175 条目已 `git checkout` 还原为提交态（`git status --short .claude/launch.json` 无输出），临时 5175 Vite 服务已停止，浏览器侧施加的 `body.style.zoom` 与 `scrollLeft` 已复位（仅存在于已关闭的页面）。**后端 8000 进程（跑的是修复终点代码）保留在运行中**，便于你手动复验；不需要时可直接结束该 uvicorn 进程。

工作树状态：`.claude/launch.json` 之外的仅有三处**未跟踪**文件——本分支的 spec 目录 `docs/superpowers/specs/`、实施计划 `docs/superpowers/plans/2026-09-16-chat-session-list.md`、以及本文档。前两者按你「文档不用提交」的指示未提交；本文档的处理见交付说明。
