# 阶段 3：Agentic 化（LangGraph 状态机 + Tool 路由 + 自反思 + SSE + 安全兜底）实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把阶段 2 的"固定三路调用"升级为由 LangGraph 状态机按意图路由、证据不足自反思重查（≤1 轮）的 Agentic RAG，主接口换成 SSE 流式 `/api/chat/stream`，前端打字机 + 溯源弹窗逐步点亮。

**Architecture:** LangGraph `StateGraph` 编排检索阶段（understand → 条件路由 → retrieve → fuse → 自反思条件边 → safety → context），每个节点产出事件化为 SSE 的 `step` 事件；生成阶段由宿主 API 层用流式 LLM 逐 token 输出（`event: token`）（Ruling S1：图只编排检索与安全决策，真实流式生成在图外，保证 httpx 流式 token 精确且图事件与 token 事件解耦）。三路检索封装为 `langchain_core.tools.tool` 标准 Tool（Function Calling 证据），按 `PLAN_MATRIX`（意图→工具子集）路由，不用自由 ReAct 循环（医疗可控性）。多轮记忆用内存会话 dict（Ruling S2：方案 REDIS_MODE=memory 起步，不引入 LangGraph checkpointer）。

**Tech Stack:** Python 3.12、FastAPI、LangGraph + langchain-core、httpx 流式、现有 jieba/rank-bm25/neo4j。SSE 手写（`event:` / `data:` 帧，不引入 sse-starlette）。

**Spec:** `docs/MediRAG-合并改造方案.md`（4.1 架构图、4.2 状态/节点/路由矩阵、4.3 SSE 协议、4.4 安全兜底、6.7 Prompt 体系、阶段 3 验证）+ `docs/前端还原规格.md`（P0-2 空态、P0-3 回答态、P0-4 溯源弹窗、三 全局交互）

## Global Constraints

- 测试不得依赖真实网络 / Neo4j / LLM：LLM 调用（`chat_completion` / `chat_completion_stream`）与检索依赖全部 monkeypatch/fake，沿用 `backend/tests/` 既有模式。构建门禁：`cd web && npm run build` + `npm run type-check` 零报错。
- SSE 协议（方案 4.3，逐字）：`event: step`（understand/retrieve/reflect/fuse/rerank）、`event: token`（`{text}`）、`event: references`（`{docs, graph_facts}`）、`event: safety`（`{type, message}`）、`event: done`（`{message_id, metrics}`）。
- 意图枚举 `relation / concept / complex / chitchat`；路由矩阵（方案 4.2 逐字）：relation=向量+图谱、concept=向量+关键词、complex=三路全开、chitchat=不调工具。
- 自反思硬上限 `REFLECT_MAX = 1`（防死循环）。触发条件：检索阶段结束且 `not evidence 或 top < evidence_min_score` 且无图谱事实。
- 医疗安全兜底不可绕过：证据不足必须拒答"知识库中未检索到可靠依据"，宁可说不知道也不编造；急症词命中顶部强制就医话术（方案 4.4）。
- 设计 token 一律取 `web/src/styles/theme.ts`；文案以《前端还原规格》为准不得自造。
- 复用阶段 2 已审查模块：`app.retrieval.vector_store.get_store`、`app.retrieval.keyword.get_keyword_index`、`app.retrieval.rrf.rrf_fuse`、`app.llm.rerank.rerank`、`app.llm.embedding.embed_texts`、`app.llm.chat.chat_completion`、`app.graph.neo4j_client.get_graph`、`app.graph.entity_recognizer.recognize_entities`、`app.graph.neo4j_client`、`app.safety.*`（新建）。
- `/api/chat/ask` 由 `/api/chat/stream` 取代（单接口，不保留 ask 双路径）；`answer_cn_tcm.txt` 的【图谱事实】与【文献证据】约束沿用。
- 推理配置默认值沿用阶段 2：`semantic_k=20 / keyword_k=20 / fuse_candidate=25 / final_evidence=5 / rrf_k=60 / rerank_top_n=5 / evidence_min_score=0.3`。

---

## 文件结构

| 文件 | 责任 |
|---|---|
| `backend/app/agent/state.py`（新建） | `AgentState` TypedDict |
| `backend/app/agent/tools.py`（新建） | 三检索 `@tool`（vector_search / keyword_search / graph_search） |
| `backend/app/agent/nodes/understand.py`（新建） | 问句理解节点（结构化 LLM + 降级词典识别） |
| `backend/app/agent/nodes/retrieve.py`（新建） | 按 plan 并行调用 Tool |
| `backend/app/agent/nodes/fuse.py`（新建） | RRF + rerank 融合节点 |
| `backend/app/agent/nodes/reflect.py`（新建） | 自反思改写节点 |
| `backend/app/agent/nodes/safety.py`（新建） | 急症/置信度安全判定节点 |
| `backend/app/agent/nodes/context.py`（新建） | 组装生成 Prompt（文献+图谱） |
| `backend/app/agent/nodes/route.py`（新建） | PLAN_MATRIX + 两个条件边函数 |
| `backend/app/agent/workflow.py`（新建） | StateGraph 组装 + `get_agent()` |
| `backend/app/agent/memory.py`（新建） | 内存会话 dict（历史 8 条、写入） |
| `backend/app/agent/prompts/query_understand.txt`（新建） | 理解 Prompt（Few-shot JSON） |
| `backend/app/agent/prompts/query_rewrite_reflect.txt`（新建） | 反思改写 Prompt |
| `backend/app/agent/prompts/answer_cn_tcm.txt`（修改） | 保留第 2 条约束，移除"未检索到可靠依据"硬话术（交给 safety 节点） |
| `backend/app/safety/emergency.py`（新建） | 急症词表 + `detect_emergency` |
| `backend/app/safety/__init__.py`（新建） | 空 |
| `backend/app/llm/chat.py`（修改） | + `chat_completion_stream`（httpx stream） |
| `backend/app/api/chat.py`（修改） | ask → `/api/chat/stream` SSE |
| `backend/requirements.txt`（修改） | + langgraph + langchain-core |
| `backend/tests/test_*`（新建/修改） | 见各 Task |

---

### Task 1: 依赖 + state + 急症词表 + Prompt 文件骨架

**Files:**
- Modify: `backend/requirements.txt`
- Create: `backend/app/agent/__init__.py`（空）、`backend/app/agent/state.py`
- Create: `backend/app/safety/__init__.py`（空）、`backend/app/safety/emergency.py`
- Create: `backend/app/agent/prompts/query_understand.txt`、`backend/app/agent/prompts/query_rewrite_reflect.txt`
- Test: `backend/tests/test_state.py`、`backend/tests/test_emergency.py`

**Interfaces:**
- Produces: `AgentState`（后述字段，全部任务共用）；`detect_emergency(text: str) -> bool`；常量 `EMERGENCY_WORDS: list[str]`。

- [ ] **Step 1: 追加依赖**

修改 `backend/requirements.txt`，在 jieba 行后追加：

```
# 阶段 3：Agent 编排
langgraph>=0.2.0
langchain-core>=0.3.0
```

安装：`cd backend && .venv/Scripts/python -m pip install "langgraph>=0.2.0" "langchain-core>=0.3.0"`

- [ ] **Step 2: 写失败测试** `backend/tests/test_state.py` + `backend/tests/test_emergency.py`

```python
# test_state.py
def test_agent_state_has_required_fields():
    from app.agent.state import AgentState
    assert AgentState.__annotations__["question"] is str
    assert AgentState.__annotations__["intent"] is str
    assert AgentState.__annotations__["plan"] is list
    assert AgentState.__annotations__["reflect_count"] is int
    assert AgentState.__annotations__["safety_flag"] is str
    from typing import get_origin
    assert get_origin(AgentState.__annotations__["trace"]) is list      # Annotated[list, add]


# test_emergency.py
from app.safety.emergency import detect_emergency, EMERGENCY_WORDS


def test_detect_emergency_hits_keyword():
    assert detect_emergency("我胸口疼得厉害怎么用中医药调理") is True


def test_detect_emergency_no_keyword():
    assert detect_emergency("四君子汤由哪些中药组成") is False


def test_emergency_words_contains_required():
    for w in ["胸痛", "昏迷", "大出血", "休克", "孕妇出血"]:
        assert w in EMERGENCY_WORDS
```

- [ ] **Step 3: 运行确认失败**

Run: `cd backend && .venv/Scripts/python -m pytest tests/test_state.py tests/test_emergency.py -v`
Expected: FAIL（`ModuleNotFoundError: app.agent.state` / `app.safety.emergency`）

- [ ] **Step 4: 实现**

`backend/app/agent/state.py`：

```python
"""AgentState：LangGraph 状态机共享状态（合并方案 4.2，字段与 SSE trace 对应）。"""
from operator import add
from typing import Annotated, TypedDict


class AgentState(TypedDict):
    question: str                     # 用户原始问题
    session_id: str                   # 会话标识（多轮记忆）
    chat_history: list                # [{"role": "user"|"assistant", "content": str}, ...]
    rewritten_query: str              # 理解/反思后的检索查询
    entities: list                    # [{"name", "type", "matched"}, ...]
    entity_names: list                # 实体名的扁平列表（供图谱检索）
    intent: str                       # relation / concept / complex / chitchat
    plan: list                        # 本次路由的工具名列表（vector_search / keyword_search / graph_search）
    vector_hits: list                 # 向量召回
    keyword_hits: list                # 关键词召回
    graph_facts: list                 # 图谱事实（独立汇合，不参与 RRF）
    fused: list                       # RRF 融合截断后候选
    evidence: list                    # rerank 后最终证据
    confidence: float                 # max(evidence.score)
    low_confidence: bool              # 阈值判定
    reflect_count: int                # 自反思轮次（硬上限 1）
    safety_flag: str | None           # emergency / low_confidence / ok
    safety_message: str               # 急救提示或拒答话术（safety 节点产出）
    prompt: str                       # 组装好的最终生成 Prompt（供宿主流式生成）
    answer: str                       # 兜底固定话术（非流式）或最终完整回答（流式完成后回填供记忆）
    trace: Annotated[list, add]       # SSE step 事件流：节点只返回本次新增事件，langgraph 自动累计
```

`backend/app/safety/emergency.py`：

```python
"""急症词表拦截（方案 4.4-2）：问题命中急症症状时强制就医引导。"""

EMERGENCY_WORDS = [
    "胸痛", "胸口疼", "昏迷", "晕厥", "大出血", "休克", "孕妇出血",
    "孕妇腹痛", "呼吸困难", "咯血", "吐血", "便血", "黑便", "剧烈头痛",
    "突发瘫痪", "抽搐", "气道异物",
]


def detect_emergency(text: str) -> bool:
    """任意急症词命中即返回 True。"""
    return any(w in text for w in EMERGENCY_WORDS)
```

`backend/app/agent/prompts/query_understand.txt`：

```text
你是"本草智问"的问句理解器。结合【历史对话】与【当前问题】，输出**严格 JSON**（不要输出 JSON 之外的任何文字）：

{{
  "rewritten_query": "把指代、省略消解后的完整检索查询（若历史无指代则基本等同当前问题）",
  "entities": [{{"name": "中医药实体名", "type": "方剂|中药|证候|症状|功效|禁忌"}}],
  "intent": "relation|concept|complex|chitchat"
}}

意图判定规则：
- relation：问题指向单个明确实体、询问其组成/主治/功效/禁忌等关系 → 图谱为主。
- concept：无一实体、需对比或辨析机理（如"风寒束表与风热犯表区别"）→ 文献为主。
- complex：实体加开放式阐述的综合问题（如"脾气虚常见哪些症状和方剂"）→ 三路全开。
- chitchat：超出中医药知识库范围或与健康知识无关（如天气、闲聊）→ 不检索直接兜底。

【历史对话】（可能为空）
{history}

【当前问题】
{question}
```

`backend/app/agent/prompts/query_rewrite_reflect.txt`：

```text
你是"本草智问"的检索改写器。首轮检索证据不足，请改写查询词以提高召回。只输出改写后的查询词（一行，不要引号、不要解释）。

失败原因：{reason}
原始问题：{question}
上次检索查询：{rewritten_query}
【历史对话】（可能为空）
{history}

改写要求：保留原意与关键实体，可换更宽泛/更常见的表达或拆分术语；不要引入原文未出现的新事实。
```

- [ ] **Step 5: 运行确认通过**

Run: `cd backend && .venv/Scripts/python -m pytest tests/test_state.py tests/test_emergency.py -v`
Expected: PASS（5 passed）

- [ ] **Step 6: Commit**

```bash
git add backend/requirements.txt backend/app/agent/__init__.py backend/app/agent/state.py backend/app/safety/__init__.py backend/app/safety/emergency.py backend/app/agent/prompts/query_understand.txt backend/app/agent/prompts/query_rewrite_reflect.txt backend/tests/test_state.py backend/tests/test_emergency.py
git commit -m "feat(agent): AgentState, emergency wordlist, understand/reflect prompts"
```

---

### Task 2: 三检索 Tool 化

**Files:**
- Create: `backend/app/agent/tools.py`
- Test: `backend/tests/test_agent_tools.py`

**Interfaces:**
- Consumes: `get_store().search`, `get_keyword_index().search`, `get_graph().neighbors`, `embed_texts`
- Produces: `vector_search(query: str, top_k: int = 20) -> list[dict]`（langchain `@tool`）、`keyword_search(query: str, top_k: int = 20) -> list[dict]`、`graph_search(entity: str, hop: int = 1) -> dict`（返回 `{"entity", "facts"}`）；常量 `TOOL_NAMES = {"vector_search", "keyword_search", "graph_search"}`。Tool 是 langchain `StructuredTool`，可通过 `.invoke({...})` 调用、`.name` 取名。

- [ ] **Step 1: 写失败测试** `backend/tests/test_agent_tools.py`

```python
from unittest.mock import MagicMock

import app.agent.tools as tmod
from app.agent.tools import TOOL_NAMES, graph_search, keyword_search, vector_search


def test_tool_names_set():
    assert TOOL_NAMES == {"vector_search", "keyword_search", "graph_search"}


def test_vector_search_invokes_store(monkeypatch):
    fake_store = MagicMock()
    fake_store.search.return_value = [{"chunk_id": "a", "title": "四君子汤"}]
    monkeypatch.setattr(tmod, "get_store", lambda: fake_store)
    monkeypatch.setattr(tmod, "embed_texts", lambda texts: [[0.1, 0.2]])

    hits = vector_search.invoke({"query": "四君子汤组成", "top_k": 5})

    assert hits == [{"chunk_id": "a", "title": "四君子汤"}]
    fake_store.search.assert_called_once()
    assert fake_store.search.call_args.args[1] == 5


def test_keyword_search_invokes_index(monkeypatch):
    fake_idx = MagicMock()
    fake_idx.search.return_value = [{"chunk_id": "k1"}]
    monkeypatch.setattr(tmod, "get_keyword_index", lambda: fake_idx)

    hits = keyword_search.invoke({"query": "风寒束表", "top_k": 3})

    assert hits == [{"chunk_id": "k1"}]
    fake_idx.search.assert_called_once()


def test_graph_search_wraps_neighbors(monkeypatch):
    fake_graph = MagicMock()
    fake_graph.neighbors.return_value = [{"source": "四君子汤", "relation": "组成", "target": "人参"}]
    monkeypatch.setattr(tmod, "get_graph", lambda: fake_graph)

    out = graph_search.invoke({"entity": "四君子汤", "hop": 1})

    assert out["entity"] == "四君子汤"
    assert out["facts"][0]["relation"] == "组成"
    fake_graph.neighbors.assert_called_once_with(["四君子汤"], hop=1)
```

- [ ] **Step 2: 运行确认失败**

Run: `cd backend && .venv/Scripts/python -m pytest tests/test_agent_tools.py -v`
Expected: FAIL（`ModuleNotFoundError: app.agent.tools`）

- [ ] **Step 3: 实现** `backend/app/agent/tools.py`

```python
"""三个检索 Tool（Function Calling 的直接证据，合并方案 6.2）。

用 langchain_core.tools.tool 封装，与 LangGraph 状态机的"条件路由"配合，
由 PLAN_MATRIX 决定调用子集；不用自由 ReAct 循环（医疗可控性）。
"""
from langchain_core.tools import tool

from app.graph.neo4j_client import get_graph
from app.llm.embedding import embed_texts
from app.retrieval.keyword import get_keyword_index
from app.retrieval.vector_store import get_store


@tool
def vector_search(query: str, top_k: int = 20) -> list:
    """语义向量检索：用于概念解释、机理对比、症状与方剂关联等需要语义理解的问题。
    返回切片文本、文档名、章节、页码、相似度分数。"""
    embedding = embed_texts([query])[0]
    return get_store().search(embedding, top_k=top_k)


@tool
def keyword_search(query: str, top_k: int = 20) -> list:
    """关键词检索(BM25)：用于精确匹配中医药专有名词、方剂名、药材名、术语缩写。
    返回切片文本与 BM25 分数。"""
    return get_keyword_index().search(query, top_k=top_k)


@tool
def graph_search(entity: str, hop: int = 1) -> dict:
    """中医药知识图谱检索：查询某实体(药材/方剂/证候/症状/功效/禁忌)的 1~2 跳关系，
    返回节点、关系、路径，用于组成、配伍、禁忌等事实型问题。返回 {"entity", "facts"}。"""
    return {"entity": entity, "facts": get_graph().neighbors([entity], hop=hop)}


TOOL_NAMES = {"vector_search", "keyword_search", "graph_search"}
```

- [ ] **Step 4: 运行确认通过**

Run: `cd backend && .venv/Scripts/python -m pytest tests/test_agent_tools.py -v`
Expected: PASS（4 passed）

- [ ] **Step 5: Commit**

```bash
git add backend/app/agent/tools.py backend/tests/test_agent_tools.py
git commit -m "feat(agent): three retrieval tools as langchain StructuredTool"
```

---

### Task 3: 问句理解节点（结构化 LLM + 降级）

**Files:**
- Create: `backend/app/agent/nodes/__init__.py`（空）、`backend/app/agent/nodes/understand.py`
- Test: `backend/tests/test_understand.py`

**Interfaces:**
- Consumes: `chat_completion(system, user, temperature)`、`get_graph().all_entities()`、`recognize_entities(question, vocab)`、prompt 文件 `query_understand.txt`
- Produces: `understand(state: AgentState) -> dict`（返回部分 state 更新：`rewritten_query / entities / entity_names / intent / trace`）；内部 `_parse_understand(raw: str) -> dict | None`。降级路径：解析失败时 `rewritten_query=question`、`entities=词典识别结果`、`intent = "complex" if 命中实体 else "chitchat"`。

- [ ] **Step 1: 写失败测试** `backend/tests/test_understand.py`

```python
import app.agent.nodes.understand as umod
from app.agent.nodes.understand import _parse_understand, understand


def _state(**over):
    base = {
        "question": "四君子汤由哪些中药组成？",
        "session_id": "s1", "chat_history": [], "entity_names": [],
        "entities": [], "intent": "", "plan": [], "trace": [], "reflect_count": 0,
    }
    base.update(over)
    return base


def test_parse_understand_valid_json():
    raw = '{"rewritten_query": "四君子汤的中药组成成分", "entities": [{"name": "四君子汤", "type": "方剂"}], "intent": "relation"}'
    d = _parse_understand(raw)
    assert d["intent"] == "relation"
    assert d["entities"][0]["name"] == "四君子汤"


def test_parse_understand_invalid_returns_none():
    assert _parse_understand("不是 JSON") is None
    assert _parse_understand('{"intent": "bogus"}') is None


def test_understand_parses_llm_output(monkeypatch):
    monkeypatch.setattr(umod, "get_graph", lambda: _FakeGraph())
    monkeypatch.setattr(
        umod, "chat_completion",
        lambda system, user, temperature: (
            '{"rewritten_query": "四君子汤的中药组成成分", '
            '"entities": [{"name": "四君子汤", "type": "方剂"}], "intent": "relation"}'
        ),
    )
    upd = understand(_state())
    assert upd["intent"] == "relation"
    assert upd["entity_names"] == ["四君子汤"]
    assert upd["trace"][0]["step"] == "understand"


def test_understand_falls_back_to_lexicon_on_garbage(monkeypatch):
    monkeypatch.setattr(umod, "get_graph", lambda: _FakeGraph2())
    monkeypatch.setattr(umod, "chat_completion", lambda *a, **k: "抱歉我不确定")
    upd = understand(_state(question="人参的功效是什么"))
    assert upd["intent"] == "complex"          # 词典命中实体 → 视为综合问题
    assert "人参" in upd["entity_names"]


class _FakeGraph:
    def all_entities(self):
        return [{"name": "四君子汤", "alias": "", "type": "方剂"}]


class _FakeGraph2:
    def all_entities(self):
        return [{"name": "人参", "alias": "园参、山参", "type": "中药"}]
```

- [ ] **Step 2: 运行确认失败**

Run: `cd backend && .venv/Scripts/python -m pytest tests/test_understand.py -v`
Expected: FAIL（`ModuleNotFoundError: app.agent.nodes.understand`）

- [ ] **Step 3: 实现** `backend/app/agent/nodes/understand.py`

```python
"""问句理解节点：一次 LLM 调用输出 改写查询/实体/意图（结构化 JSON），失败降级到词典识别。"""
import json
import re
from pathlib import Path

from app.agent.state import AgentState
from app.graph.entity_recognizer import recognize_entities
from app.graph.neo4j_client import get_graph
from app.llm.chat import chat_completion

PROMPTS_DIR = Path(__file__).resolve().parents[2] / "agent" / "prompts"

VALID_INTENTS = {"relation", "concept", "complex", "chitchat"}


def _parse_understand(raw: str) -> dict | None:
    """从 LLM 输出容忍提取 JSON；非法/字段缺失返回 None。"""
    text = raw.strip()
    text = re.sub(r"^```(?:json)?|```$", "", text, flags=re.MULTILINE).strip()
    try:
        d = json.loads(text)
    except (json.JSONDecodeError, ValueError):
        m = re.search(r"\{.*\}", text, flags=re.DOTALL)
        if not m:
            return None
        try:
            d = json.loads(m.group(0))
        except (json.JSONDecodeError, ValueError):
            return None
    if not isinstance(d, dict) or d.get("intent") not in VALID_INTENTS:
        return None
    ents = d.get("entities")
    if not isinstance(ents, list):
        return None
    return {"rewritten_query": str(d.get("rewritten_query") or ""),
            "entities": [e for e in ents if isinstance(e, dict) and e.get("name")],
            "intent": d["intent"]}


def understand(state: AgentState) -> dict:
    """理解节点：结构化 LLM；失败则用词典识别兜底（保证链路不因格式问题中断）。"""
    history_block = _history_block(state.get("chat_history") or [])
    prompt = (PROMPTS_DIR / "query_understand.txt").read_text(encoding="utf-8").format(
        history=history_block, question=state["question"])

    try:
        raw = chat_completion(system="你是中医药问句理解器，只输出 JSON。", user=prompt, temperature=0.1)
    except RuntimeError:
        raw = ""
    parsed = _parse_understand(raw) if raw else None

    if parsed is None:
        vocab = get_graph().all_entities()
        ents = recognize_entities(state["question"], vocab)
        parsed = {
            "rewritten_query": state["question"],
            "entities": ents,
            "intent": "complex" if ents else "chitchat",
        }

    entities = [{"name": e["name"], "type": e.get("type", ""), "matched": e.get("matched", e["name"])}
                for e in parsed["entities"]]
    entity_names = [e["name"] for e in entities]
    trace_evt = {
        "step": "understand",
        "raw": state["question"],
        "rewritten": parsed["rewritten_query"] or state["question"],
        "entities": entity_names,
        "intent": parsed["intent"],
    }
    return {
        "rewritten_query": parsed["rewritten_query"] or state["question"],
        "entities": entities,
        "entity_names": entity_names,
        "intent": parsed["intent"],
        "trace": [trace_evt],
    }


def _history_block(history: list) -> str:
    if not history:
        return "（无）"
    lines = []
    for m in history[-8:]:
        who = "用户" if m["role"] == "user" else "助手"
        lines.append(f"【{who}】{m['content']}")
    return "\n".join(lines)
```

- [ ] **Step 4: 运行确认通过**

Run: `cd backend && .venv/Scripts/python -m pytest tests/test_understand.py -v`
Expected: PASS（4 passed）

- [ ] **Step 5: Commit**

```bash
git add backend/app/agent/nodes/__init__.py backend/app/agent/nodes/understand.py backend/tests/test_understand.py
git commit -m "feat(agent): query understanding node with structured JSON + lexicon fallback"
```

---

### Task 4: 检索 + 融合节点 + 路由函数

**Files:**
- Create: `backend/app/agent/nodes/route.py`、`backend/app/agent/nodes/retrieve.py`、`backend/app/agent/nodes/fuse.py`
- Test: `backend/tests/test_retrieve_fuse.py`

**Interfaces:**
- Consumes: `vector_search/keyword_search/graph_search`（Task 2）、`rrf_fuse`、`rerank`、`get_settings`
- Produces: `route(state) -> str`（条件边："retrieve" | "safety"）、`PLAN_MATRIX: dict[str, list[str]]`、`retrieve(state) -> dict`（更新 `vector_hits/keyword_hits/graph_facts/plan/trace`）、`fuse(state) -> dict`（更新 `fused/evidence/confidence/low_confidence/trace`）、`reflect_edge(state) -> str`（条件边："reflect" | "safety"）、`REFLECT_MAX = 1`。

- [ ] **Step 1: 写失败测试** `backend/tests/test_retrieve_fuse.py`

```python
import app.agent.nodes.fuse as fmod
import app.agent.nodes.retrieve as rmod
from app.agent.nodes.route import PLAN_MATRIX, route
from app.agent.nodes.fuse import fuse, reflect_edge, REFLECT_MAX


def _state(**over):
    base = {
        "question": "q", "session_id": "s", "chat_history": [], "rewritten_query": "q",
        "entities": [], "entity_names": [], "intent": "complex", "plan": [],
        "vector_hits": [], "keyword_hits": [], "graph_facts": [], "trace": [],
        "fused": [], "evidence": [], "confidence": 0.0, "low_confidence": False,
        "reflect_count": 0, "safety_flag": None, "safety_message": "", "prompt": "",
        "answer": "",
    }
    base.update(over)
    return base


def test_plan_matrix_routing():
    assert PLAN_MATRIX["relation"] == ["vector_search", "graph_search"]
    assert PLAN_MATRIX["concept"] == ["vector_search", "keyword_search"]
    assert PLAN_MATRIX["complex"] == ["vector_search", "keyword_search", "graph_search"]
    assert PLAN_MATRIX["chitchat"] == []


def test_route_returns_safety_for_chitchat():
    assert route(_state(intent="chitchat")) == "safety"
    assert route(_state(intent="relation")) == "retrieve"


def test_retrieve_invokes_tools_per_plan(monkeypatch):
    calls = []

    class FakeTool:
        def __init__(self, name):
            self._name = name
        def invoke(self, kwargs):
            calls.append(self._name)
            return {"fact": self._name}

    rmod.TOOLS = {n: FakeTool(n) for n in ["vector_search", "keyword_search", "graph_search"]}
    upd = rmod.retrieve(_state(intent="complex", entity_names=["四君子汤"], rewritten_query="四君子汤组成"))
    assert upd["plan"] == ["vector_search", "keyword_search", "graph_search"]
    assert calls == ["vector_search", "keyword_search", "graph_search"]
    assert upd["trace"][0]["step"] == "retrieve"


def test_retrieve_skips_graph_without_entities(monkeypatch):
    calls = []

    class FakeTool:
        def __init__(self, name):
            self._name = name
        def invoke(self, kwargs):
            calls.append(self._name)
            return {"fact": self._name}

    rmod.TOOLS = {n: FakeTool(n) for n in ["vector_search", "keyword_search", "graph_search"]}
    rmod.retrieve(_state(intent="concept", entity_names=[], rewritten_query="风寒束表与风热犯表的区别"))
    assert "graph_search" not in calls        # 无实体 → 跳过图谱
    assert calls == ["vector_search", "keyword_search"]


def test_fuse_rrf_and_rerank(monkeypatch):
    monkeypatch.setattr(fmod, "rrf_fuse", lambda lists, k=60, weights=None: [
        {"chunk_id": "a", "title": "四君子汤", "text": "组成人参白术茯苓炙甘草", "rrf_score": 0.3},
        {"chunk_id": "b", "title": "归脾汤", "text": "益气补血", "rrf_score": 0.2},
    ])
    monkeypatch.setattr(fmod, "rerank", lambda q, docs, top_n: [{"index": 0, "score": 0.9}, {"index": 1, "score": 0.4}])
    monkeypatch.setattr(fmod, "get_settings", lambda: _Cfg())
    st = _state(vector_hits=[{"chunk_id": "a"}], keyword_hits=[{"chunk_id": "b"}])
    upd = fmod.fuse(st)
    assert upd["evidence"][0]["chunk_id"] == "a"
    assert upd["evidence"][0]["score"] == 0.9
    assert upd["confidence"] == 0.9
    assert upd["low_confidence"] is False
    assert [e["step"] for e in upd["trace"]] == ["fuse", "rerank"]


def test_reflect_edge_triggers_once(monkeypatch):
    monkeypatch.setattr(fmod, "get_settings", lambda: _Cfg())
    # 不足 + 未反射 → reflect
    assert reflect_edge(_state(evidence=[], graph_facts=[], reflect_count=0)) == "reflect"
    # 已反射一轮 → safety
    assert reflect_edge(_state(evidence=[], graph_facts=[], reflect_count=1)) == "safety"
    # 置信度低但图谱支持 → safety（豁免）
    assert reflect_edge(_state(low_confidence=True, graph_facts=[{"relation": "组成"}], reflect_count=0)) == "safety"


class _Cfg:
    semantic_k = 20; keyword_k = 20; fuse_candidate = 25; final_evidence = 5
    rrf_k = 60; rerank_top_n = 5; evidence_min_score = 0.3
```

- [ ] **Step 2: 运行确认失败**

Run: `cd backend && .venv/Scripts/python -m pytest tests/test_retrieve_fuse.py -v`
Expected: FAIL（`ModuleNotFoundError: app.agent.nodes.route`）

- [ ] **Step 3: 实现**

`backend/app/agent/nodes/route.py`：

```python
"""意图→工具路由矩阵（合并方案 4.2 逐字）与条件边。"""

PLAN_MATRIX = {
    "relation": ["vector_search", "graph_search"],
    "concept": ["vector_search", "keyword_search"],
    "complex": ["vector_search", "keyword_search", "graph_search"],
    "chitchat": [],
}


def route(state) -> str:
    """understand 之后：chitchat 直接进 safety，其余进检索。"""
    return "safety" if state["intent"] == "chitchat" else "retrieve"
```

`backend/app/agent/nodes/retrieve.py`：

```python
"""检索节点：按 plan（意图路由）调用被选 Tool。图谱无实体则跳过。"""
from app.agent import tools as tool_module
from app.agent.state import AgentState
from app.agent.nodes.route import PLAN_MATRIX

TOOLS = {
    "vector_search": tool_module.vector_search,
    "keyword_search": tool_module.keyword_search,
    "graph_search": tool_module.graph_search,
}


def retrieve(state: AgentState) -> dict:
    plan = PLAN_MATRIX.get(state["intent"], [])
    vector_hits = TOOLS["vector_search"].invoke({"query": state["rewritten_query"], "top_k": 20}) \
        if "vector_search" in plan else []
    keyword_hits = TOOLS["keyword_search"].invoke({"query": state["rewritten_query"], "top_k": 20}) \
        if "keyword_search" in plan else []
    graph_facts = []
    if "graph_search" in plan and state.get("entity_names"):
        for name in state["entity_names"]:
            out = TOOLS["graph_search"].invoke({"entity": name, "hop": 1})
            graph_facts.extend(out.get("facts", []))

    trace_evt = {
        "step": "retrieve",
        "vector_n": len(vector_hits),
        "keyword_n": len(keyword_hits),
        "graph_n": len(graph_facts),
        "entity_n": len(state.get("entity_names", [])),
        "entities": state.get("entity_names", []),
    }
    return {
        "plan": plan,
        "vector_hits": vector_hits,
        "keyword_hits": keyword_hits,
        "graph_facts": graph_facts,
        "trace": [trace_evt],
    }
```

`backend/app/agent/nodes/fuse.py`：

```python
"""融合节点：向量+关键词 RRF，图谱独立汇合不参与；rerank 精排 + 置信度判定。"""
from app.agent.state import AgentState
from app.config import get_settings
from app.llm.rerank import rerank
from app.retrieval.rrf import rrf_fuse

REFLECT_MAX = 1


def fuse(state: AgentState) -> dict:
    s = get_settings()
    fused = rrf_fuse(
        [state["vector_hits"], state["keyword_hits"]], k=s.rrf_k)[:s.fuse_candidate]
    docs = [f"{c['title']}：{c['text']}" for c in fused]
    reranked = rerank(state["rewritten_query"], docs, top_n=s.rerank_top_n)
    evidence = [{**fused[r["index"]], "score": r["score"]} for r in reranked]
    confidence = max((e["score"] for e in evidence), default=0.0)
    low_confidence = bool(evidence) and evidence[0]["score"] < s.evidence_min_score

    trace = [
        {"step": "fuse", "candidate_n": len(fused), "method": "RRF"},
        {"step": "rerank", "evidence_n": len(evidence), "confidence": round(confidence, 4),
         "status": "证据充分，正常生成" if not low_confidence else "知识库未匹配"},
    ]
    return {"fused": fused, "evidence": evidence, "confidence": confidence,
            "low_confidence": low_confidence, "trace": trace}


def reflect_edge(state: AgentState) -> str:
    """fuse 之后：证据不足且未达上限且意图非闲聊 → reflect；否则 safety。"""
    if state["intent"] == "chitchat":
        return "safety"
    insufficient = (not state["evidence"] or state["low_confidence"]) and not state["graph_facts"]
    if insufficient and state["reflect_count"] < REFLECT_MAX:
        return "reflect"
    return "safety"
```

- [ ] **Step 4: 运行确认通过**

Run: `cd backend && .venv/Scripts/python -m pytest tests/test_retrieve_fuse.py -v`
Expected: PASS（7 passed）

- [ ] **Step 5: Commit**

```bash
git add backend/app/agent/nodes/route.py backend/app/agent/nodes/retrieve.py backend/app/agent/nodes/fuse.py backend/tests/test_retrieve_fuse.py
git commit -m "feat(agent): retrieve/fuse nodes with intent routing matrix"
```

---

### Task 5: 自反思节点 + workflow 图组装

**Files:**
- Create: `backend/app/agent/nodes/reflect.py`、`backend/app/agent/workflow.py`
- Test: `backend/tests/test_workflow.py`

**Interfaces:**
- Consumes: Task 1-4 的节点函数、`chat_completion`、prompt `query_rewrite_reflect.txt`
- Produces: `reflect(state) -> dict`（更新 `rewritten_query / reflect_count / trace`（reflect 事件）；检索结果与图谱不变，重查由 retrieve 节点回填）；`build_agent()` 返回**未编译的 `StateGraph`**；`get_agent()` 返回编译后的编译图（进程单例）。图结构见下。

- [ ] **Step 1: 写失败测试** `backend/tests/test_workflow.py`

```python
import app.agent.nodes.reflect as remod
from app.agent.nodes.reflect import reflect
from app.agent.workflow import build_agent, get_agent


def _state(**over):
    base = {
        "question": "四君子汤有什么禁忌？", "session_id": "s", "chat_history": [],
        "rewritten_query": "四君子汤有什么禁忌？", "entities": [], "entity_names": ["四君子汤"],
        "intent": "relation", "plan": [], "vector_hits": [], "keyword_hits": [],
        "graph_facts": [], "fused": [], "evidence": [], "confidence": 0.0,
        "low_confidence": True, "reflect_count": 0, "safety_flag": None, "safety_message": "",
        "prompt": "", "answer": "", "trace": [],
    }
    base.update(over)
    return base


def test_reflect_rewrites_query(monkeypatch):
    captured = {}
    monkeypatch.setattr(
        remod, "chat_completion",
        lambda system, user, temperature: captured.setdefault("user", user) and "四君子汤 禁忌 使用注意",
    )
    upd = reflect(_state())
    assert upd["rewritten_query"] == "四君子汤 禁忌 使用注意"
    assert upd["reflect_count"] == 1
    assert upd["trace"][-1]["step"] == "reflect"
    assert "四君子汤有什么禁忌" in captured["user"]


def test_build_agent_has_expected_nodes():
    g = build_agent()
    nodes = g.nodes
    for name in ["understand", "retrieve", "fuse", "reflect", "safety", "context"]:
        assert name in nodes


def test_workflow_routes_chitchat_around_retrieval(monkeypatch):
    # 用真实图 + 全节点 monkeypatch，验证 chitchat 跳过 retrieve 且得到兜底答案
    import app.agent.workflow as wmod
    monkeypatch.setattr(wmod, "understand", lambda state: {"intent": "chitchat",
        "rewritten_query": state["question"], "entity_names": [], "trace": [{"step": "understand"}]})
    monkeypatch.setattr(wmod, "safety", lambda state: {"safety_flag": "low_confidence",
        "safety_message": "知识库中未检索到可靠依据。", "answer": "知识库中未检索到可靠依据。"})
    monkeypatch.setattr(wmod, "context", lambda state: {"prompt": "EMPTY"})
    g = wmod.build_agent().compile()
    final = g.invoke(_state(intent="chitchat"))
    assert final["safety_flag"] == "low_confidence"
    # 验证 retrieve 从未被调用（wmod 没有 monkeypatch retrieve，但 chitchat 路由不经过它）
```

- [ ] **Step 2: 运行确认失败**

Run: `cd backend && .venv/Scripts/python -m pytest tests/test_workflow.py -v`
Expected: FAIL（`ModuleNotFoundError: app.agent.nodes.reflect` / `app.agent.workflow`）

- [ ] **Step 3: 实现**

`backend/app/agent/nodes/reflect.py`：

```python
"""自反思节点：证据不足时改写检索查询（合并方案 4.2 自反思，上限 1 轮）。"""
from pathlib import Path

from app.agent.state import AgentState
from app.config import get_settings
from app.llm.chat import chat_completion

PROMPTS_DIR = Path(__file__).resolve().parents[2] / "agent" / "prompts"


def reflect(state: AgentState) -> dict:
    s = get_settings()
    reason = "最终证据为空" if not state["evidence"] else \
        f"Top 相关度 {state['confidence']:.3f} 低于阈值 {s.evidence_min_score}"
    history_block = _history_block(state.get("chat_history") or [])
    prompt = (PROMPTS_DIR / "query_rewrite_reflect.txt").read_text(encoding="utf-8").format(
        reason=reason, question=state["question"],
        rewritten_query=state["rewritten_query"], history=history_block)
    try:
        new_query = chat_completion(system="你是中医药检索改写器。", user=prompt, temperature=0.2).strip()
    except RuntimeError:
        new_query = state["rewritten_query"]
    if not new_query:
        new_query = state["rewritten_query"]

    trace_evt = {"step": "reflect", "round": state["reflect_count"] + 1, "reason": reason,
                 "rewritten": new_query}
    return {"rewritten_query": new_query,
            "reflect_count": state["reflect_count"] + 1,
            "trace": [trace_evt]}


def _history_block(history: list) -> str:
    if not history:
        return "（无）"
    return "\n".join(f"【{'用户' if m['role'] == 'user' else '助手'}】{m['content']}" for m in history[-8:])
```

`backend/app/agent/content`（context 节点，本 Task 一并实现以避免 workflow 引用未定义符号）：

`backend/app/agent/nodes/context.py`：

```python
"""context 节点：组装最终生成 Prompt（文献 + 图谱），产出宿主流式生成所需输入。"""
from pathlib import Path

from app.agent.state import AgentState

PROMPTS_DIR = Path(__file__).resolve().parents[2] / "agent" / "prompts"
ANSWER_TEMPLATE = PROMPTS_DIR / "answer_cn_tcm.txt"


def context(state: AgentState) -> dict:
    graph_block = "\n".join(
        f"{f['source']} --{f['relation']}--> {f['target']}" for f in state["graph_facts"]) or "（无）"
    evidence_block = "\n\n".join(
        f"[{i + 1}] 《{e['doc_name']}》{e.get('chapter', '')}（序号 {e.get('page_no', '')}）\n{e['title']}：{e['text']}"
        for i, e in enumerate(state["evidence"])) or "（无）"
    template = ANSWER_TEMPLATE.read_text(encoding="utf-8")
    return {"prompt": template.format(graph_facts=graph_block, evidence=evidence_block,
                                     question=state["question"])}
```

`backend/app/agent/nodes/safety.py`（本 Task 一并实现，供 workflow 引用；测试在 Task 6）：

```python
"""安全兜底节点：急症词拦截 + 低置信度拒答 + 图谱豁免（方案 4.4）。"""
from app.agent.state import AgentState
from app.safety.emergency import detect_emergency

EMERGENCY_MESSAGE = (
    "您提到的情况可能属于急症，请立即就医或拨打 120，本系统不提供急诊建议，也不替代专业诊断。"
)
LOW_CONFIDENCE_MESSAGE = "知识库中未检索到可靠依据。请换个问题，或提供更具体的证候、方剂或中药名称。"


def safety(state: AgentState) -> dict:
    text = f"{state['question']} {' '.join(state.get('entity_names', []))}"
    if detect_emergency(text):
        return {"safety_flag": "emergency", "safety_message": EMERGENCY_MESSAGE}
    if state["intent"] == "chitchat":
        return {"safety_flag": "low_confidence", "safety_message": LOW_CONFIDENCE_MESSAGE,
                "answer": LOW_CONFIDENCE_MESSAGE}
    if (not state["evidence"] or state["low_confidence"]) and not state["graph_facts"]:
        return {"safety_flag": "low_confidence", "safety_message": LOW_CONFIDENCE_MESSAGE,
                "answer": LOW_CONFIDENCE_MESSAGE}
    return {"safety_flag": "ok", "safety_message": ""}
```

`backend/app/agent/workflow.py`：

```python
"""LangGraph StateGraph 组装：检索编排状态机（合并方案 4.2）。"""
from langgraph.graph import END, START, StateGraph

from app.agent.nodes.context import context
from app.agent.nodes.fuse import fuse, reflect_edge
from app.agent.nodes.reflect import reflect
from app.agent.nodes.retrieve import retrieve
from app.agent.nodes.route import route
from app.agent.nodes.safety import safety
from app.agent.nodes.understand import understand
from app.agent.state import AgentState


def build_agent() -> StateGraph:
    g = StateGraph(AgentState)
    g.add_node("understand", understand)
    g.add_node("retrieve", retrieve)
    g.add_node("fuse", fuse)
    g.add_node("reflect", reflect)
    g.add_node("safety", safety)
    g.add_node("context", context)

    g.add_edge(START, "understand")
    g.add_conditional_edges("understand", route, {"retrieve": "retrieve", "safety": "safety"})
    g.add_edge("retrieve", "fuse")
    g.add_conditional_edges("fuse", reflect_edge, {"reflect": "reflect", "safety": "safety"})
    g.add_edge("reflect", "retrieve")
    g.add_edge("safety", "context")
    g.add_edge("context", END)
    return g


_graph = None


def get_agent():
    """进程级编译单例（图无状态，可安全复用）。"""
    global _graph
    if _graph is None:
        _graph = build_agent().compile()
    return _graph
```

- [ ] **Step 4: 运行确认通过**

Run: `cd backend && .venv/Scripts/python -m pytest tests/test_workflow.py -v`
Expected: PASS（3 passed）

- [ ] **Step 5: Commit**

```bash
git add backend/app/agent/nodes/reflect.py backend/app/agent/nodes/context.py backend/app/agent/nodes/safety.py backend/app/agent/workflow.py backend/tests/test_workflow.py
git commit -m "feat(agent): reflect node, safety/context nodes, LangGraph workflow assembly"
```

---

### Task 6: 流式 LLM + SSE `/api/chat/stream` + 记忆

**Files:**
- Modify: `backend/app/llm/chat.py`（+ `chat_completion_stream`）
- Create: `backend/app/agent/memory.py`
- Modify: `backend/app/api/chat.py`（ask → `/api/chat/stream`）
- Remove: 旧 `ask` 路由（其测试改为 stream 测试）
- Test: `backend/tests/test_stream_llm.py`、`backend/tests/test_memory.py`、`backend/tests/test_chat_stream.py`（替换/重写 `test_chat_api.py`）

**Interfaces:**
- Consumes: `get_agent()`、`history_block`、`_endpoint()`、`get_settings`、safety 输出
- Produces: `chat_completion_stream(system, user, temperature=0.3) -> Iterator[str]`；`get_history(session_id) -> list[dict]`、`upsert_message(session_id, role, content) -> list[dict]`、`new_session() -> str`；`sse(event, data) -> str`（SSE 帧编码）；POST `/api/chat/stream`（StreamingResponse）。

- [ ] **Step 1: 写失败测试**

`backend/tests/test_stream_llm.py`：

```python
import json
import httpx
import pytest

import app.llm.chat as cmod
from app.llm.chat import chat_completion_stream


class _FakeResponse:
    def __init__(self, lines):
        self._lines = lines
    def raise_for_status(self):
        pass
    def iter_lines(self):
        return iter(self._lines)
    def __enter__(self):
        return self
    def __exit__(self, *a):
        return False


def test_stream_yields_deltas(monkeypatch):
    lines = [
        'data: {"choices": [{"delta": {"content": "四君子"}}]}',
        'data: {"choices": [{"delta": {"content": "汤"}}]}',
        "data: [DONE]",
    ]
    monkeypatch.setattr(cmod, "get_settings", lambda: _S())
    monkeypatch.setattr(httpx, "stream", lambda *a, **k: _FakeResponse(lines))
    out = "".join(chat_completion_stream(system="s", user="u"))
    assert out == "四君子汤"


def test_stream_skips_non_data_and_empty_delta(monkeypatch):
    lines = [
        "event: ping",
        'data: {"choices": [{"delta": {}}]}',
        'data: {"choices": [{"delta": {"content": "人参"}}]}',
        "data: [DONE]",
    ]
    monkeypatch.setattr(cmod, "get_settings", lambda: _S())
    monkeypatch.setattr(httpx, "stream", lambda *a, **k: _FakeResponse(lines))
    assert "".join(chat_completion_stream("s", "u")) == "人参"


class _S:
    llm_vendor = "deepseek"
    deepseek_api_key = "k"; deepseek_base_url = "http://x"; llm_model_main = "m"
    dashscope_api_key = ""; dashscope_base_url = "http://y"; llm_model_alt = "q"
```

`backend/tests/test_memory.py`：

```python
from app.agent.memory import get_history, new_session, upsert_message


def test_session_roundtrip():
    sid = new_session()
    upsert_message(sid, "user", "四君子汤组成")
    upsert_message(sid, "assistant", "人参白术茯苓炙甘草")
    h = get_history(sid)
    assert h[0]["role"] == "user"
    assert h[1]["content"] == "人参白术茯苓炙甘草"


def test_history_capped_at_8():
    sid = new_session()
    for i in range(12):
        upsert_message(sid, "user", f"q{i}")
    assert len(get_history(sid)) == 8
    assert get_history(sid)[-1]["content"] == "q11"


def test_unknown_session_returns_empty():
    assert get_history("no-such-session") == []
```

`backend/tests/test_chat_stream.py`（替换旧的 `test_chat_api.py`）：

```python
from unittest.mock import MagicMock

import app.api.chat as chatmod
from app.agent.memory import get_history, upsert_message


def _patch_agent(client, monkeypatch, *, safety="ok", answer=None, safety_message=""):
    """monkeypatch get_agent 返回一个假编译图：invoke/stream 返回统一 final state。"""
    final = {
        "question": "四君子汤由哪些中药组成？", "session_id": "", "chat_history": [],
        "rewritten_query": "四君子汤组成", "entities": [], "entity_names": ["四君子汤"],
        "intent": "relation", "plan": ["vector_search", "graph_search"],
        "vector_hits": [], "keyword_hits": [], "graph_facts": [
            {"source": "四君子汤", "relation": "组成", "target": "人参", "source_type": "方剂", "target_type": "中药"}],
        "fused": [], "evidence": [{"chunk_id": "a", "title": "四君子汤", "doc_name": "中药方剂学基础",
                                   "chapter": "第1节", "page_no": 1, "text": "组成", "score": 0.9}],
        "confidence": 0.9, "low_confidence": False, "reflect_count": 0,
        "safety_flag": safety, "safety_message": safety_message, "prompt": "P",
        "answer": answer or "", "trace": [
            {"step": "understand", "rewritten": "四君子汤组成"},
            {"step": "retrieve", "vector_n": 1, "graph_n": 1},
            {"step": "rerank", "evidence_n": 1, "confidence": 0.9, "status": "证据充分，正常生成"}],
    }
    fake_graph = MagicMock()
    fake_graph.stream.return_value = [  # (node_name, update_dict) 对，与 stream_mode="updates" 一致
        ("understand", {"rewritten_query": "四君子汤组成", "trace": [{"step": "understand"}]}),
        ("retrieve", {"vector_hits": [], "graph_facts": final["graph_facts"], "trace": [{"step": "retrieve", "vector_n": 0, "graph_n": 1}]}),
        ("fuse", {"evidence": final["evidence"], "confidence": 0.9,
                   "trace": [{"step": "fuse", "candidate_n": 1}, {"step": "rerank", "evidence_n": 1, "confidence": 0.9, "status": "证据充分，正常生成"}]}),
        ("safety", {"safety_flag": safety}),
        ("context", {"prompt": "P"}),
    ]
    monkeypatch.setattr(chatmod, "get_agent", lambda: fake_graph)
    monkeypatch.setattr(chatmod, "chat_completion_stream", lambda system, user, temperature=0.3: iter(["四君子汤由人参、白术、茯苓、炙甘草组成 [1]"]))
    return fake_graph


def test_stream_emits_expected_events(client, monkeypatch):
    fake = _patch_agent(client, monkeypatch)
    with client.stream("POST", "/api/chat/stream", json={"question": "四君子汤由哪些中药组成？"}) as resp:
        assert resp.status_code == 200
        raw = "".join(resp.iter_text())
    # 事件顺序：step...、token、references、safety、done
    assert "event: step" in raw
    assert "event: token" in raw
    assert "event: references" in raw
    assert "event: done" in raw
    assert "组成" in raw


def test_stream_low_confidence_emits_safety_and_fallback_text(client, monkeypatch):
    _patch_agent(client, monkeypatch, safety="low_confidence",
                 safety_message="知识库中未检索到可靠依据。", answer="知识库中未检索到可靠依据。")
    with client.stream("POST", "/api/chat/stream", json={"question": "今天天气"}) as resp:
        raw = "".join(resp.iter_text())
    assert '"type": "low_confidence"' in raw
    assert "知识库中未检索到可靠依据" in raw


def test_stream_empty_question_rejected(client):
    resp = client.post("/api/chat/stream", json={"question": ""})
    assert resp.status_code == 422
```

- [ ] **Step 2: 运行确认失败**

Run: `cd backend && .venv/Scripts/python -m pytest tests/test_stream_llm.py tests/test_memory.py tests/test_chat_stream.py -v`
Expected: FAIL（`ModuleNotFoundError` / route 404）

- [ ] **Step 3: 实现**

`backend/app/llm/chat.py`（追加流式函数；`_endpoint` 已存在）：

```python
import json


def chat_completion_stream(system: str, user: str, temperature: float = 0.3):
    """流式对话补全：逐 token 产出文本。返回生成器。"""
    base_url, api_key, model = _endpoint()
    with httpx.stream(
        "POST", f"{base_url}/chat/completions",
        headers={"Authorization": f"Bearer {api_key}"},
        json={
            "model": model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": temperature,
            "stream": True,
        },
        timeout=120,
    ) as resp:
        resp.raise_for_status()
        for line in resp.iter_lines():
            if not line or not line.startswith("data:"):
                continue
            payload = line[len("data:"):].strip()
            if payload == "[DONE]":
                break
            try:
                data = json.loads(payload)
            except (json.JSONDecodeError, ValueError):
                continue
            delta = data.get("choices", [{}])[0].get("delta", {}).get("content")
            if delta:
                yield delta
```

`backend/app/agent/memory.py`：

```python
"""多轮会话记忆：内存 dict（方案 REDIS_MODE=memory；Redis 为 P1）。"""
import uuid

_sessions: dict[str, list[dict]] = {}
_HISTORY_CAP = 8


def new_session() -> str:
    sid = uuid.uuid4().hex
    _sessions[sid] = []
    return sid


def get_history(session_id: str) -> list[dict]:
    return list(_sessions.get(session_id, []))


def upsert_message(session_id: str, role: str, content: str) -> list[dict]:
    msgs = _sessions.setdefault(session_id, [])
    msgs.append({"role": role, "content": content})
    if len(msgs) > _HISTORY_CAP * 2:
        _sessions[session_id] = msgs[-_HISTORY_CAP * 2:]
    return list(_sessions[session_id])
```

`backend/app/api/chat.py`（重写；删除 ask）：

```python
"""SSE 流式问答接口（合并方案 4.3 事件协议）。"""
import json

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.agent.memory import get_history, new_session, upsert_message
from app.agent.workflow import get_agent
from app.llm.chat import chat_completion_stream

router = APIRouter()


class StreamBody(BaseModel):
    question: str = Field(min_length=1, max_length=500)
    session_id: str | None = Field(default=None, max_length=64)


def sse(event: str, data: dict | str) -> str:
    payload = data if isinstance(data, str) else json.dumps(data, ensure_ascii=False)
    return f"event: {event}\ndata: {payload}\n\n"


def _initial_state(body: StreamBody, session_id: str) -> dict:
    return {
        "question": body.question, "session_id": session_id,
        "chat_history": get_history(session_id), "rewritten_query": body.question,
        "entities": [], "entity_names": [], "intent": "", "plan": [],
        "vector_hits": [], "keyword_hits": [], "graph_facts": [], "fused": [],
        "evidence": [], "confidence": 0.0, "low_confidence": False, "reflect_count": 0,
        "safety_flag": None, "safety_message": "", "prompt": "", "answer": "",
        "trace": [],
    }


@router.post("/chat/stream")
def chat_stream(body: StreamBody) -> StreamingResponse:
    session_id = body.session_id or new_session()
    graph = get_agent()
    initial = _initial_state(body, session_id)

    def gen():
        final = dict(initial)
        try:
            for node_name, update in graph.stream(initial, stream_mode="updates"):
                for key, val in update.items():
                    if key == "trace":
                        final["trace"] = final.get("trace", []) + val
                    else:
                        final[key] = val
                if "trace" in update:
                    for ev in update["trace"]:
                        yield sse("step", ev)
        except RuntimeError as e:
            yield sse("error", {"detail": str(e)})
            return

        # 生成阶段
        if final["safety_flag"] == "emergency":
            yield sse("safety", {"type": "emergency", "message": final["safety_message"]})
            collected = []
            for chunk in chat_completion_stream(system="你是中医药知识助手。", user=final["prompt"], temperature=0.3):
                collected.append(chunk)
                yield sse("token", {"text": chunk})
            final["answer"] = "".join(collected)
        elif final["safety_flag"] == "low_confidence":
            yield sse("safety", {"type": "low_confidence", "message": final["safety_message"]})
            yield sse("token", {"text": final["answer"]})
        else:
            collected = []
            for chunk in chat_completion_stream(system="你是中医药知识助手「本草智问」。", user=final["prompt"], temperature=0.3):
                collected.append(chunk)
                yield sse("token", {"text": chunk})
            final["answer"] = "".join(collected)

        refs = [
            {"chunk_id": c["chunk_id"], "title": c["title"], "doc_name": c["doc_name"],
             "chapter": c["chapter"], "page_no": c["page_no"], "score": c["score"]}
            for c in final["evidence"]
        ]
        yield sse("references", {"docs": refs, "graph_facts": final["graph_facts"]})
        yield sse("done", {"message_id": session_id, "metrics": {
            "vector_n": len(final.get("vector_hits", [])),
            "graph_n": len(final.get("graph_facts", [])),
            "evidence_n": len(final["evidence"]),
            "reflect_count": final.get("reflect_count", 0),
        }})

        upsert_message(session_id, "user", body.question)
        if final["answer"]:
            upsert_message(session_id, "assistant", final["answer"])

    return StreamingResponse(gen(), media_type="text/event-stream")
```

- [ ] **Step 4: 运行确认通过**

Run: `cd backend && .venv/Scripts/python -m pytest tests/test_stream_llm.py tests/test_memory.py tests/test_chat_stream.py -v`
Expected: PASS（2 + 3 + 3 = 8 passed）

- [ ] **Step 5: Commit**

```bash
git add backend/app/llm/chat.py backend/app/agent/memory.py backend/app/api/chat.py backend/tests/test_stream_llm.py backend/tests/test_memory.py backend/tests/test_chat_stream.py
git rm backend/tests/test_chat_api.py
git commit -m "feat(api): SSE /api/chat/stream with streaming LLM and in-memory sessions"
```

---

### Task 7: 图级集成测试 + 安全节点测试（demo case 闭环）

**Files:**
- Test: `backend/tests/test_agent_graph.py`（新建，图级集成；覆盖"首轮不足→反思→补查成功"democase）

**Interfaces:**
- Consumes: `get_agent()`（完整图）、`build_agent()`

- [ ] **Step 1: 写失败测试**（其实是补行为样例，图已能编译；先写保证行为）
- 实际本 Task 无新实现——纯粹补图级集成测试与安全节点单测。测试：

```python
import app.agent.workflow as wmod
from app.agent.workflow import get_agent

# 复用上一 Task 的 _state 工厂


def test_safety_emergency_flag():
    import app.agent.nodes.safety as smod
    from app.agent.nodes.safety import safety
    st = _state(question="我胸痛得厉害", entity_names=[], intent="complex")
    upd = safety(st)
    assert upd["safety_flag"] == "emergency"
    assert "120" in upd["safety_message"]


def test_safety_low_confidence_when_no_evidence_and_no_graph():
    import app.agent.nodes.safety as smod
    from app.agent.nodes.safety import safety
    st = _state(question="今天天气", intent="complex", evidence=[], graph_facts=[], low_confidence=True)
    upd = safety(st)
    assert upd["safety_flag"] == "low_confidence"
    assert upd["answer"] == smod.LOW_CONFIDENCE_MESSAGE


def test_full_graph_reflect_then_recover(monkeypatch):
    # demo case：首轮检索不足 → reflect 改写 → 第二轮补查成功 → ok
    import app.agent.workflow as wmod
    # 使首轮 fuse 判定 low_confidence，第二轮正常
    rounds = {"n": 0}
    monkeypatch.setattr(wmod, "fuse", lambda state: _round_fuse(state, rounds))
    monkeypatch.setattr(wmod, "understand", lambda state: {"intent": "relation",
        "entity_names": ["四君子汤"], "rewritten_query": "四君子汤 禁忌", "trace": [{"step": "understand"}]})
    monkeypatch.setattr(wmod, "retrieve", lambda state: {"vector_hits": [],
        "graph_facts": [{"source": "四君子汤", "relation": "禁忌", "target": "对方剂成分过敏者禁用"}],
        "trace": [{"step": "retrieve"}]})
    monkeypatch.setattr(wmod, "reflect", lambda state: {"reflect_count": state["reflect_count"] + 1,
        "rewritten_query": "四君子汤 使用注意", "trace": [{"step": "reflect"}]})
    monkeypatch.setattr(wmod, "context", lambda state: {"prompt": "P"})

    g = wmod.build_agent().compile()
    final = g.invoke(_state(question="四君子汤有什么禁忌？"))
    assert final["reflect_count"] == 1
    assert final["safety_flag"] == "ok"          # 图谱补充后放行


def _round_fuse(state, rounds):
    rounds["n"] += 1
    if rounds["n"] == 1:
        upd = {"evidence": [], "confidence": 0.0, "low_confidence": True,
               "trace": [{"step": "rerank", "status": "知识库未匹配"}]}
    else:
        upd = {"evidence": [{"chunk_id": "x", "score": 0.8}], "confidence": 0.8, "low_confidence": False,
               "trace": [{"step": "rerank", "status": "证据充分，正常生成"}]}
    return {**state, **upd}
```

- [ ] **Step 2: 运行确认失败 / 通过**

Run: `cd backend && .venv/Scripts/python -m pytest tests/test_agent_graph.py -v`
Expected: 若节点实现正确应 PASS（4 passed）；若报错按 TDD 修正节点实现（不改测试语义）。

- [ ] **Step 3: 运行全量**

Run: `cd backend && .venv/Scripts/python -m pytest -v`
Expected: 全绿（阶段 2 的 37 + 本阶段新增 ~27 ≈ 64 passed）。注意 `test_chat_api.py` 已被 `test_chat_stream.py` 替换，旧文件已 `git rm`。

- [ ] **Step 4: Commit**

```bash
git add backend/tests/test_agent_graph.py
git commit -m "test(agent): graph-level reflect-then-recover demo case and safety node tests"
```

---

### Task 8: 前端 SSE 打字机 + 空态卡片 + 弹窗逐步点亮

**Files:**
- Modify: `web/src/types/chat.ts`、`web/src/api/chat.ts`、`web/src/views/qa/Chat.vue`、`web/src/views/qa/components/TraceDialog.vue`
- Test: 构建门禁（`npm run build` + `npm run type-check`）

**Interfaces:**
- Consumes: 后端 `/api/chat/stream` 事件（step/token/references/safety/done）
- Produces: `streamChat(question, handlers, sessionId?)`（fetch ReadableStream SSE 解析）；TraceDialog props 扩展：`trace: Trace` → `steps: StepEvent[]`、`activeStep: number`（当前点亮步）、`entities`；徽章逻辑不变（`status`）；弹窗过程条 5 步（图标 + 当前态橙色，规落点 M-10）。

- [ ] **Step 1: 改类型与 API**

`web/src/types/chat.ts`（整体替换）：

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

export interface StepEvent {
  step: string            // understand | retrieve | reflect | fuse | rerank
  raw?: string
  rewritten?: string
  entities?: string[]
  intent?: string
  vector_n?: number
  keyword_n?: number
  graph_n?: number
  entity_n?: number
  candidate_n?: number
  method?: string
  evidence_n?: number
  confidence?: number
  status?: string
  round?: number
  reason?: string
}

export interface StreamHandlers {
  onStep: (ev: StepEvent) => void
  onToken: (text: string) => void
  onReferences: (refs: Reference[], graphFacts: GraphFact[]) => void
  onSafety: (type: string, message: string) => void
  onDone: (metrics: Record<string, number>) => void
}
```

`web/src/api/chat.ts`（整体替换）：

```ts
/** SSE 流式问答（fetch ReadableStream 解析，EventSource 不支持 POST） */
import type { StreamHandlers } from '../types/chat'

export async function streamChat(
  question: string,
  handlers: StreamHandlers,
  sessionId?: string,
): Promise<void> {
  const resp = await fetch('/api/chat/stream', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ question, session_id: sessionId }),
  })
  if (!resp.ok || !resp.body) {
    const detail = await resp.json().catch(() => ({ detail: `HTTP ${resp.status}` }))
    throw new Error(detail.detail ?? `请求失败（${resp.status}）`)
  }
  const reader = resp.body.getReader()
  const decoder = new TextDecoder('utf-8')
  let buf = ''
  while (true) {
    const { done, value } = await reader.read()
    if (done) break
    buf += decoder.decode(value, { stream: true })
    const frames = buf.split('\n\n')
    buf = frames.pop() ?? ''
    for (const frame of frames) {
      const evt = parseSseFrame(frame)
      if (!evt) continue
      dispatch(evt, handlers)
    }
  }
}

function parseSseFrame(frame: string): { event: string; data: string } | null {
  let event = 'message'
  const dataLines: string[] = []
  for (const line of frame.split('\n')) {
    if (line.startsWith('event:')) event = line.slice(6).trim()
    else if (line.startsWith('data:')) dataLines.push(line.slice(5).trim())
  }
  if (!dataLines.length) return null
  return { event, data: dataLines.join('\n') }
}

function dispatch(evt: { event: string; data: string }, h: StreamHandlers) {
  const data = JSON.parse(evt.data || 'null')
  switch (evt.event) {
    case 'step': h.onStep(data); break
    case 'token': h.onToken(data.text ?? ''); break
    case 'references': h.onReferences(data.docs ?? [], data.graph_facts ?? []); break
    case 'safety': h.onSafety(data.type, data.message ?? ''); break
    case 'done': h.onDone(data.metrics ?? {}); break
    default: break
  }
}
```

- [ ] **Step 2: Chat.vue 改造**（空态 5 卡片 + SSE 打字机 + 自动开弹窗）
- 参考规格 P0-2 空态文案与 P0-3 回答态。核心 script 如下（完整见现有 Chat.vue 结构重写；关键状态）：

```ts
import { nextTick, ref } from 'vue'
import { streamChat } from '../../api/chat'
import type { GraphFact, Reference, StepEvent } from '../../types/chat'

interface QA {
  question: string
  answer: string
  references: Reference[]
  graphFacts: GraphFact[]
  safety: { type: string; message: string } | null
  trace: StepEvent[]
}

const suggestions = [
  '四君子汤由哪些中药组成？',
  '脾气虚常见哪些症状和方剂？',
  '风寒束表与风热犯表有什么区别？',
  '酸枣仁汤的组成、功效和禁忌是什么？',
  '失眠在中医药知识图谱中关联哪些证候？',
]

const messages = ref<QA[]>([])
const input = ref('')
const loading = ref(false)
const listRef = ref<HTMLElement>()
const sessionId = crypto.randomUUID()
const traceVisible = ref(false)
const currentTrace = ref<StepEvent[]>([])

async function send(q?: string) {
  const question = (q ?? input.value).trim()
  if (!question || loading.value) return
  input.value = ''
  loading.value = true
  const item: QA = { question, answer: '', references: [], graphFacts: [], safety: null, trace: [] }
  messages.value.push(item)
  currentTrace.value = []
  traceVisible.value = true
  await nextTick()
  listRef.value?.scrollTo({ top: listRef.value.scrollHeight })

  try {
    await streamChat(question, {
      onStep: (ev) => { item.trace.push(ev); currentTrace.value = [...item.trace] },
      onToken: (text) => { item.answer += text; scrollToBottom() },
      onReferences: (refs, gfs) => { item.references = refs; item.graphFacts = gfs; scrollToBottom() },
      onSafety: (type, message) => { item.safety = { type, message } },
      onDone: () => {},
    }, sessionId)
  } catch (e) {
    item.answer = `请求失败：${(e as Error).message}`
  } finally {
    loading.value = false
    await nextTick(); scrollToBottom()
  }
}
```

模板新增（空态卡片、安全框、图谱事实区、溯源按钮、弹窗）；弹窗 props 改为 `:steps="currentTrace"`，TraceDialog 内部按 step 逐步点亮。

- [ ] **Step 3: TraceDialog.vue 改 props 为逐步驱动**
- props：`steps: StepEvent[]`（替换原 `trace: Trace`）；内部 computed `activeStep` = 据最后 step 映射到 1-5（understand→1、retrieve→2、fuse→3（含 reflect 提示）、rerank→4，done/生成→5）；数字卡从对应 StepEvent 字段读；徽章据 `rerank.status`；步骤条 5 图标+当前态橙色（`theme.colorWarning`）。样式沿用 token（已有）。空的 `trace` 从 StepEvent 读取而非旧 Trace 结构。

- [ ] **Step 4: 构建验证**

Run: `cd web && npm run type-check && npm run build`
Expected: 零报错。

- [ ] **Step 5: Commit**

```bash
git add web/src/types/chat.ts web/src/api/chat.ts web/src/views/qa/Chat.vue web/src/views/qa/components/TraceDialog.vue
git commit -m "feat(web): SSE typewriter, empty-state cards, step-driven trace dialog"
```

---

### Task 9: 端到端实测验收

**Files:**
- Create: `docs/superpowers/plans/stage3-verification.md`
- Test: 真实 API + 浏览器（真实 DeepSeek/SiliconFlow 调用）

**步骤：**
1. 启动后端 `uvicorn app.main:app`；`curl`/httpx 实测四类问题（relation / concept / complex / chitchat）+ 多轮指代（同 session_id 先问"四君子汤组成"再问"它有什么禁忌"验证改写）+ 急症问题（"我胸痛怎么办"验证 emergency safety 事件）。
2. `cd backend && .venv/Scripts/python -m pytest -v` 全量绿；`cd web && npm run type-check && npm run build` 零报错。
3. 前端 `npm run dev` + 浏览器：登录 → 空态 5 卡片 → 点「四君子汤由哪些中药组成？」→ 打字机 + 弹窗逐步点亮（understand→retrieve→rerank 数字卡）+ 证据折叠 + 安全框。拒答场景琥珀徽章。急症场景 safety 提示。
4. 记录真实数字与 demo case（首轮不足→反思改写→补查成功：选一个弱召回查询如"四君子汤组成成分"改写后命中），归档 stage3-verification.md（日期 2026-09-14）。
5. 清理后台进程；提交：

```bash
git add docs/superpowers/plans/stage3-verification.md
git commit -m "docs: stage 3 verification record"
```

浏览器视觉验收由控制器在复审后补做；实现者完成 API 侧实测 + 数字记录 + dev server 健康（200）+ 全量测试/build 门禁。

---

## 自审

- **Spec 覆盖**：4.1 架构（workflow 节点）、4.2 状态/路由矩阵/节点（state.py/route.py/retrieve.py）、4.2 自反思≤1（reflect.py/fuse.reflect_edge）、4.3 SSE（api/chat.py + 前端）、4.4 安全兜底（safety.py/emergency.py）、6.7 Prompt（understand/reflect/answer/safety）、阶段 3 验证（Task 9：不同类型问题 tool 组合、多轮指代、乱问兜底、demo case）全覆盖。SSE 逐步点亮（Task 8 前端 step-driven）。
- **占位符扫描**：无 TBD/TODO/占位实现；每步有真实代码与命令。Task 3 的 `PROMPT_PATH` 兼容语句已显式纠正为单一正确路径。
- **类型一致性**：`AgentState` 字段名在 state/understand/retrieve/fuse/reflect/safety/context/api 全链路一致（`entity_names/evidence/graph_facts/low_confidence/reflect_count/safety_flag/safety_message/prompt/answer/trace`）；`StepEvent` 字段与后端 trace 事件的键一致；前端 `streamChat` handlers 与后端 `sse(event, data)` 帧一致。
- **架构裁定记录**：Ruling S1（图只编排检索与安全，流式生成在宿主 API 层）；Ruling S2（内存会话 dict 替代 LangGraph checkpointer）。