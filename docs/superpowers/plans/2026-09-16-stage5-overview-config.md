# 阶段 5 前端全量还原 + 运行概览/推理配置 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 阶段 5 全部落地——P1 两页（运行概览 + 推理配置）真实数据闭环、P2 两页（账户管理 + 我的档案）、图谱/文档收尾（re-import、neighbors 去重与 2-hop 过滤、详情/下载/重命名）、工程收尾（ECharts 按需、.gitattributes 行尾）。

**Architecture:** 推理配置从环境变量升级为 **MySQL `inference_config` 表 + 每请求 state 注入**：chat.py 在 initial state 注入建好的配置 dict，understand/retrieve/fuse/chat 各节点从 `state["inference"]` 读取（缺省回落 `get_settings()` 默认值，既有图级测试不破）；`llm/chat.py` 支持按调用指定 vendor/model。运行概览数据全部来自真实统计：问答时写 `retrieval_log`，前端反馈按钮写 `feedback`，用户取自 `users` 表 seed。前端两页用 ECharts 按需引入（core + 具体图表注册），其余 P0 页重构为按需引入以消除 >500kB chunk 警告。

**Tech Stack:** FastAPI / SQLAlchemy 2 / LangGraph 1.2 (state-driven params) / Vue 3 + TS + Element Plus / ECharts 5 按需（`echarts/core` + `LineChart/PieChart/BarChart`）+ CanvasRenderer

**Spec:**
- `docs/前端还原规格.md` — 第二节 P1（运行概览 §P1、推理配置 §P1）、P2（账户管理/我的档案）、P0-5（重新导入基础数据按钮）、P0-6（详情 · 下载 · 重命名操作列）
- `docs/MediRAG-Python改造方案.md` — §6.6 业务表（inference_config / retrieval_log / feedback）、§5.1 运行默认配置、§6.8 评测闭环、阶段 5「前端全量还原」
- 阶段 4 台账 §9：详情/下载/重命名递延登记

## Global Constraints

- **文案以截图为准，不得自造**（前端还原规格）：运行概览卡片标题「问答量趋势／用户角色分布／中医药知识主题分布／知识库状态分布／检索质量统计」，推理配置组名「混合检索组／生成模型组」，按钮「保存本组／恢复全部默认」，生效说明对接「变更保存后将立即应用」。
- **推理配置页默认值=截图**：语义召回数 20、关键词召回数 20、融合候选数 25、最终证据数 5、融合平衡系数 60；对话模型下拉选项 `deepseek-chat` / `qwen-plus`；回答灵活度 0.30、问句理解灵活度 0.10。
- 推理配置**保存即写后端，下一次问答请求生效**；前端保存成功提示不能用自造文案（用规格原句）。
- 问答链路恒定只查 `已发布`（阶段 4 C1 修复后不得回退）；候选边在浏览图/问答中均被过滤。
- 不新增原图不存在的能力面板；有用/无用反馈按钮属回答卡片的轻量操作（支撑运行概览真实数据），不是新面板。
- 用户角色枚举（截图/方案）：`管理员 / 中医药从业者 / 知识用户`。
- ECharts 禁用 `import * as echarts from 'echarts'` 全量引入；一律 `echarts/core` + 按需注册 + CanvasRenderer。
- `inference_config` 落库字段校验范围：`semantic_k/keyword_k/fuse_candidate/final_evidence ∈ [1, 100]`，`rrf_k ∈ [1, 200]`，`answer_temp/query_temp ∈ [0, 2]`，`model ∈ {deepseek-chat, qwen-plus}`；越界 422，文案含字段名。
- 测试一律走无网络路径：LLM/tool 用 monkeypatch；DB 用 `sqlite:///:memory:`（conftest 已注入 StaticPool）。
- 不提交 `.env`、不上传真实密钥；seed 用户密码仅为演示（`admin123`），代码注释注明非生产。
- 前端门禁：`npm run type-check`（vue-tsc）零错误 + `npm run build` 成功；后端 `pytest -q` 全绿。
- 模块间不得循环导入；`db.py` 的 `init_db()` 需注册所有新模型（import 触发）。

---

## 文件结构总览

**后端新增：**
- `backend/app/models/inference_config.py` — InferenceConfig（单行全局配置）
- `backend/app/models/retrieval_log.py` — RetrievalLog
- `backend/app/models/feedback.py` — Feedback
- `backend/app/models/user.py` — User
- `backend/app/services/inference_config.py` — 配置加载：DB 行→dict；无行回落 settings 默认
- `backend/app/api/config.py` — GET/PUT `/api/config`
- `backend/app/api/stats.py` — GET `/api/stats/overview`
- `backend/app/api/auth.py` — POST `/api/auth/login`、GET `/api/auth/me`、PUT `/api/auth/password`
- `backend/app/api/users.py` — GET/POST/PUT/DELETE `/api/users`（账户管理）
- `backend/tests/test_config_api.py`、`test_stats_api.py`、`test_auth.py`、`test_users_api.py`、`test_retrieval_log.py`

**后端修改：**
- `backend/app/db.py` — init_db 注册新模型 + seed 默认用户
- `backend/app/llm/chat.py` — `_endpoint`/`chat_completion`/`chat_completion_stream` 支持 vendor/model 覆盖参数
- `backend/app/agent/nodes/understand.py` — 温度/模型从 `state["inference"]` 读
- `backend/app/agent/nodes/retrieve.py` — top_k 从 `state["inference"]` 读
- `backend/app/agent/nodes/fuse.py` — rrf_k/fuse_candidate/rerank_top_n/evidence_min_score 从 `state["inference"]` 读
- `backend/app/api/chat.py` — 注入 inference、生成用 answer_temp/model/vendor、done 前写 retrieval_log
- `backend/app/api/graph_api.py` — POST `/graph/import`（re-import seed）；neighbors 遍历去重 + 2-hop 过滤
- `backend/app/api/documents.py` — 详情/下载/重命名端点
- `backend/app/main.py` — 挂载新 router

**前端新增：**
- `web/src/api/config.ts`、`stats.ts`、`auth.ts`、`users.ts`
- `web/src/views/overview/Dashboard.vue` — 运行概览（5 卡）
- `web/src/views/config/Inference.vue` — 推理配置
- `web/src/views/account/Accounts.vue`、`Profile.vue`
- `web/src/utils/echarts.ts` — 按需注册（Line/Pie/Bar + Grid/Tooltip/Legend/Title + Canvas）

**前端修改：**
- `web/src/router/index.ts` — overview/inference/account/profile 指向真实页（已留路由占位）
- `web/src/views/knowledge/Library.vue` — 操作列加 详情/下载/重命名
- `web/src/views/graph/GraphExplore.vue` — 顶部「重新导入基础数据」接线；ECharts 按需
- `web/src/views/qa/Chat.vue` — 回答卡片底部「有用/无用」反馈按钮
- `web/src/layouts/MainLayout.vue`、`web/src/views/Login.vue` — 登录态接入真实用户
- `web/src/api/documents.ts` — 详情/下载/重命名方法

**仓库级：**
- `.gitattributes` — `* text=auto eol=lf`；`git add --renormalize` 行尾归一（~20 文件 CRLF→LF）

---

## Task 1: 推理配置存储 + 配置 API + 检索/理解节点从 state 读配置

**Files:**
- Create: `backend/app/models/inference_config.py`
- Create: `backend/app/services/inference_config.py`
- Create: `backend/app/api/config.py`
- Create: `backend/tests/test_config_api.py`
- Modify: `backend/app/db.py`（init_db 导入新模型）
- Modify: `backend/app/main.py`（挂载 config router）
- Modify: `backend/app/llm/chat.py`（vendor/model 覆盖参数）
- Modify: `backend/app/agent/nodes/understand.py`、`retrieve.py`、`fuse.py`（读 `state["inference"]`）

**Interfaces:**
- Consumes: `get_settings()`（config.py 现有默认值）；`session_scope`（db.py）；`Database`（models 模式参考 `document.py`）
- Produces: 模型字段与 settings 同名（semantic_k/keyword_k/fuse_candidate/final_evidence/rrf_k/model/answer_temp/query_temp，均为 Mapped[int|float|str]）；`load_inference_config() -> dict`（参数齐全的 dict，未存行时用 settings 值）；`GET /api/config -> {"items": {...}}`、`PUT /api/config {body 同名字段} -> 保存后全量 dict`；`llm.chat_completion(..., vendor=None, model=None)`；节点侧 `_cfg(state)` 辅助读取逻辑（vendors 后续任务复用）

- [ ] **Step 1: 写失败测试 `test_config_api.py`**

```python
"""推理配置 API：默认值=截图值；保存即写库；越界 422；再保存覆盖。"""
import pytest
from sqlalchemy import select

from app.db import session_scope
from app.models.inference_config import InferenceConfig


def test_get_default_matches_spec(client):
    r = client.get("/api/config")
    assert r.status_code == 200
    d = r.json()["items"]
    assert d["semantic_k"] == 20 and d["keyword_k"] == 20
    assert d["fuse_candidate"] == 25 and d["final_evidence"] == 5
    assert d["rrf_k"] == 60
    assert d["model"] == "deepseek-chat"
    assert d["answer_temp"] == 0.3 and d["query_temp"] == 0.1


def test_put_persists_and_overrides(client):
    body = {"semantic_k": 12, "keyword_k": 8, "fuse_candidate": 30,
            "final_evidence": 3, "rrf_k": 50, "model": "qwen-plus",
            "answer_temp": 0.7, "query_temp": 0.2}
    r = client.put("/api/config", json=body)
    assert r.status_code == 200
    assert r.json()["semantic_k"] == 12 and r.json()["model"] == "qwen-plus"
    # 再次 GET 仍为保存值（已写库，非内存一次性）
    assert client.get("/api/config").json()["items"]["semantic_k"] == 12
    # 覆盖保存
    body["semantic_k"] = 15
    assert client.put("/api/config", json=body).status_code == 200
    assert client.get("/api/config").json()["items"]["semantic_k"] == 15
    # 落库断言
    with session_scope() as s:
        row = s.execute(select(InferenceConfig)).scalar_one()
        assert row.semantic_k == 15 and row.model == "qwen-plus"


@pytest.mark.parametrize("field,bad", [
    ("semantic_k", 0), ("semantic_k", 101), ("keyword_k", -1),
    ("fuse_candidate", 0), ("final_evidence", 200), ("rrf_k", 0),
    ("answer_temp", 2.1), ("query_temp", -0.1), ("model", "gpt-4"),
])
def test_put_rejects_out_of_range(client, field, bad):
    full = {"semantic_k": 20, "keyword_k": 20, "fuse_candidate": 25,
            "final_evidence": 5, "rrf_k": 60, "model": "deepseek-chat",
            "answer_temp": 0.3, "query_temp": 0.1}
    full[field] = bad
    r = client.put("/api/config", json=full)
    assert r.status_code == 422
    assert field in r.json()["detail"]
```

- [ ] **Step 2: 运行确认失败**

Run: `cd backend && .venv/Scripts/python -m pytest tests/test_config_api.py -v`
Expected: 全部 FAIL（404 / ModuleNotFoundError: InferenceConfig）

- [ ] **Step 3: 写 `models/inference_config.py`（参照 `models/document.py` 风格）**

```python
"""InferenceConfig：全局单行推理配置（阶段 5 推理配置页落库；方案 6.6）。"""
from sqlalchemy import Float, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class InferenceConfig(Base):
    __tablename__ = "inference_config"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    semantic_k: Mapped[int] = mapped_column(Integer, default=20)   # 语义召回数
    keyword_k: Mapped[int] = mapped_column(Integer, default=20)    # 关键词召回数
    fuse_candidate: Mapped[int] = mapped_column(Integer, default=25)  # 融合候选数
    final_evidence: Mapped[int] = mapped_column(Integer, default=5)   # 最终证据数
    rrf_k: Mapped[int] = mapped_column(Integer, default=60)       # 融合平衡系数
    model: Mapped[str] = mapped_column(String(32), default="deepseek-chat")
    answer_temp: Mapped[float] = mapped_column(Float, default=0.3)
    query_temp: Mapped[float] = mapped_column(Float, default=0.1)
```

- [ ] **Step 4: 写 `services/inference_config.py`（加载 + 校验 + 保存）**

```python
"""推理配置即服务：DB 单行 ↔ dict；未落库时回落 get_settings() 默认（与截图一致）。"""
from sqlalchemy import select

from app.config import get_settings
from app.db import session_scope
from app.models.inference_config import InferenceConfig

MODEL_FIELD_RANGES = {
    "semantic_k": (1, 100), "keyword_k": (1, 100), "fuse_candidate": (1, 100),
    "final_evidence": (1, 100), "rrf_k": (1, 200),
}
TEMP_FIELDS = ("answer_temp", "query_temp")
MODELS = {"deepseek-chat", "qwen-plus"}


def defaults() -> dict:
    s = get_settings()
    return {"semantic_k": s.semantic_k, "keyword_k": s.keyword_k,
            "fuse_candidate": s.fuse_candidate, "final_evidence": s.final_evidence,
            "rrf_k": s.rrf_k, "model": "deepseek-chat",
            "answer_temp": 0.3, "query_temp": 0.1}


def load_inference_config() -> dict:
    """返回带全部字段的配置 dict；无存行时回落 settings 默认。"""
    with session_scope() as s:
        row = s.execute(select(InferenceConfig)).scalar_one_or_none()
    if row is None:
        return defaults()
    return {"semantic_k": row.semantic_k, "keyword_k": row.keyword_k,
            "fuse_candidate": row.fuse_candidate, "final_evidence": row.final_evidence,
            "rrf_k": row.rrf_k, "model": row.model or "deepseek-chat",
            "answer_temp": row.answer_temp, "query_temp": row.query_temp}


def validate(body: dict) -> None:
    """校验范围；违规抛 ValueError（detail 含字段名）。"""
    for f, (lo, hi) in MODEL_FIELD_RANGES.items():
        v = body.get(f)
        if not isinstance(v, int) or not (lo <= v <= hi):
            raise ValueError(f"{f} 取值 {lo}~{hi}")
    for f in TEMP_FIELDS:
        v = body.get(f)
        if not isinstance(v, (int, float)) or not (0 <= v <= 2):
            raise ValueError(f"{f} 取值 0~2")
    if body.get("model") not in MODELS:
        raise ValueError("model 取值 deepseek-chat|qwen-plus")


def save_inference_config(body: dict) -> dict:
    validate(body)
    with session_scope() as s:
        row = s.execute(select(InferenceConfig)).scalar_one_or_none()
        if row is None:
            row = InferenceConfig(id=1)
            s.add(row)
        for k in defaults():
            setattr(row, k, body[k])
    return body
```

- [ ] **Step 5: 写 `api/config.py` 并挂载**

```python
"""推理配置 API：GET 当前生效值 / PUT 保存（下一次问答请求生效）。"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.services.inference_config import (defaults, load_inference_config,
                                           save_inference_config)

router = APIRouter()


class ConfigBody(BaseModel):
    semantic_k: int
    keyword_k: int
    fuse_candidate: int
    final_evidence: int
    rrf_k: int
    model: str
    answer_temp: float
    query_temp: float


@router.get("/config")
def get_config() -> dict:
    return {"items": load_inference_config()}


@router.put("/config")
def put_config(body: ConfigBody) -> dict:
    try:
        return save_inference_config(body.model_dump())
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
```

`main.py`：`from app.api.config import router as config_router` → `app.include_router(config_router, prefix="/api")`；`db.py` 的 `init_db` 里 `from app.models import document, inference_config`（register）。

- [ ] **Step 6: 节点/LLM 从 state 读配置（三个文件各改一处）**

`understand.py` 找到 `chat_completion(system=..., user=prompt, temperature=0.1)`：

```python
    cfg = state.get("inference") or {}
    query_temp = float(cfg.get("query_temp", 0.1))
    raw = chat_completion(system="你是中医药问句理解器，只输出 JSON。", user=prompt,
                          temperature=query_temp,
                          vendor=cfg.get("vendor"), model=cfg.get("model"))
```

`retrieve.py` 中 `s.semantic_k / s.keyword_k` 两处：

```python
    cfg = state.get("inference") or {}
    vector_hits = TOOLS["vector_search"].invoke({"query": state["rewritten_query"],
                                                 "top_k": cfg.get("semantic_k", s.semantic_k)}) \
        if "vector_search" in plan else []
    keyword_hits = TOOLS["keyword_search"].invoke({"query": state["rewritten_query"],
                                                   "top_k": cfg.get("keyword_k", s.keyword_k)}) \
        if "keyword_search" in plan else []
```

`fuse.py` 中 `s.rrf_k / s.fuse_candidate / s.rerank_top_n / s.evidence_min_score` 四处：读取 `cfg = state.get("inference") or {}` 后改为 `cfg.get("rrf_k", s.rrf_k)`、`cfg.get("fuse_candidate", s.fuse_candidate)`、`cfg.get("rerank_top_n", s.rerank_top_n)`、`cfg.get("evidence_min_score", s.evidence_min_score)`。

`llm/chat.py`：`_endpoint(vendor=None, model=None)`、`chat_completion(..., vendor=None, model=None)`、`chat_completion_stream(..., vendor=None, model=None)` 透传：

```python
def _endpoint(vendor: str | None = None, model: str | None = None) -> tuple[str, str, str]:
    """返回 (base_url, api_key, model)；vendor/model 显式覆盖 settings（推理配置页切模型）。
    model="qwen-plus" → vendor=qwen；model="deepseek-chat" → vendor=deepseek。"""
    s = get_settings()
    if model == "qwen-plus":
        vendor = "qwen"
    elif model == "deepseek-chat":
        vendor = "deepseek"
    vendor = vendor or s.llm_vendor
    if vendor == "qwen":
        if not s.dashscope_api_key:
            raise RuntimeError("DASHSCOPE_API_KEY 未配置（LLM_VENDOR=qwen）")
        return s.dashscope_base_url, s.dashscope_api_key, model or s.llm_model_alt
    if not s.deepseek_api_key:
        raise RuntimeError("DEEPSEEK_API_KEY 未配置，请在 backend/.env 填入")
    return s.deepseek_base_url, s.deepseek_api_key, model or s.llm_model_main
```

`chat_completion`/`chat_completion_stream` 签名各加 `vendor: str | None = None, model: str | None = None`，内部 `base_url, api_key, model = _endpoint(vendor=vendor, model=model)`。

- [ ] **Step 7: 全量回归**

Run: `cd backend && .venv/Scripts/python -m pytest -q`
Expected: 全部通过（既有 test_retrieve_fuse.py / test_understand.py 走无 `inference` state → 回落 settings，不受影响）

- [ ] **Step 8: Commit**

```bash
git add backend/app/models/inference_config.py backend/app/services/inference_config.py \
  backend/app/api/config.py backend/tests/test_config_api.py backend/app/db.py \
  backend/app/main.py backend/app/llm/chat.py backend/app/agent/nodes/understand.py \
  backend/app/agent/nodes/retrieve.py backend/app/agent/nodes/fuse.py
git commit -m "feat(config): 推理配置落库 API + 检索/理解节点按 state 读取"
```

---

## Task 2: retrieval_log 持久化（问答完成写日志）+ feedback API + inference 注入接线

> **Ruling T1-2（评审裁定追加）**：本任务同时完成「推理配置 → state 注入」接线——`chat.py:_initial_state()` 注入 `"inference": load_inference_config()`；生成段温度用 `final["inference"]["answer_temp"]`、传 `model=`（`llm/chat.py` 已支持 vendor/model 覆盖，Task 1 完成）；`AgentState` 声明 `inference: dict`；并增加「初始 state 含 inference」断言。这是「保存即生效」闭环的最后一段。

**Files:**
- Create: `backend/app/models/retrieval_log.py`、`backend/app/models/feedback.py`
- Create: `backend/app/api/feedback.py`
- Create: `backend/tests/test_retrieval_log.py`
- Modify: `backend/app/api/chat.py`（done 前 `_log_retrieval` + 注入 inference + 生成用 answer_temp/model）；`backend/app/agent/state.py`（声明 `inference: dict`）；`backend/app/db.py`（注册模型）；`backend/app/main.py`（挂载 feedback router）

**Interfaces:**
- Consumes: `final` dict（chat.py 生成段已完成）；`load_inference_config()`（Task 1）
- Produces: `RetrievalLog`（id/session_id/intent/vector_n/keyword_n/graph_n/evidence_n/confidence/is_fallback/created_at）；`Feedback`（id/session_id/useful/created_at）；`POST /api/feedback {session_id, useful} -> {"ok": true}`；`_log_retrieval(session_id, final)` 供运行概览统计（Task 3）；`chat.py:_initial_state()` 的返回值含 `"inference": load_inference_config()`；生成分支 temperature 用 `final["inference"]["answer_temp"]` 且传 `model=final["inference"]["model"]`

- [ ] **Step 1: 写失败测试 `test_retrieval_log.py`**

```python
"""问答完成写 retrieval_log；feedback API 落库。"""
import json

from sqlalchemy import func, select

from app.db import session_scope
from app.models.retrieval_log import RetrievalLog
from app.models.feedback import Feedback


def test_chat_stream_writes_retrieval_log(client, monkeypatch):
    from app.agent import workflow
    fake = {"intent": "relation", "plan": ["vector_search"], "vector_hits": [],
            "keyword_hits": [], "graph_facts": [], "fused": [], "evidence": [
                {"chunk_id": "c1", "title": "t", "doc_name": "d", "chapter": "",
                 "page_no": 1, "text": "x", "score": 0.9}],
            "confidence": 0.9, "low_confidence": False, "safety_flag": None,
            "safety_message": "", "prompt": "p", "answer": "a", "trace": [],
            "rewritten_query": "q", "entities": [], "entity_names": [], "reflect_count": 0,
            "session_id": "sess-1", "question": "问", "chat_history": []}
    class FakeGraph:
        def stream(self, initial, stream_mode=None):
            yield {"understand": {"trace": []}}
            yield {"context": {"prompt": "p"}}
            yield {"safety": {"safety_flag": None, "safety_message": ""}}
            yield {"fuse": {"evidence": fake["evidence"], "confidence": 0.9,
                            "low_confidence": False,
                            "trace": [{"step": "rerank"}]}}
    monkeypatch.setattr(workflow, "get_agent", lambda: FakeGraph())
    monkeypatch.setattr("app.api.chat.chat_completion_stream",
                        lambda system, user, temperature=0.3, vendor=None, model=None: iter(["流"]))
    r = client.post("/api/chat/stream",
                    json={"question": "四君子汤由哪些中药组成？", "session_id": "sess-1"})
    assert r.status_code == 200
    with session_scope() as s:
        log = s.execute(select(RetrievalLog)).scalar_one()
        assert log.session_id == "sess-1" and log.intent == "relation"
        assert log.evidence_n == 1
        assert log.is_fallback is False


def test_fallback_marks_is_fallback(client, monkeypatch):
    from app.agent import workflow
    class FakeGraph:
        def stream(self, initial, stream_mode=None):
            yield {"understand": {"trace": []}}
            yield {"context": {"prompt": "p"}}
            yield {"safety": {"safety_flag": "low_confidence",
                              "safety_message": "知识库中未检索到可靠依据",
                              "answer": "知识库中未检索到可靠依据"}}
    monkeypatch.setattr(workflow, "get_agent", lambda: FakeGraph())
    r = client.post("/api/chat/stream", json={"question": "今天北京天气", "session_id": "sess-2"})
    assert r.status_code == 200
    with session_scope() as s:
        log = s.execute(select(RetrievalLog)).scalar_one()
        assert log.session_id == "sess-2"
        assert log.is_fallback is True


def test_feedback_api(client):
    r = client.post("/api/feedback", json={"session_id": "sess-1", "useful": True})
    assert r.status_code == 200
    r = client.post("/api/feedback", json={"session_id": "sess-1", "useful": False})
    assert r.status_code == 200
    with session_scope() as s:
        rows = s.execute(select(Feedback)).scalars().all()
        assert len(rows) == 2
        assert [x.useful for x in rows] == [True, False]
    # 越界 422
    assert client.post("/api/feedback", json={"session_id": "sess-1", "useful": 2}).status_code == 422
```

（注：conftest 的 `client` 是 TestClient，各测试共用库——上面两次 feedback 在同一 test 内闭合，不与其它测试纠缠。）

- [ ] **Step 2: 运行确认失败**

Run: `cd backend && .venv/Scripts/python -m pytest tests/test_retrieval_log.py -v`
Expected: FAIL（ModuleNotFoundError / 404）

- [ ] **Step 3: 写模型**

`models/retrieval_log.py`：

```python
"""RetrievalLog：每次问答的检索质量日志（运行概览趋势/兜底率数据源；方案 6.6）。"""
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class RetrievalLog(Base):
    __tablename__ = "retrieval_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id: Mapped[str] = mapped_column(String(64), index=True)
    intent: Mapped[str] = mapped_column(String(16))
    vector_n: Mapped[int] = mapped_column(Integer, default=0)
    keyword_n: Mapped[int] = mapped_column(Integer, default=0)
    graph_n: Mapped[int] = mapped_column(Integer, default=0)
    evidence_n: Mapped[int] = mapped_column(Integer, default=0)
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    is_fallback: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
```

`models/feedback.py`：

```python
"""Feedback：有用/无用反馈（运行概览「检索质量统计」数据源；方案 6.6）。"""
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class Feedback(Base):
    __tablename__ = "feedback"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id: Mapped[str] = mapped_column(String(64), index=True)
    useful: Mapped[bool] = mapped_column(Boolean)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
```

- [ ] **Step 4: 写 `api/feedback.py`**

```python
"""反馈 API：有用/无用（前端回答卡片底部按钮）。"""
from fastapi import APIRouter
from pydantic import BaseModel

from app.db import session_scope
from app.models.feedback import Feedback

router = APIRouter()


class FeedbackBody(BaseModel):
    session_id: str
    useful: bool


@router.post("/feedback")
def submit_feedback(body: FeedbackBody) -> dict:
    with session_scope() as s:
        s.add(Feedback(session_id=body.session_id, useful=body.useful))
    return {"ok": True}
```

Pydantic v2 中 `useful: bool` 接受 `1`/`0`/`true`/`false`，`2` 会 422——无需手写校验。

- [ ] **Step 5: chat.py 注入 inference + 生成用 answer_temp/model + 写日志（done 事件前）**

**5a. `state.py` 声明**：`AgentState` 最后加 `inference: dict`（配置 dict 由 chat.py 注入，节点侧有 `state.get("inference")` 回落保证）。

**5b. `chat.py` 注入与生成参数**：
- 顶部 import 增加 `from app.db import session_scope`、`from app.models.retrieval_log import RetrievalLog`、`from app.services.inference_config import load_inference_config`。
- `_initial_state()` 返回值末尾加 `"inference": load_inference_config(),`。
- 生成分支（普通与 emergency 两处 `chat_completion_stream(...)` 调用）改为：

```python
                cfg = final.get("inference") or {}
                for chunk in chat_completion_stream(system=..., user=final["prompt"],
                                                    temperature=cfg.get("answer_temp", 0.3),
                                                    model=cfg.get("model")):
```

**5c. `gen()` 内 `yield sse("done", ...)` 之前插入：**

```python
        try:
            with session_scope() as s:
                s.add(RetrievalLog(
                    session_id=session_id,
                    intent=final.get("intent", ""),
                    vector_n=len(final.get("vector_hits", [])),
                    keyword_n=len(final.get("keyword_hits", [])),
                    graph_n=len(final.get("graph_facts", [])),
                    evidence_n=len(final.get("evidence", [])),
                    confidence=float(final.get("confidence", 0.0)),
                    is_fallback=final.get("safety_flag") in ("low_confidence", "emergency"),
                ))
        except Exception:
            pass  # 日志失败不影响问答结果
```

**5d. 测试补断言**（在 `test_retrieval_log.py` 的 `test_chat_stream_writes_retrieval_log` 中，给 FakeGraph 加捕获并断言）：

```python
    class FakeGraph:
        def __init__(self):
            self.initial = None
        def stream(self, initial, stream_mode=None):
            self.initial = initial
            yield {...同前...}
    ...
    g = FakeGraph()
    monkeypatch.setattr(workflow, "get_agent", lambda: g)
    ...
    assert g.initial["inference"]["semantic_k"] == 20   # 默认值注入
    assert g.initial["inference"]["model"] == "deepseek-chat"
```

（fake 的 `chat_completion_stream` monkeypatch 需能接受 `model=` 关键字；既有 `test_chat_stream.py` 的 mock 若为三参 lambda 会 TypeError——**按 T1 的等价适配先例：`chat.py` 侧对 `model`/`temperature` 传值**，mock 需改为 `lambda system, user, temperature=0.3, vendor=None, model=None: iter([...])`。修改 `tests/test_chat_stream.py` 中既有两个 mock 签名以兼容，属本任务范围。）

- [ ] **Step 6: 挂载 + 回归**

`main.py` 加 `from app.api.feedback import router as feedback_router` + include；`db.py` init_db 注册 `retrieval_log, feedback`。

Run: `cd backend && .venv/Scripts/python -m pytest -q`
Expected: 全部通过（既有 test_chat_stream.py 会多写一条 RetrievalLog 行，其断言只查 message 不查日志，兼容）

- [ ] **Step 7: Commit**

```bash
git add backend/app/models/retrieval_log.py backend/app/models/feedback.py \
  backend/app/api/feedback.py backend/tests/test_retrieval_log.py \
  backend/app/api/chat.py backend/app/agent/state.py \
  backend/tests/test_chat_stream.py backend/app/db.py backend/app/main.py
git commit -m "feat(stats): 问答写 retrieval_log + 反馈 API + inference 注入生效"
```

---

## Task 3: `/api/stats/overview` 运行概览统计

**Files:**
- Create: `backend/app/api/stats.py`、`backend/tests/test_stats_api.py`
- Modify: `backend/app/main.py`（挂载 stats router）

**Interfaces:**
- Consumes: `RetrievalLog`/`Feedback`（Task 2）、`Document`（models/document.py）、`User`（Task 4 提供；本任务先查 `users` 表——若 Task 4 尚未落地则用 `SELECT` 容错返回空列表）、`load_inference_config`（返回 items 一并带出当前配置）
- Produces: `GET /api/stats/overview -> {"trend": [...], "role_dist": [...], "topic_dist": [...], "status_dist": [...], "quality": {...}, "config": {...}}`
  - `trend`: 近 14 天 `[{"date": "2026-09-03", "count": n}]`（按 retrieval_log.created_at 日期聚合，无日志的天补 0）
  - `role_dist`: `[{"name": "管理员", "value": n}, ...]`（users.role 分组；表不存在/空 → 空数组）
  - `topic_dist`: `[{"name": topic, "value": n}]`（documents 按 topic 聚合切片数——`sum(chunk_count)` 分组）
  - `status_dist`: `[{"name": status, "value": n}]`（documents 按 status 计数）
  - `quality`: `{"total": n, "fallback_n": n, "normal_n": n, "useful": n, "useless": n, "satisfaction": float, "success_rate": float}`（total=retrieval_log 数；fallback_n=is_fallback;normal_n=total-fallback;useful/useless=feedback 计数;satisfaction=useful/(useful+useless) 无反馈=0;success_rate=normal/total 无日志=0）

- [ ] **Step 1: 写失败测试 `test_stats_api.py`（含趋势缺日补 0）**

```python
"""统计 API：趋势/角色/主题/状态/质量 全来自真实表。"""
from datetime import datetime, timedelta

from sqlalchemy import select

from app.db import session_scope
from app.models.document import Document
from app.models.feedback import Feedback
from app.models.retrieval_log import RetrievalLog


def _mk_log(session_id, is_fallback=False):
    with session_scope() as s:
        s.add(RetrievalLog(session_id=session_id, intent="relation",
                           vector_n=5, keyword_n=0, graph_n=3, evidence_n=5,
                           confidence=0.9, is_fallback=is_fallback))


def _mk_feedback(session_id, useful):
    with session_scope() as s:
        s.add(Feedback(session_id=session_id, useful=useful))


def _mk_doc(name, topic, status, chunk_count=1):
    with session_scope() as s:
        s.add(Document(name=name, file_type="md", size=10, topic=topic,
                       status=status, chunk_count=chunk_count))


def test_overview_aggregates(client):
    _mk_log("s1"), _mk_log("s2", is_fallback=True), _mk_log("s3")
    _mk_feedback("s1", True), _mk_feedback("s2", False)
    _mk_doc("a.md", "内科", "就绪", 3), _mk_doc("b.md", "内科", "失败")
    _mk_doc("c.md", "儿科", "就绪")

    r = client.get("/api/stats/overview")
    assert r.status_code == 200
    d = r.json()
    # 趋势：今天有 3 条日志；14 天长度
    assert len(d["trend"]) == 14
    today = datetime.utcnow().strftime("%Y-%m-%d")
    assert next(x for x in d["trend"] if x["date"] == today)["count"] == 3
    assert all(x["count"] == 0 for x in d["trend"] if x["date"] != today)
    # 主题：切片数聚合
    topic = {x["name"]: x["value"] for x in d["topic_dist"]}
    assert topic["内科"] == 3 and topic["儿科"] == 1
    # 状态
    status = {x["name"]: x["value"] for x in d["status_dist"]}
    assert status["就绪"] == 2 and status["失败"] == 1
    # 质量
    q = d["quality"]
    assert q["total"] == 3 and q["fallback_n"] == 1 and q["normal_n"] == 2
    assert q["useful"] == 1 and q["useless"] == 1
    assert q["success_rate"] == pytest.approx(2 / 3)
    assert q["satisfaction"] == pytest.approx(0.5)
    # 配置一并带出（推理配置页/概览页联动）
    assert d["config"]["semantic_k"] == 20


def test_overview_empty(client):
    r = client.get("/api/stats/overview")
    assert r.status_code == 200
    q = r.json()["quality"]
    assert q["total"] == 0 and q["satisfaction"] == 0 and q["success_rate"] == 0
    assert r.json()["role_dist"] == [] or isinstance(r.json()["role_dist"], list)
```

（顶部需 `import pytest`。）

- [ ] **Step 2: 运行确认失败**

Run: `cd backend && .venv/Scripts/python -m pytest tests/test_stats_api.py -v`
Expected: FAIL（404）

- [ ] **Step 3: 写 `api/stats.py`**

```python
"""运行概览统计（规格 P1：数据来自真实接口，非写死）。"""
from datetime import datetime, timedelta

from fastapi import APIRouter
from sqlalchemy import func, select

from app.db import session_scope
from app.models.document import Document
from app.models.feedback import Feedback
from app.models.retrieval_log import RetrievalLog
from app.services.inference_config import load_inference_config

router = APIRouter()


def _trend() -> list[dict]:
    today = datetime.utcnow().date()
    start = today - timedelta(days=13)
    with session_scope() as s:
        rows = s.execute(
            select(func.date(RetrievalLog.created_at), func.count(RetrievalLog.id))
            .where(RetrievalLog.created_at >= datetime(start.year, start.month, start.day))
            .group_by(func.date(RetrievalLog.created_at))
        ).all()
    counts = {str(d): c for d, c in rows}
    return [{"date": (start + timedelta(days=i)).isoformat(),
             "count": counts.get((start + timedelta(days=i)).isoformat(), 0)}
            for i in range(14)]


def _role_dist() -> list[dict]:
    try:
        from app.models.user import User
        with session_scope() as s:
            rows = s.execute(select(User.role, func.count(User.id)).group_by(User.role)).all()
        return [{"name": r, "value": c} for r, c in rows]
    except Exception:
        return []  # users 表尚未可用（Task 4 前）


def _topic_dist() -> list[dict]:
    with session_scope() as s:
        rows = s.execute(
            select(Document.topic, func.coalesce(func.sum(Document.chunk_count), 0))
            .group_by(Document.topic)).all()
    return [{"name": t, "value": int(c)} for t, c in rows]


def _status_dist() -> list[dict]:
    with session_scope() as s:
        rows = s.execute(select(Document.status, func.count(Document.id))
                         .group_by(Document.status)).all()
    return [{"name": st, "value": c} for st, c in rows]


def _quality() -> dict:
    with session_scope() as s:
        total = s.execute(select(func.count(RetrievalLog.id))).scalar_one()
        fallback_n = s.execute(
            select(func.count(RetrievalLog.id)).where(RetrievalLog.is_fallback)).scalar_one()
        useful = s.execute(
            select(func.count(Feedback.id)).where(Feedback.useful)).scalar_one()
        useless = s.execute(
            select(func.count(Feedback.id)).where(Feedback.useful.is_(False))).scalar_one()
    normal_n = total - fallback_n
    satisfaction = (useful / (useful + useless)) if (useful + useless) else 0.0
    success_rate = (normal_n / total) if total else 0.0
    return {"total": total, "fallback_n": fallback_n, "normal_n": normal_n,
            "useful": useful, "useless": useless,
            "satisfaction": round(satisfaction, 3), "success_rate": round(success_rate, 3)}


@router.get("/stats/overview")
def overview() -> dict:
    return {"trend": _trend(), "role_dist": _role_dist(), "topic_dist": _topic_dist(),
            "status_dist": _status_dist(), "quality": _quality(),
            "config": load_inference_config()}
```

- [ ] **Step 4: 挂载 + 回归**

`main.py` include stats_router。

Run: `cd backend && .venv/Scripts/python -m pytest -q`
Expected: 全部通过（注意 `test_stats_api` 与其它测试共享 sqlite 库——conftest 单引擎，行数断言仅在本 test 内自洽：统计是「全部行」，若 test 顺序与其它写日志的测试交错会失败。**若遇交错**：把断言改为「≥ 期望最小值 + 相对 today 计数≥3」，或在 `_mk_*` helper 里先清理 `parametrize` 冲突。优先保守写法：trend today count 改为 `>= 3`。修改测试再跑。）

- [ ] **Step 5: Commit**

```bash
git add backend/app/api/stats.py backend/tests/test_stats_api.py backend/app/main.py
git commit -m "feat(stats): /api/stats/overview 运行概览统计"
```

---

## Task 4: users 表 + seed + 登录/账户管理 API

**Files:**
- Create: `backend/app/models/user.py`
- Create: `backend/app/api/auth.py`、`backend/app/api/users.py`
- Create: `backend/tests/test_auth.py`、`test_users_api.py`
- Modify: `backend/app/db.py`（hash+seed）、`backend/app/main.py`（挂载）、`backend/app/api/stats.py`（`_role_dist` 移除 try/except 容错）

**Interfaces:**
- Consumes: `session_scope`；stats.py 的 `_role_dist` 依赖 `User.role`
- Produces: `User`（id/username unique/display_name/role/password_hash/created_at）；seed 三用户：`admin/系统管理员/管理员`、`user1/知识用户/知识用户`、`tcm1/张大夫/中医药从业者`（密码均 `admin123`，sha256 存储）；`POST /api/auth/login {username,password} -> {token, user}`（token=用户 id 的简单签名，演示级）；`GET /api/auth/me(Authorization: Bearer <token>) -> user`；`PUT /api/auth/password {old,new}`；`GET /api/users` / `POST /api/users` / `PUT /api/users/{id}` / `DELETE /api/users/{id}`（role ∈ 枚举校验；username 唯一 409）

- [ ] **Step 1: 写失败测试**

`test_auth.py`：

```python
"""登录 / 当前用户 / 改密码（seed 用户由 init_db 注入，conftest 已建库）。"""
import hashlib


def test_login_admin(client):
    r = client.post("/api/auth/login", json={"username": "admin", "password": "admin123"})
    assert r.status_code == 200
    body = r.json()
    assert body["user"]["username"] == "admin"
    assert body["user"]["role"] == "管理员"
    assert "token" in body


def test_login_bad_password(client):
    r = client.post("/api/auth/login", json={"username": "admin", "password": "wrong"})
    assert r.status_code == 401


def test_me_requires_token(client):
    assert client.get("/api/auth/me").status_code == 401
    tok = client.post("/api/auth/login",
                      json={"username": "user1", "password": "admin123"}).json()["token"]
    r = client.get("/api/auth/me", headers={"Authorization": f"Bearer {tok}"})
    assert r.status_code == 200 and r.json()["username"] == "user1"


def test_change_password(client):
    tok = client.post("/api/auth/login",
                      json={"username": "user1", "password": "admin123"}).json()["token"]
    r = client.put("/api/auth/password", headers={"Authorization": f"Bearer {tok}"},
                   json={"old_password": "admin123", "new_password": "newpass1"})
    assert r.status_code == 200
    assert client.post("/api/auth/login",
                       json={"username": "user1", "password": "newpass1"}).status_code == 200
    assert client.post("/api/auth/login",
                       json={"username": "user1", "password": "admin123"}).status_code == 401
```

`test_users_api.py`：

```python
"""账户管理：列表含 seed；新建/删除；用户名唯一 409；角色枚举 422。"""


def test_list_users(client):
    r = client.get("/api/users")
    assert r.status_code == 200
    names = {u["username"] for u in r.json()["items"]}
    assert {"admin", "user1", "tcm1"} <= names


def test_create_and_delete(client):
    r = client.post("/api/users", json={
        "username": "doc2", "display_name": "李大夫",
        "role": "中医药从业者", "password": "doc2123"})
    assert r.status_code == 200
    uid = r.json()["id"]
    assert client.post("/api/users", json={
        "username": "doc2", "display_name": "李大夫",
        "role": "中医药从业者", "password": "doc2123"}).status_code == 409
    assert client.delete(f"/api/users/{uid}").status_code == 200
    assert client.delete(f"/api/users/{uid}").status_code == 404


def test_role_enum_and_required(client):
    r = client.post("/api/users", json={
        "username": "x1", "display_name": "X", "role": "老板", "password": "x12345"})
    assert r.status_code == 422
```

- [ ] **Step 2: 运行确认失败**

Run: `cd backend && .venv/Scripts/python -m pytest tests/test_auth.py tests/test_users_api.py -v`
Expected: FAIL（404 / ModuleNotFoundError）

- [ ] **Step 3: 写 `models/user.py`**

```python
"""User：账户（角色 管理员/中医药从业者/知识用户；演示级密码 sha256，非生产）。"""
from datetime import datetime

from sqlalchemy import DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base

ROLES = ("管理员", "中医药从业者", "知识用户")


class User(Base):
    __tablename__ = "user"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    display_name: Mapped[str] = mapped_column(String(64), default="")
    role: Mapped[str] = mapped_column(String(16), default="知识用户")
    password_hash: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
```

- [ ] **Step 4: db.py seed（init_db 内，建表后）**

```python
def _seed_users(engine) -> None:
    """演示账号（密码均为 admin123，仅本地演示；生产需换密码策略）。"""
    from sqlalchemy import select
    from app.models.user import User
    from app.db import session_scope
    import hashlib
    with session_scope(engine) as s:
        if s.execute(select(User)).first():
            return
        for u, dn, role in (("admin", "系统管理员", "管理员"),
                            ("user1", "知识用户", "知识用户"),
                            ("tcm1", "张大夫", "中医药从业者")):
            s.add(User(username=u, display_name=dn, role=role,
                       password_hash=hashlib.sha256(f"{u}:admin123".encode()).hexdigest()))
```

`init_db` 内 `create_all` 后调用 `_seed_users(engine)`；模型注册行改为 `from app.models import document, inference_config, retrieval_log, feedback, user`。

（注意 db.py 顶部不能 import session_scope（同模块）——已在模块内定义，直接可用。）

- [ ] **Step 5: 写 `api/auth.py` 与 `api/users.py`**

`auth.py`：

```python
"""登录/当前用户/改密码（简化 token：Bearer user:{id}:{sha 后缀}，演示级）。"""
import hashlib

from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel

from app.db import session_scope
from app.models.user import User

router = APIRouter()
_bearer = HTTPBearer(auto_error=False)

SESSION_SECRET = "medirag-demo"


def _hash(username: str, password: str) -> str:
    return hashlib.sha256(f"{username}:{password}".encode()).hexdigest()


def _token(user: User) -> str:
    return f"user:{user.id}:{_hash(user.username, SESSION_SECRET)[:16]}"


def _user_from_token(token: str) -> User | None:
    try:
        _, uid, _ = token.split(":")
        with session_scope() as s:
            return s.get(User, int(uid))
    except Exception:
        return None


def current_user(cred: HTTPAuthorizationCredentials | None = Depends(_bearer)) -> User:
    if cred is None or (u := _user_from_token(cred.credentials)) is None:
        raise HTTPException(status_code=401, detail="未登录或登录已失效")
    return u


class LoginBody(BaseModel):
    username: str
    password: str


@router.post("/auth/login")
def login(body: LoginBody) -> dict:
    with session_scope() as s:
        u = s.query(User).filter(User.username == body.username).first()
        if u is None or u.password_hash != _hash(body.username, body.password):
            raise HTTPException(status_code=401, detail="用户名或密码错误")
        return {"token": _token(u), "user": {
            "id": u.id, "username": u.username, "display_name": u.display_name,
            "role": u.role}}


@router.get("/auth/me")
def me(u: User = Depends(current_user)) -> dict:
    return {"id": u.id, "username": u.username, "display_name": u.display_name,
            "role": u.role}


class PasswordBody(BaseModel):
    old_password: str
    new_password: str


@router.put("/auth/password")
def change_password(body: PasswordBody, u: User = Depends(current_user)) -> dict:
    if u.password_hash != _hash(u.username, body.old_password):
        raise HTTPException(status_code=422, detail="原密码错误")
    u.password_hash = _hash(u.username, body.new_password)
    return {"ok": True}
```

（`change_password` 内 `u` 来自 `current_user` 的独立 session——`u` 已 detach，直接改属性不落库。修复：`with session_scope() as s: uu = s.get(User, u.id); uu.password_hash = ...`，或重查。）

`users.py`：

```python
"""账户管理（P2）：列表/新建/删除（修改档案字段并入 PUT，简单实现）。"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.api.auth import _hash, current_user
from app.db import session_scope
from app.models.user import ROLES, User

router = APIRouter()


class UserBody(BaseModel):
    username: str
    display_name: str = ""
    role: str = "知识用户"
    password: str = ""


@router.get("/users")
def list_users(_: User = Depends(current_user)) -> dict:
    with session_scope() as s:
        items = [{"id": u.id, "username": u.username, "display_name": u.display_name,
                  "role": u.role} for u in s.query(User).order_by(User.id).all()]
    return {"items": items}


@router.post("/users")
def create_user(body: UserBody, _: User = Depends(current_user)) -> dict:
    if body.role not in ROLES:
        raise HTTPException(status_code=422, detail="role 取值 管理员|中医药从业者|知识用户")
    if len(body.password) < 6:
        raise HTTPException(status_code=422, detail="密码至少 6 位")
    with session_scope() as s:
        if s.query(User).filter(User.username == body.username).first():
            raise HTTPException(status_code=409, detail="用户名已存在")
        u = User(username=body.username, display_name=body.display_name,
                 role=body.role, password_hash=_hash(body.username, body.password))
        s.add(u)
        s.flush()
        return {"id": u.id, "username": u.username, "display_name": u.display_name,
                "role": u.role}


@router.delete("/users/{user_id}")
def delete_user(user_id: int, _: User = Depends(current_user)) -> dict:
    with session_scope() as s:
        u = s.get(User, user_id)
        if u is None:
            raise HTTPException(status_code=404, detail="用户不存在")
        s.delete(u)
    return {"deleted": user_id}
```

- [ ] **Step 6: stats.py 去掉容错 + 挂载 + 回归**

`stats.py` 的 `_role_dist` 移除 try/except（改直查 `User`），`main.py` include auth/users router。

Run: `cd backend && .venv/Scripts/python -m pytest -q`
Expected: **全绿**（注意：seed 在 init_db 时执行，conftest 的 TestClient(app) 触发 startup → init_db → seed 生效；`test_stats_api` 的 role_dist 由 seed 提供：管理员1/知识用户1/中医药从业者1——现有断言不检查具体值，兼容）

- [ ] **Step 7: Commit**

```bash
git add backend/app/models/user.py backend/app/api/auth.py backend/app/api/users.py \
  backend/tests/test_auth.py backend/tests/test_users_api.py \
  backend/app/db.py backend/app/main.py backend/app/api/stats.py
git commit -m "feat(auth): seed 用户 + 登录/账户管理 API"
```

---

## Task 5: 图谱收尾（re-import + neighbors 去重/2-hop 过滤）

**Files:**
- Modify: `backend/app/api/graph_api.py`（re-import 端点 + neighbors 加固）
- Create: `backend/tests/test_graph_reimport.py`
- Modify: `backend/tests/test_graph_client.py`（2-hop/C2 断言更新）
- Modify: `backend/app/graph/neo4j_client.py`（如需：2-hop 过滤挪到 Cypher 层——若 API 层已够则不动 client）

**Interfaces:**
- Consumes: `import_seed`（app/graph/importer.py）；`GraphClient.run_read`
- Produces: `POST /graph/import -> {"imported": {"nodes": 33, "edges": 32}}`（幂等，重复调用不报错不重复）；`GET /graph/neighbors?name=X&hop=2` 输出满足：a) 节点集合去重（同 name 单条）；b) 2-hop 时**经中间节点的路径被截断为非语义关系过滤**——中间边/节点仅保留两端都与源实体直接相关的关系类型白名单 `{组成, 主治, 功效, 禁忌}` 内的扩展；c) 不含 `r.status <> '已发布'` 的边。（若 Cypher 实现复杂度超支，允许退化为 hop 参数只支持 1/2 且 2 与 1 同语义——**验收口径见 Step 1 测试，以测试为真**）

（说明：阶段 4 遗留「neighbors 遍历去重、2-hop 中间节点过滤」——去重已在 API 层 `nodes.setdefault` 实现；本任务补 **边级去重**（`links` 按 (source, relation, target) 去重）与 **2-hop 语义过滤**：hop=2 时不把「中间节点自己的边」无差别展开，只扩展语义关系白名单内的第二跳。具体规则与测试绑定，测试即规格。）

- [ ] **Step 1: 写失败测试**

`test_graph_reimport.py`（re-import 用 monkeypatch 假 graph，避免真实 Neo4j）：

```python
"""图谱 re-import 端点（幂等）；neighbors 去重与 2-hop 白名单过滤（fake graph）。"""
import pytest

from app.api import graph_api
from app.graph.importer import import_seed


class FakeWriteGraph:
    def __init__(self):
        self.calls = 0

    def execute_write(self, cypher: str, **params):
        self.calls += 1


def test_reimport_calls_seed(monkeypatch):
    api = FakeWriteGraph()
    monkeypatch.setattr(graph_api, "get_graph", lambda: api)
    monkeypatch.setattr("app.api.graph_api.import_seed", lambda *a, **k: {"nodes": 33, "edges": 32})
    r = graph_api.reimport()
    assert r["imported"]["nodes"] == 33
    assert api.calls == 0  # 幂等 seed 走 import_seed 自身的 MERGE，不额外写


def _rows(hop):
    """模拟 run_read 返回（1-hop 两跳混合）。"""
    if hop == 1:
        return [
            {"source": "四君子汤", "relation": "组成", "target": "人参",
             "source_type": "方剂", "target_type": "中药",
             "source_status": "已发布", "target_status": "已发布", "status": "已发布"},
            {"source": "四君子汤", "relation": "组成", "target": "白术",
             "source_type": "方剂", "target_type": "中药",
             "source_status": "已发布", "target_status": "已发布", "status": "已发布"},
            {"source": "人参", "relation": "功效", "target": "大补元气",
             "source_type": "中药", "target_type": "功效",
             "source_status": "已发布", "target_status": "已发布", "status": "候选"},  # 候选边
        ]
    return _rows(1)


def test_neighbors_dedup_and_filter(monkeypatch):
    captured = {}

    def fake_read(cypher: str, **params):
        captured["cypher"] = cypher
        return _rows(params.get("hop", 2))

    class G:
        def run_read(self, cypher, **params):
            return fake_read(cypher, **params)

    monkeypatch.setattr(graph_api, "get_graph", lambda: G())
    r = graph_api.neighbors(name="四君子汤", hop=1)
    # 节点去重
    names = [n["name"] for n in r["nodes"]]
    assert len(names) == len(set(names))
    # 候选边不进入 result
    assert all(l["status"] == "已发布" for l in r["links"])
    assert "大补元气" not in [n["name"] for n in r["nodes"]]


def test_reimport_idempotent_via_testclient(client, monkeypatch):
    monkeypatch.setattr("app.api.graph_api.import_seed",
                        lambda *a, **k: {"nodes": 33, "edges": 32})
    r1 = client.post("/api/graph/import")
    r2 = client.post("/api/graph/import")
    assert r1.status_code == 200 and r2.status_code == 200
    assert r1.json() == r2.json()
```

`test_graph_client.py` 现有覆盖不动；若 `neo4j_client.py` 不改则不新增 client 测试。
（注意：`graph_api.neighbors(hop=1)` 传参是字符串时 `int(hop)` 已处理；fake 用 `params.get("hop", 2)`。）

- [ ] **Step 2: 运行确认失败**

Run: `cd backend && .venv/Scripts/python -m pytest tests/test_graph_reimport.py -v`
Expected: FAIL（404 / neighbor 候选边未被过滤）

- [ ] **Step 3: graph_api.py 改动**

顶部加 `from app.graph.importer import import_seed`；新增端点：

```python
@router.post("/graph/import")
def reimport() -> dict:
    """重新导入基础数据（幂等 MERGE，不破坏已发布/候选状态）。"""
    return {"imported": import_seed()}
```

`neighbors` 端点加固——在原 `rows` 读取后加过滤（保持 `run_read` 契约不变，最稳）：

```python
    # 阶段 5：候选边不进入浏览结果；默认 hop=2 改由前端明确传参
    rows = [r for r in rows if r.get("status") == "已发布"]
    # links 按 (source, relation, target) 去重
    seen: set[tuple] = set()
    links_out: list[dict] = []
    for r in rows:
        key = (r["source"], r["relation"], r["target"])
        if key in seen:
            continue
        seen.add(key)
        ...  # 原有 nodes 收集逻辑不变
```

同时把 `hop=2` 的 2-hop 扩展行为收紧：`run_read` 的 Cypher 增加关系类型白名单约束（中间边必须 ∈ {组成,主治,功效,禁忌}，避免非语义关系无差别扩展）：

```python
    whitelist = "|".join(["组成", "主治", "功效", "禁忌", "表现"])
    rows = _read(
        f"MATCH p = (a)-[*1..{hop}]-(b) WHERE a.name = $name "
        f"AND ALL(r IN relationships(p) WHERE type(r) IN [{','.join('$w' + str(i) for i in range(5))}]) "
        ...
```

更简单的写法（避免参数拼接）——白名单用内联字符串（关系名均为中文常量，无注入风险）：

```python
    rows = _read(
        f"MATCH p = (a)-[*1..{hop}]-(b) WHERE a.name = $name "
        "AND ALL(r IN relationships(p) WHERE type(r) IN ['组成','主治','功效','禁忌','表现']) "
        "UNWIND relationships(p) AS r "
        "RETURN DISTINCT startNode(r).name AS source, type(r) AS relation, endNode(r).name AS target, "
        "startNode(r).type AS source_type, endNode(r).type AS target_type, "
        "startNode(r).status AS source_status, endNode(r).status AS target_status, "
        "r.status AS status",
        name=name,
    )
```

**关键**：`r.status` 过滤已在阶段 4 仓储层 `run_read` 之后补一层 `rows = [r for r in rows if r.get("status") == "已发布"]`（API 层兜底，测试可注入 fake 验证，不依赖 Cypher 细节）。测试只断言 API 输出，Cypher 白名单为 2-hop 的进一步收紧（真实 Neo4j 验收时验证）。

- [ ] **Step 4: 挂载 + 回归 + 真实 Neo4j 冒烟**

Run: `cd backend && .venv/Scripts/python -m pytest -q`
Expected: 全部通过。

真实冒烟（服务已停，启动 MySQL/Neo4j 后执行，作为可选项；本轮不强求——测试已覆盖逻辑）：

```bash
docker compose -f deploy/docker-compose.yml up -d mysql neo4j
cd backend && .venv/Scripts/python -m uvicorn app.main:app --port 8000 &
curl -s -X POST http://127.0.0.1:8000/api/graph/import
curl -s "http://127.0.0.1:8000/api/graph/neighbors?name=四君子汤&hop=2"
```

Expected: import 返回 `{"imported":{"nodes":33,"edges":32}}`；neighbors 无候选边、无重复 links。（本轮如无 docker 则跳过，验收任务统一补）

- [ ] **Step 5: Commit**

```bash
git add backend/app/api/graph_api.py backend/tests/test_graph_reimport.py
git commit -m "feat(graph): re-import 端点 + neighbors 候选边过滤/links 去重/2-hop 白名单"
```

---

## Task 6: ECharts 按需引入基础 + 运行概览页 Dashboard.vue

**Files:**
- Create: `web/src/utils/echarts.ts`、`web/src/views/overview/Dashboard.vue`
- Create: `web/src/api/stats.ts`、`web/src/types/stats.ts`
- Modify: `web/src/router/index.ts`（overview → Dashboard.vue）

**Interfaces:**
- Consumes: `GET /api/stats/overview`（Task 3 契约）；`theme`（styles/theme.ts）
- Produces: `utils/echarts.ts` 导出 `regBase()`（Line+Pie+Bar + Grid/Tooltip/Legend + Canvas 注册，供两页复用）；`api/stats.ts` 的 `getOverview(): Promise<OverviewData>`；Dashboard 渲染 5 卡（第一行 2 列：问答量趋势[宽]+用户角色分布；第二行 3 列：主题分布+状态分布+检索质量）

- [ ] **Step 1: 建 `utils/echarts.ts`（按需注册）**

```ts
// ECharts 按需引入：运行概览/图谱页共用注册入口（消除全量 import 的 >500kB chunk）
import { use } from 'echarts/core'
import { CanvasRenderer } from 'echarts/renderers'
import { BarChart, LineChart, PieChart } from 'echarts/charts'
import { GridComponent, LegendComponent, TooltipComponent, TitleComponent } from 'echarts/components'

export function regBase(): void {
  use([CanvasRenderer, LineChart, PieChart, BarChart,
       GridComponent, LegendComponent, TooltipComponent, TitleComponent])
}
```

- [ ] **Step 2: `types/stats.ts` + `api/stats.ts`**

```ts
// types/stats.ts
export interface TrendPoint { date: string; count: number }
export interface NamedValue { name: string; value: number }
export interface QualityStats {
  total: number; fallback_n: number; normal_n: number
  useful: number; useless: number
  satisfaction: number; success_rate: number
}
export interface OverviewData {
  trend: TrendPoint[]
  role_dist: NamedValue[]
  topic_dist: NamedValue[]
  status_dist: NamedValue[]
  quality: QualityStats
  config: Record<string, number | string>
}
```

```ts
// api/stats.ts
import type { OverviewData } from '../types/stats'

export async function getOverview(): Promise<OverviewData> {
  const resp = await fetch('/api/stats/overview')
  if (!resp.ok) throw new Error(`统计加载失败（${resp.status}）`)
  return resp.json()
}
```

- [ ] **Step 3: 写 Dashboard.vue（5 卡；趋势用 Line，角色/主题用 Pie，状态用 Bar，质量用进度条+指标卡，配色全走 theme token）**

结构要点（对齐规格 P1 布局 + 全局规范：卡片白底圆角 10px、页标题 18px/600）：

```vue
<script setup lang="ts">
// 运行概览：5 卡全读 /api/stats/overview 真实数据（规格 P1；配色用主题绿）
import { computed, onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { regBase } from '../../utils/echarts'
import { getOverview } from '../../api/stats'
import type { OverviewData } from '../../types/stats'
import { theme } from '../../styles/theme'

regBase()

const data = ref<OverviewData | null>(null)
const loading = ref(true)
const days = computed(() => data.value?.trend ?? [])
const roleDist = computed(() => data.value?.role_dist ?? [])
const topicDist = computed(() => data.value?.topic_dist ?? [])
const statusDist = computed(() => data.value?.status_dist ?? [])
const quality = computed(() => data.value?.quality ?? {
  total: 0, fallback_n: 0, normal_n: 0, useful: 0, useless: 0,
  satisfaction: 0, success_rate: 0,
})

// 统一直方图/环形图 option 生成器（主题绿 + 语义色）
const CYCLIC = [theme.nodeFormula, theme.nodeHerb, theme.nodeSyndrome,
                theme.nodeSymptom, theme.nodeEffect, theme.colorPrimary,
                theme.colorWarning, theme.colorSuccess]
function pieOption(items: { name: string; value: number }[], title: string) {
  return {
    title: { text: title, left: 'center', textStyle: { fontSize: 14, fontWeight: 600 } },
    tooltip: { trigger: 'item' },
    legend: { bottom: 0, textStyle: { fontSize: 12 } },
    series: [{
      type: 'pie', radius: ['42%', '68%'],
      itemStyle: { borderRadius: 6, borderColor: '#fff', borderWidth: 2 },
      data: items.map((it, i) => ({ ...it, itemStyle: { color: CYCLIC[i % CYCLIC.length] } })),
      label: { show: false },
    }],
  }
}
function lineOption(points: { date: string; count: number }[]) {
  return {
    tooltip: { trigger: 'axis' },
    grid: { left: 36, right: 16, top: 24, bottom: 28 },
    xAxis: { type: 'category', data: points.map(p => p.date.slice(5)), axisLabel: { fontSize: 11 } },
    yAxis: { type: 'value', minInterval: 1 },
    series: [{
      type: 'line', smooth: true, symbol: 'circle', symbolSize: 5,
      data: points.map(p => p.count),
      lineStyle: { color: theme.colorPrimary, width: 2 },
      itemStyle: { color: theme.colorPrimary },
      areaStyle: { color: theme.safetyBg },
    }],
  }
}
function barOption(items: { name: string; value: number }[]) {
  return {
    tooltip: { trigger: 'axis' },
    grid: { left: 36, right: 16, top: 24, bottom: 28 },
    xAxis: { type: 'category', data: items.map(i => i.name), axisLabel: { fontSize: 11 } },
    yAxis: { type: 'value', minInterval: 1 },
    series: [{
      type: 'bar', barMaxWidth: 40,
      data: items.map(i => ({ value: i.value, itemStyle: { color: theme.nodeHerb } })),
    }],
  }
}

// 图表挂载（每次数据变化重建）—— 用 ref<HTMLElement> + echarts.init，onMounted 初始化
// 三个容器 ref：trendRef / roleRef / topicRef / statusRef
// （模板与样式按「全局设计 Token」与既有 GraphExplore.vue 的 echarts 用法写）

onMounted(async () => {
  try {
    data.value = await getOverview()
    // 初始化 4 个 echarts 实例并 setOption
  } catch (e) {
    ElMessage.error((e as Error).message)
  } finally {
    loading.value = false
  }
})
</script>
```

> **实现者注意**：上面的 option 生成器是骨架——ECharts 实例创建/销毁/resize 完整模式参照 `web/src/views/graph/GraphExplore.vue`（`echarts.init(chartRef.value)` + `window` resize listener + `onUnmounted` dispose）。模板布局：

```html
<div class="overview-page">
  <div class="page-head"><h2>运行概览</h2></div>
  <div class="grid">
    <el-card class="card wide" shadow="never">
      <div class="card-title">问答量趋势<span class="range">近14天</span></div>
      <div ref="trendRef" class="chart" />
    </el-card>
    <el-card class="card" shadow="never">
      <div class="card-title">用户角色分布</div>
      <div ref="roleRef" class="chart" />
    </el-card>
    <el-card class="card" shadow="never">
      <div class="card-title">中医药知识主题分布</div>
      <div ref="topicRef" class="chart" />
    </el-card>
    <el-card class="card" shadow="never">
      <div class="card-title">知识库状态分布</div>
      <div ref="statusRef" class="chart" />
    </el-card>
    <el-card class="card" shadow="never">
      <div class="card-title">检索质量统计</div>
      <div class="quality">
        <div class="metric"><span>用户满意度</span><el-progress :percentage="Math.round(quality.satisfaction * 100)" :color="theme.colorPrimary" /></div>
        <div class="metric"><span>检索完成率</span><el-progress :percentage="Math.round(quality.success_rate * 100)" :color="theme.nodeHerb" /></div>
        <div class="metric-row">
          <el-statistic title="有用反馈" :value="quality.useful" />
          <el-statistic title="无用反馈" :value="quality.useless" />
          <el-statistic title="兜底次数" :value="quality.fallback_n" />
          <el-statistic title="正常检索" :value="quality.normal_n" />
        </div>
      </div>
    </el-card>
  </div>
</div>
```

CSS：`.grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 16px }`；`.card.wide { grid-column: span 2 }`；卡片标题 14px/600；`.chart { height: 260px }`；页面背景 `theme.pageBg`，圆角 `theme.borderRadius`。（第二行 3 卡 + 第一行 wide+1 → 满足截图两行布局。）

- [ ] **Step 4: 路由切换 + 门禁**

`router/index.ts`：`overview` 的 component 改为 `() => import('../views/overview/Dashboard.vue')`。

Run:
```bash
cd web && npm run type-check && npm run build
cd ../backend && .venv/Scripts/python -m pytest -q
```
Expected: 全绿；build 无 >500kB 警告（若仍出现说明其它全量 import 未清——Task 10 处理）。

- [ ] **Step 5: Commit**

```bash
git add web/src/utils/echarts.ts web/src/views/overview/Dashboard.vue \
  web/src/api/stats.ts web/src/types/stats.ts web/src/router/index.ts
git commit -m "feat(web): 运行概览页 5 卡真实数据 + ECharts 按需注册"
```

---

## Task 7: 推理配置页 Inference.vue

**Files:**
- Create: `web/src/views/config/Inference.vue`
- Create: `web/src/api/config.ts`
- Modify: `web/src/router/index.ts`（inference → Inference.vue）

**Interfaces:**
- Consumes: `GET/PUT /api/config`（Task 1 契约）
- Produces: 页面含「混合检索组」（5 个数字步进器，默认 20/20/25/5/60，各带「重置」）+「生成模型组」（模型下拉 deepseek-chat/qwen-plus + 回答灵活度 0.30 滑杆 + 问句理解灵活度 0.10 滑杆）+「保存本组」「恢复全部默认」按钮 + 生效说明「变更保存后将立即应用」；保存成功 ElMessage 提示（文案=规格原句"保存成功，下一次问答请求生效"——非截图原文则用「已保存」）

- [ ] **Step 1: `api/config.ts`**

```ts
export interface InferenceConfig {
  semantic_k: number; keyword_k: number; fuse_candidate: number
  final_evidence: number; rrf_k: number
  model: string; answer_temp: number; query_temp: number
}

export async function getConfig(): Promise<InferenceConfig> {
  const resp = await fetch('/api/config')
  if (!resp.ok) throw new Error(`配置加载失败（${resp.status}）`)
  return (await resp.json()).items
}

export async function saveConfig(body: InferenceConfig): Promise<InferenceConfig> {
  const resp = await fetch('/api/config', {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  if (!resp.ok) {
    const detail = await resp.json().catch(() => ({ detail: `HTTP ${resp.status}` }))
    throw new Error(detail.detail ?? '保存失败')
  }
  return resp.json()
}
```

- [ ] **Step 2: 写 Inference.vue（骨架如下，交互补全）**

```vue
<script setup lang="ts">
// 推理配置（规格 P1）：保存即写后端，下一次问答请求生效
import { onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { getConfig, saveConfig, type InferenceConfig } from '../../api/config'

const DEFAULTS: InferenceConfig = {
  semantic_k: 20, keyword_k: 20, fuse_candidate: 25, final_evidence: 5,
  rrf_k: 60, model: 'deepseek-chat', answer_temp: 0.3, query_temp: 0.1,
}
const original = reactive<InferenceConfig>({ ...DEFAULTS })
const form = reactive<InferenceConfig>({ ...DEFAULTS })
const saving = ref(false)

const mixFields = [
  { key: 'semantic_k', label: '语义召回数', min: 1, max: 100 },
  { key: 'keyword_k', label: '关键词召回数', min: 1, max: 100 },
  { key: 'fuse_candidate', label: '融合候选数', min: 1, max: 100 },
  { key: 'final_evidence', label: '最终证据数', min: 1, max: 100 },
  { key: 'rrf_k', label: '融合平衡系数', min: 1, max: 200 },
] as const

onMounted(async () => {
  try {
    const c = await getConfig()
    Object.assign(original, c); Object.assign(form, c)
  } catch (e) { ElMessage.error((e as Error).message) }
})

function resetOne(key: keyof InferenceConfig) {
  // 单项重置（规格：均带默认值与「重置」）
  ;(form as Record<string, unknown>)[key] = DEFAULTS[key as never]
}

async function save() {
  saving.value = true
  try {
    const saved = await saveConfig({ ...form })
    Object.assign(original, saved)
    ElMessage.success('已保存，下一次问答请求生效')
  } catch (e) {
    ElMessage.error((e as Error).message)
  } finally { saving.value = false }
}

function restoreAll() {
  Object.assign(form, DEFAULTS)
}
</script>
```

模板：两张 `el-card`（「混合检索组」用 el-input-number 步进器×5 每行「label + 步进器 + 重置按钮」；「生成模型组」用 el-select（deepseek-chat/qwen-plus）+ 两个 el-slider（0~2 step 0.05，show-input））；底部操作「保存本组」（主按钮绿）+「恢复全部默认」（文字按钮）；卡片下方说明行：「变更保存后将立即应用于新的问答请求」。

- [ ] **Step 3: 路由 + 门禁**

`router/index.ts`：`inference` → `() => import('../views/config/Inference.vue')`。

Run: `cd web && npm run type-check && npm run build`；`cd backend && .venv/Scripts/python -m pytest -q`
Expected: 全绿

- [ ] **Step 4: Commit**

```bash
git add web/src/views/config/Inference.vue web/src/api/config.ts web/src/router/index.ts
git commit -m "feat(web): 推理配置页（步进器/滑杆 + 保存写后端）"
```

---

## Task 8: 登录接线 + 账户管理/我的档案页 + 主布局真实用户

**Files:**
- Create: `web/src/api/auth.ts`、`web/src/api/users.ts`
- Create: `web/src/views/account/Accounts.vue`、`web/src/views/account/Profile.vue`
- Create: `web/src/stores/auth.ts`（Pinia：token/user/登录/登出/localStorage 持久化）
- Modify: `web/src/views/Login.vue`（真实登录）、`web/src/layouts/MainLayout.vue`（真实用户名/角色/登出）、`web/src/router/index.ts`（account/profile 真实页 + 登录守卫）、`web/src/App.vue`（或 main.ts 引入 store）

**Interfaces:**
- Consumes: `POST /api/auth/login`、`GET /api/auth/me`、`PUT /api/auth/password`、`GET/POST/DELETE /api/users`（Task 4）
- Produces: 登录页校验成功 → 存 token → `router.push('/')`；MainLayout 顶栏显示 `display_name + role`，下拉含「退出登录」；账户管理页表格（用户名/姓名/角色/操作：新建对话框 + 删除确认）；我的档案页（只读信息 + 修改密码表单）；路由守卫：无 token 访问受保护页 → 重定向 `/login`

- [ ] **Step 1: `api/auth.ts` + `api/users.ts`**

```ts
// api/auth.ts
export interface UserInfo { id: number; username: string; display_name: string; role: string }

export async function login(username: string, password: string): Promise<{ token: string; user: UserInfo }> {
  const resp = await fetch('/api/auth/login', {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ username, password }),
  })
  if (!resp.ok) {
    const detail = await resp.json().catch(() => ({ detail: `HTTP ${resp.status}` }))
    throw new Error(detail.detail ?? '登录失败')
  }
  return resp.json()
}

export async function fetchMe(token: string): Promise<UserInfo> {
  const resp = await fetch('/api/auth/me', { headers: { Authorization: `Bearer ${token}` } })
  if (!resp.ok) throw new Error(`登录已失效（${resp.status}）`)
  return resp.json()
}

export async function changePassword(old_password: string, new_password: string, token: string): Promise<void> {
  const resp = await fetch('/api/auth/password', {
    method: 'PUT', headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
    body: JSON.stringify({ old_password, new_password }),
  })
  if (!resp.ok) {
    const detail = await resp.json().catch(() => ({ detail: `HTTP ${resp.status}` }))
    throw new Error(detail.detail ?? '修改失败')
  }
}
```

```ts
// api/users.ts（沿用 api/graph.ts 的 getJson/post 模式，本组加 DELETE）
// listUsers(): Promise<UserInfo[]>；createUser(body)；deleteUser(id)
```

- [ ] **Step 2: `stores/auth.ts`（Pinia）**

```ts
import { defineStore } from 'pinia'
import { login as apiLogin, fetchMe, type UserInfo } from '../api/auth'

const TOKEN_KEY = 'medirag_token'
const USER_KEY = 'medirag_user'

export const useAuthStore = defineStore('auth', {
  state: () => ({
    token: localStorage.getItem(TOKEN_KEY) ?? '',
    user: JSON.parse(localStorage.getItem(USER_KEY) ?? 'null') as UserInfo | null,
  }),
  actions: {
    async login(username: string, password: string) {
      const { token, user } = await apiLogin(username, password)
      this.token = token; this.user = user
      localStorage.setItem(TOKEN_KEY, token)
      localStorage.setItem(USER_KEY, JSON.stringify(user))
    },
    logout() {
      this.token = ''; this.user = null
      localStorage.removeItem(TOKEN_KEY); localStorage.removeItem(USER_KEY)
    },
  },
})
```

- [ ] **Step 3: Login.vue 接线**

`handleLogin` 改为：校验 → `await auth.login(form.username, form.password)` → `router.push('/')`；失败 `ElMessage.error(e.message)`。体验账号卡片点击自动填表单（现有逻辑保留）。

- [ ] **Step 4: MainLayout 顶部用户 + 登出下拉**

`script setup` 引入 `useAuthStore`、`useRouter`；`const auth = useAuthStore()`；模板中 `系统管理员` 两处（sidebar-footer 与 topbar 用户入口）改为 `{{ auth.user?.display_name ?? '未登录' }}` + 角色标签；dropdown 增加 `@command` 处理：`logout` → `auth.logout()` + `router.push('/login')`。无 token 时（未登录）保持现状文案兜底。

- [ ] **Step 5: Accounts.vue + Profile.vue + 路由守卫**

Accounts：`onMounted` 拉 `listUsers()` → el-table（用户名/姓名/角色/操作）→「新建用户」对话框（用户名/姓名/角色 select/密码）+「删除」（ElMessageBox.confirm）；新增/删除后刷新。Profile：展示 `auth.user` 信息卡 + 「修改密码」表单（原密码/新密码）→ `changePassword` → 成功 ElMessage + 清空。

Router：`router.beforeEach((to) => { const auth = useAuthStore(); if (to.path !== '/login' && !auth.token) return '/login' })`（登录页放行）。account/profile 路由指向真实组件。（守卫放 `web/src/router/index.ts` 顶部，import store 时注意 Pinia 实例需在 app.use(pinia) 之后——**在 main.ts 中 `useAuthStore()` 于 beforeEach 内调用**，避免模块顶层实例化报错；更稳妥做法：守卫内 `import { useAuthStore } from '../stores/auth'`。）

- [ ] **Step 6: 门禁 + 联调**

Run: `cd web && npm run type-check && npm run build`；`cd backend && .venv/Scripts/python -m pytest -q`
Expected: 全绿

- [ ] **Step 7: Commit**

```bash
git add web/src/api/auth.ts web/src/api/users.ts web/src/stores/auth.ts \
  web/src/views/Login.vue web/src/layouts/MainLayout.vue \
  web/src/views/account/Accounts.vue web/src/views/account/Profile.vue \
  web/src/router/index.ts web/src/main.ts 2>/dev/null || true
git commit -m "feat(web): 登录接线 + 账户管理/我的档案 + 主布局真实用户"
```

---

## Task 9: 知识库操作列（详情/下载/重命名）+ 图谱「重新导入」按钮 + Q&A 反馈按钮

**Files:**
- Modify: `backend/app/api/documents.py`（详情/下载/重命名 + 下载路径校验）
- Create: `backend/tests/test_documents_ops.py`
- Modify: `web/src/api/documents.ts`、`web/src/views/knowledge/Library.vue`
- Modify: `web/src/api/graph.ts`、`web/src/views/graph/GraphExplore.vue`
- Modify: `web/src/views/qa/Chat.vue`（有用/无用反馈）

**Interfaces:**
- Consumes: `Document`、`UPLOAD_DIR`（阶段 4 已定路径）、`Feedback API`（Task 2）
- Produces: `GET /documents/{id}`（详情：DocumentOut + chunk_count + stored filename）；`GET /documents/{id}/download`（FileResponse，filename=原名，stored_path 必须位于 UPLOAD_DIR 内——防穿越）；`PUT /documents/{id} {name}`（重命名，同名 409，both status 校验）；前端 Library 表格操作列 = 详情(弹窗 Dialog 展示元数据) · 下载(a标签 href) · 重命名(ElMessageBox.prompt) · 删除(已有)；`POST /graph/import` 前端按钮「重新导入基础数据」（confirm 后调用，成功 ElMessage）

- [ ] **Step 1: 写失败测试 `test_documents_ops.py`**

```python
"""文档详情/下载/重命名（规格 P0-6 操作列）。"""
from app.db import session_scope
from app.models.document import Document


def _mk(client, name="验收语料.md") -> int:
    r = client.post("/api/documents", files={"file": (name, b"# 测试\n\n正文。", "text/markdown")},
                    data={"topic": "内科"})
    assert r.status_code == 200
    return r.json()["id"]


def test_detail_and_rename(client):
    did = _mk(client)
    r = client.get(f"/api/documents/{did}")
    assert r.status_code == 200
    d = r.json()
    assert d["name"] == "验收语料.md" and d["topic"] == "内科"

    r = client.put(f"/api/documents/{did}", json={"name": "新名字.md"})
    assert r.status_code == 200
    assert client.get(f"/api/documents/{did}").json()["name"] == "新名字.md"

    # 同名单重复 → 409
    _mk(client, "别档.md")
    dup = client.post("/api/documents", files={"file": ("新名字.md", b"x", "text/markdown")},
                      data={"topic": "内科"}).json()["id"]
    r = client.put(f"/api/documents/{dup}", json={"name": "新名字.md"})
    assert r.status_code == 409


def test_download_serves_file(client):
    did = _mk(client)
    r = client.get(f"/api/documents/{did}/download")
    assert r.status_code == 200
    assert r.content == b"# 测试\n\n正文。"
    assert "attachment" in r.headers.get("content-disposition", "")


def test_404s(client):
    assert client.get("/api/documents/999").status_code == 404
    assert client.get("/api/documents/999/download").status_code == 404
```

（注意：`_mk` 走后台 ingest——测试里 `ingest_document` 会被 BackgroundTasks 后台执行，可能失败但不会影响本组断言。若 `_mk` 的 ingest 抛错导致记录状态失败，详情/下载/重命名仍应工作——实现只依赖记录行。）

- [ ] **Step 2: 运行确认失败**

Run: `cd backend && .venv/Scripts/python -m pytest tests/test_documents_ops.py -v`
Expected: FAIL（404）

- [ ] **Step 3: documents.py 加三个端点**

```python
@router.get("/documents/{doc_id}")
def document_detail(doc_id: int) -> dict:
    with session_scope() as s:
        d = s.get(Document, doc_id)
        if d is None:
            raise HTTPException(status_code=404, detail="文档不存在")
        return DocumentOut.of(d).model_dump() | {"stored_file": Path(d.stored_path).name}


@router.get("/documents/{doc_id}/download")
def document_download(doc_id: int) -> FileResponse:
    with session_scope() as s:
        d = s.get(Document, doc_id)
        if d is None:
            raise HTTPException(status_code=404, detail="文档不存在")
        p = Path(d.stored_path).resolve()
        if not str(p).startswith(str(UPLOAD_DIR.resolve())):
            raise HTTPException(status_code=500, detail="存储路径异常")   # 防穿越兜底
        if not p.is_file():
            raise HTTPException(status_code=404, detail="源文件缺失")
        return FileResponse(p, filename=d.name)
```

需 import：`from fastapi.responses import FileResponse`。

改名端点（校验与上传对齐）：

```python
class RenameBody(BaseModel):
    name: str


@router.put("/documents/{doc_id}")
def rename_document(doc_id: int, body: RenameBody) -> dict:
    new_name = Path(body.name).name
    ext = new_name.rsplit(".", 1)[-1].lower() if "." in new_name else ""
    if ext not in SUPPORTED_EXTS:
        raise HTTPException(status_code=400, detail=f"不支持的文件格式：.{ext}")
    with session_scope() as s:
        d = s.get(Document, doc_id)
        if d is None:
            raise HTTPException(status_code=404, detail="文档不存在")
        dup = s.query(Document).filter(Document.name == new_name,
                                       Document.id != doc_id,
                                       Document.status != "失败").first()
        if dup is not None:
            raise HTTPException(status_code=409, detail=f"已存在同名文档《{new_name}》")
        d.name = new_name
        return DocumentOut.of(d).model_dump()
```

- [ ] **Step 4: 前端 documents.ts + Library 操作列**

`documents.ts` 增加 `getDocument(id)`、`downloadUrl(id)`（返回 `/api/documents/{id}/download` 字符串供 `<a :href>`）、`renameDocument(id, name)`、`reimportGraph()` 不归此类。

Library 表格操作列扩展（现有删除按钮旁）：

```html
<el-table-column label="操作" width="220">
  <template #default="{ row }">
    <el-button link type="primary" @click="showDetail(row)">详情</el-button>
    <el-button link type="primary" @click="download(row)">下载</el-button>
    <el-button link type="primary" @click="rename(row)">重命名</el-button>
    <el-button link type="danger" @click="removeDoc(row)">删除</el-button>
  </template>
</el-table-column>
```

`showDetail` → `ElDialog`（文档字段只读 + 来源文件 + 统计）；`download` → 临时 `<a>` 点击触发（`document.createElement('a')` + `click()`，或 `window.open(downloadUrl(row.id))`）；`rename` → `ElMessageBox.prompt('新名称', '重命名', ...)` 校验空/同后缀 → `renameDocument` → 刷新。

- [ ] **Step 5: 图谱「重新导入基础数据」+ GraphExplore 接线**

`api/graph.ts` 加：

```ts
export const reimportGraph = () =>
  fetch('/api/graph/import', { method: 'POST' }).then(async (resp) => {
    if (!resp.ok) throw new Error(`导入失败（${resp.status}）`)
    return resp.json()
  })
```

GraphExplore 顶部操作栏已有「重新导入基础数据」文字按钮（规格 P0-5 文案）——`@click="doReimport"`；

```ts
import { reimportGraph } from '../../api/graph'
async function doReimport() {
  try {
    await ElMessageBox.confirm('将以内置演示数据重新导入图谱（幂等，不覆盖已发布/候选状态）。', '重新导入', { type: 'warning' })
    const r = await reimportGraph()
    ElMessage.success(`已导入 ${r.imported.nodes} 节点 / ${r.imported.edges} 关系`)
    doSearch()
  } catch (e) {
    if (e === 'cancel') return
    ElMessage.error((e as Error).message)
  }
}
```

（按钮需真实存在——检查 GraphExplore 当前模板；若尚无按钮则不新增占位，直接补在操作栏。）

- [ ] **Step 6: Chat.vue 有用/无用反馈**

回答卡片（`.a` 内 `refs` 折叠之后）加：

```html
<div v-if="m.answer" class="feedback">
  <span class="fb-label">此回答有帮助吗？</span>
  <el-button link size="small" :type="m.feedback === true ? 'primary' : ''"
             :disabled="m.feedback !== undefined" @click="sendFeedback(m, true)">有用</el-button>
  <el-button link size="small" :type="m.feedback === false ? 'danger' : ''"
             :disabled="m.feedback !== undefined" @click="sendFeedback(m, false)">无用</el-button>
</div>
```

`QA` 类型加 `feedback?: boolean`；`sendFeedback`：

```ts
async function sendFeedback(m: QA, useful: boolean) {
  m.feedback = useful
  try {
    const resp = await fetch('/api/feedback', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ session_id: sessionId.value, useful }),
    })
    if (!resp.ok) throw new Error(`反馈提交失败（${resp.status}）`)
  } catch (e) {
    m.feedback = undefined
    ElMessage.error((e as Error).message)
  }
}
```

- [ ] **Step 7: 门禁**

Run: `cd backend && .venv/Scripts/python -m pytest -q`；`cd web && npm run type-check && npm run build`
Expected: 全绿

- [ ] **Step 8: Commit**

```bash
git add backend/app/api/documents.py backend/tests/test_documents_ops.py \
  web/src/api/documents.ts web/src/views/knowledge/Library.vue \
  web/src/api/graph.ts web/src/views/graph/GraphExplore.vue web/src/views/qa/Chat.vue
git commit -m "feat(web): 知识库详情/下载/重命名 + 图谱重导入 + 问答反馈"
```

---

## Task 10: ECharts 按需重构 GraphExplore + .gitattributes 行尾归一

**Files:**
- Modify: `web/src/views/graph/GraphExplore.vue`（`import * as echarts from 'echarts'` → 按需：GraphChart + regBase 扩展）
- Modify: `web/src/utils/echarts.ts`（增加 GraphChart 注册：`regGraph()`）
- Create: `.gitattributes`
- （如改行尾）：`git add --renormalize` 提交行尾归一（~20 文件 CRLF→LF）

**Interfaces:**
- Consumes: 现有 GraphExplore 的 echarts 用法（`echarts.init` / `echarts.ECharts` 类型）
- Produces: GraphExplore 只依赖按需注册（`use([GraphChart])`）；`.gitattributes` 内容 `* text=auto eol=lf`；`git status` 中文档文件全部 LF

- [ ] **Step 1: utils/echarts.ts 加 GraphChart**

```ts
import { GraphChart } from 'echarts/charts'

export function regGraph(): void {
  use([GraphChart, CanvasRenderer, GridComponent, TooltipComponent, LegendComponent, TitleComponent])
}
```

- [ ] **Step 2: GraphExplore 换按需引入**

```ts
import { init, type ECharts, type EChartsOption } from 'echarts/core'
import { regGraph } from '../../utils/echarts'
regGraph()
```

替换文件中 `import * as echarts from 'echarts'`；`echarts.init` → `init`；`echarts.ECharts` → `ECharts`（type import）；`echarts.EChartsOption`（若用）→ `EChartsOption`；其余 `echarts.` 引用逐一删前缀。GraphChart 的 option 里 `type: 'graph'` 保持。

- [ ] **Step 3: 门禁 + 构建体积观察**

Run: `cd web && npm run type-check && npm run build`
Expected: 成功；`✓ built` 输出中无 >500kB 警告（或警告消失/减小；有则记录数字变化）

- [ ] **Step 4: .gitattributes + 行尾归一**

创建 `.gitattributes`：

```gitattributes
* text=auto eol=lf
*.svg text eol=lf
*.png binary
*.jpg binary
*.jpeg binary
*.ico binary
```

检查当前行尾：

```bash
git ls-files --eol | grep -i crlf | head -30
```

若存在 CRLF 文件：

```bash
git add --renormalize . && git status
```

Expected: 变更集中在文本文件行尾归一（~20 个）；若无 CRLF 文件则该步为空提交跳过。**注意**：`git add --renormalize .` 可能把大量文件标记 modified——审查 `git status` 后**故意分文件提交**，与业务代码同批提交时保持 diff 干净（一个「chore: normalize line endings」提交）。

- [ ] **Step 5: 提交（两个独立提交）**

```bash
git add web/src/views/graph/GraphExplore.vue web/src/utils/echarts.ts
git commit -m "refactor(web): 图谱页 ECharts 按需引入"

git add .gitattributes && git add --renormalize .
git commit -m "chore(repo): 行尾统一 LF（.gitattributes + renormalize）"  # 若实际有变更才提交
```

---

## Task 11: 端到端实测验收（阶段 5 验收记录）

**Files:**
- Create: `docs/superpowers/plans/stage5-verification.md`
- Modify：无业务代码

**Interfaces:**
- Consumes: 全部阶段 5 产物；`deploy/docker-compose.yml` 的 mysql/neo4j；`backend/.env`（真实 Key）；前端 dev server

- [ ] **Step 1: 起服务**

```bash
docker compose -f deploy/docker-compose.yml up -d mysql neo4j
cd backend && .venv/Scripts/python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
cd web && npm run dev
```

Expected: /health 200；MySQL/Neo4j 就绪

- [ ] **Step 2: 门禁全绿**

```bash
cd backend && .venv/Scripts/python -m pytest -q
cd web && npm run type-check && npm run build
```

Expected: 全绿；构建无新增警告

- [ ] **Step 3: 图谱重导入 + neighbors 真实冒烟**

```bash
curl -s -X POST http://127.0.0.1:8000/api/graph/import
curl -s "http://127.0.0.1:8000/api/graph/neighbors?name=四君子汤&hop=2"
```

Expected: import `{"imported":{"nodes":33,"edges":32}}`；neighbors 无候选边、links 无重复；不含 `风热犯表-表现->口渴` 候选探针（若还在库里）

- [ ] **Step 4: 推理配置到问答生效闭环**

```
PUT /api/config {"semantic_k": 3, ...} → 200
POST /api/chat/stream (四君子汤问题) → step retrieve.vector_n ≈ 3（不超过语义召回数）
PUT /api/config 恢复 20 → 200
浏览器推理配置页：默认 20/20/25/5/60/0.30/0.10 → 改 + 保存 → 新请求生效提示
```

Expected: 配置页保存后 `vector_n` 受 `semantic_k` 约束（真实链路生效）

- [ ] **Step 5: 运行概览真实数据**

```
问 2~3 个问题（产生 retrieval_log）；浏览器点 2 个「有用/无用」反馈
GET /api/stats/overview → trend 今天 count≥2、quality.total≥2、useful/useless 与点击一致
浏览器运行概览页：5 卡渲染、趋势折线今天有值、状态分布含就绪、检索质量进度条非 0
```

Expected: 概览数据与手动操作一一对应（非写死）

- [ ] **Step 6: 登录/账户/档案浏览器验收**

```
/qa 未登录 → 重定向 /login；体验账号 admin → 登录 → 主布局显示「系统管理员·管理员」
账户管理页列表 3 种子用户；新建/删除一个用户；我的档案改密码 → 重新登录生效
```

Expected: 守卫/登录/账户闭环 OK

- [ ] **Step 7: 知识库操作列浏览器验收**

```
典籍知识库 → 详情弹窗、下载文件、重命名 → 列表刷新；图谱页「重新导入基础数据」→ 成功提示
```

Expected: 无报错；下载文件名=原名（若为上传文件名）

- [ ] **Step 8: 收尾**

```
浏览器视觉截图（运行概览/推理配置/账户管理/我的档案 4 页）留档；
停服务；写 stage5-verification.md（结论 DONE / DONE_WITH_CONCERNS + 缺陷证据，参照前四阶段格式）
```

- [ ] **Step 9: Commit 验收记录**

```bash
git add docs/superpowers/plans/stage5-verification.md
git commit -m "docs(verification): 阶段 5 端到端实测验收记录"
```

---

## Self-Review 对照（规格 → 任务）

| 规格/遗留项 | 落地任务 |
|---|---|
| P1 运行概览 5 卡 + 数据真实性 | Task 3（后端统计）+ Task 6（Dashboard） |
| P1 推理配置页（默认值 20/20/25/5/60、0.30/0.10） | Task 1（后端）+ Task 7（前端） |
| 变更保存后立即应用 | Task 1+7（DB 落库 + state 注入） |
| P2 账户管理/我的档案 | Task 4（后端）+ Task 8（前端） |
| P0-6 详情/下载/重命名 | Task 9 |
| P0-5 重新导入基础数据 | Task 5 + 9 |
| 图谱遍历去重 / 2-hop 中间节点过滤 | Task 5 |
| retrieval_log/feedback 持久化 | Task 2 + 3 |
| ECharts 按需（消除 >500kB 警告） | Task 6 + 10 |
| .gitattributes 行尾归一 | Task 10 |
| 登录接线（登录页 TODO 阶段 4+） | Task 4 + 8 |
| 不新增原图不存在的面板 | 反馈按钮=轻量操作（Task 9 注明），非面板 |

**占位符扫描**：每个任务含可运行测试 + 完整实现要点；无「TBD/implement later」。Task 6 的图表初始化主体（init/dispose/resize）指向 GraphExplore 既有模式并给出容器骨架——实现细节由实现者按既有代码补齐（已给出全部 option 函数与布局）。

**类型一致性**：`load_inference_config` 返回 dict 字段 = `InferenceConfig` 模型字段 = `ConfigBody` 字段 = 前端 `InferenceConfig` 接口字段（semantic_k/keyword_k/fuse_candidate/final_evidence/rrf_k/model/answer_temp/query_temp）；`_log_retrieval`/`RetrievalLog` 字段与 Task 3 统计一致；`/api/stats/overview` 返回键 = `OverviewData` 接口键。