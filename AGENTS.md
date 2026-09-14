# MediRAG「本草智问」Agent 宪法

> 项目级配置，优先级高于用户全局配置。通用工程纪律继承自 `~/.claude/AGENTS.md`（通用 Agent 宪法），本文件只做适配与细化，不削弱核心原则。

## 项目定位

**MediRAG「本草智问」**：中医药 Agentic RAG 问答系统（个人项目，对口 Python Agent 开发实习）。
将网上找到的「Spring Boot 3 + LangChain4j + Vue3」固定管道 RAG 项目，改造为 Python 技术栈的 Agentic RAG。**原项目无源码**，前端按 8 张截图 1:1 仿制，后端从零实现，数据自建替代。

## 真源入口

- **总方案**：`docs/MediRAG-合并改造方案.md`（架构、SSE 协议、阶段计划、技术选型的唯一主线）
- **前端唯一验收真源**：`docs/前端还原规格.md`（布局/配色/文案逐项对照，与截图不符即缺陷）
- **数据**：`data/corpus/`（文献语料）、`data/graph/`（图谱 seed）、`data/eval/`（Golden QA 评测集）
- 真源冲突时：当前源码与测试 > 本文件 > 合并改造方案 > 前端还原规格 > 其余 docs

## 技术栈

| 层 | 选型 |
|---|---|
| 后端 | Python 3.12 + FastAPI + pydantic-settings + pytest |
| Agent/LLM | LangChain + LangGraph（阶段 3 引入）；DeepSeek 主力 / Qwen 备用（`.env` 切换） |
| Embedding/Rerank | SiliconFlow API（bge-m3 1024 维 / bge-reranker-v2-m3），可切 local |
| 向量库 | 当前 `numpy_local`（Windows 无 milvus-lite），接口已对齐 Milvus schema，后续换 Milvus standalone |
| 图谱/业务库 | Neo4j 5.20（`deploy/docker-compose.yml`）+ MySQL 8.4（宿主 3307） |
| 前端 | Vue 3 + Vite + TypeScript + Pinia + Vue Router + Element Plus + ECharts |

## 项目边界（goal / non-goal）

**做**：Agentic RAG（LangGraph 状态机 + 三检索 Tool + 受控自反思）、三路混合检索 + RRF + Rerank、医疗安全双层兜底（急症拦截 + 低置信拒答）、来源可追溯（文档/章节/页码 + 图谱路径）、RAGAS 评测闭环、前端按截图 1:1 还原。

**不做**（方案第十一节已否定，禁止带回）：模型微调/LoRA、多模态/数字人、多 Agent 协作作为主线、Go/Java 双实现、用户系统精化（P2 边角）、独立「Agent 推理面板」（Agent 轨迹收纳于既有溯源弹窗）。

## 关键命令

```bash
# 后端测试（backend/ 下，无需网络与中间件，LLM 调用全部 monkeypatch）
cd backend && .venv/Scripts/python -m pytest

# 后端启动
cd backend && .venv/Scripts/python -m uvicorn app.main:app --port 8000

# 语料入库（向量化写入 data/vectorstore/index.json）
cd backend && .venv/Scripts/python -m app.ingestion.pipeline

# 前端启动 / 构建
cd web && npm run dev        # http://localhost:5173，/api 代理到 8000
cd web && npm run build

# 中间件（Neo4j + MySQL；Redis 为 P1 可选）
docker compose -f deploy/docker-compose.yml up -d
```

## 分层与 Owner

- 检索语义（向量/BM25/RRF/Rerank）owner：`backend/app/retrieval/`
- LLM 与 Embedding 适配 owner：`backend/app/llm/`（统一 OpenAI 兼容接口，业务代码禁止直连厂商 SDK）
- Agent 编排 owner：`backend/app/agent/`（阶段 3 建设：workflow/state/tools/prompts）
- 图谱访问 owner：`backend/app/graph/`（阶段 2 引入 Neo4j client）
- API 层只做协议映射与接线，不拥有业务语义；Prompt 模板集中在 `agent/prompts/`
- 前端设计 token 唯一来源：`web/src/styles/theme.ts` + `docs/前端还原规格.md`，组件内禁止写死色值

## 项目专项规则

- **数字必须实测**：简历与文档中的评测数字只能来自阶段 6 评测脚本实跑，严禁编造。
- **医疗安全兜底不可绕过**：证据不足必须拒答"知识库未检索到可靠依据"，宁可说不知道也不编造；急症词命中必须强制就医提示。
- **密钥纪律**：`.env` 已被 `.gitignore` 排除，禁止提交、禁止写入日志、禁止出现在交付物中；仓库样板只维护 `.env.example`。
- **测试约定**：pytest 测试不得依赖真实网络/中间件，LLM 与检索依赖用 monkeypatch 隔离（参见 `backend/tests/` 既有模式）。
- **数据「小而真」**：语料/图谱/评测集保持真实可引用，禁止虚构内容充数。
- **Git**：项目根当前未初始化 git；初始化后提交只 stage 与本任务相关文件，禁止 `git add .`。

## 当前阶段

阶段 0（脚手架）与阶段 1（最小 RAG 闭环）已完成：15 个 pytest 用例通过，语料 11 条已入库，前端登录页/主布局/最简对话页可用。

**进行中：阶段 2 —— 三路检索 + RRF + Rerank**（BM25、Neo4j 接入、溯源弹窗），验证标准见合并方案第九节。
