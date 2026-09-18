# 辨证问答页「问答会话」侧栏 + 会话持久化 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 补齐《前端还原规格.md》P0-2 规定的左侧「问答会话」列表（新对话 / 全部·已收藏筛选 / 历史会话项 / 收藏 / 更多操作），并为其建立后端会话持久化与列表 API，使历史会话跨进程重启保留、按用户隔离、点开可完整回放。

**Architecture:** 新增 `chat_session` / `chat_message` 两张 MySQL 表（SQLAlchemy 2），业务语义集中在 `app/services/chat_session.py`，API 层只做协议映射。`/api/chat/stream` 从「无鉴权 + 生成结束才写内存」改为「强制鉴权 + 请求开始即建会话并写 user 消息、生成结束写 assistant 消息（含 trace/references/graph_facts/safety 的 JSON payload）」。`app/agent/memory.py` 的 `get_history` 由进程内 dict 改为读消息表，签名不变，`understand` / `reflect` 节点零改动。前端新建 `SessionList.vue` 与 `stores/session.ts`，`Chat.vue` 由单栏改为「左 280px 会话列表 + 右弹性问答区」。

**Tech Stack:** Python 3.12、FastAPI、SQLAlchemy 2（`sqlalchemy.JSON`）、pytest、Vue 3 + TypeScript + Pinia + Element Plus。

**Spec:** `docs/superpowers/specs/2026-09-16-chat-session-list-design.md`

## Global Constraints

- **测试不得依赖真实网络 / MySQL / Neo4j / LLM**：数据库测试用 `sqlite:///:memory:` 注入 `dbmod._engine`；LLM 与图谱用 monkeypatch。
- **鉴权与归属**：`/api/chat/stream` 与四个会话接口一律挂 `Depends(current_user)`；会话不属于当前用户时返回 **404**（不是 403——403 会泄露「该 id 存在」）。
- **落库时序不可颠倒**：`建会话 → get_history → 写 user 消息 → 跑图`。若把写 user 消息提到 `get_history` 之前，当前问题会重复进入 `chat_history`，污染多轮上下文。
- **先落库再发 done**：前端收到 `done` 即刷新会话列表，反序会读到未写完的条数。
- **时间戳约定**：沿用仓库既有的 `datetime.utcnow()`（naive UTC）。序列化给前端时**必须补 `Z`**，否则 JS `Date.parse` 按本地时区解析，相对时间会偏 8 小时。
- **前端设计 token 唯一来源**：`web/src/styles/theme.ts`，组件内禁止写死色值。
- **文案以《前端还原规格.md》为准**，不得自造。
- MySQL 容器：`docker compose -f deploy/docker-compose.yml up -d mysql`（宿主端口 3307）。
- 前端无测试运行器，前端任务的验证手段是 `npm run type-check` + 浏览器实跑。

---

## 文件结构

| 文件 | 责任 |
|---|---|
| `backend/app/models/chat.py`（新建） | `ChatSession` / `ChatMessage` ORM |
| `backend/app/db.py`（修改） | `init_db()` 模型导入列表登记 `chat` |
| `backend/app/services/chat_session.py`（新建） | 建会话 / 列表 / 收藏 / 删除 / 追加消息 / 回放 / 最近历史 |
| `backend/app/agent/memory.py`（修改） | `get_history` 改为读消息表（签名不变） |
| `backend/app/api/chat.py`（修改） | 流式端点挂鉴权 + 落库；新增四个会话管理端点 |
| `backend/tests/test_chat_models.py`（新建） | 建表 + JSON payload 往返 |
| `backend/tests/test_chat_sessions_service.py`（新建） | service 层行为与归属隔离 |
| `backend/tests/test_chat_sessions_api.py`（新建） | 四个端点 + 越权 404 |
| `backend/tests/test_memory.py`（重写） | 4 个用例改走库 |
| `backend/tests/test_chat_stream.py`（修改） | 7 个用例补鉴权 |
| `backend/tests/test_retrieval_log.py`（修改） | 3 个用例补鉴权 + 真实会话 id |
| `web/src/types/chat.ts`（修改） | `SessionSummary` / `StoredMessage` / `SessionListResponse`；`onDone` 改为传整个 done 载荷 |
| `web/src/utils/time.ts`（新建） | 相对时间格式化 |
| `web/src/api/chat.ts`（修改） | 4 个会话接口 + `streamChat` 补鉴权头 |
| `web/src/stores/session.ts`（新建） | 会话列表状态 |
| `web/src/views/qa/components/SessionList.vue`（新建） | 规格 P0-2 的左侧列表 |
| `web/src/views/qa/Chat.vue`（修改） | 左右分栏 + 历史会话回放接线 |

---

### Task 1: 会话持久化模型与建表

**Files:**
- Create: `backend/app/models/chat.py`
- Modify: `backend/app/db.py`（`init_db` 的模型导入行）
- Test: `backend/tests/test_chat_models.py`

**Interfaces:**
- Consumes: `app.db.Base`、`app.db.session_scope`、`app.db._make_engine`、`app.db.init_db`
- Produces: `app.models.chat.ChatSession`（字段 `id: str` / `user_id: int` / `title: str` / `favorite: bool` / `created_at` / `updated_at`）、`app.models.chat.ChatMessage`（字段 `id: int` / `session_id: str` / `seq: int` / `role: str` / `content: str` / `payload: dict | None` / `created_at`）

- [ ] **Step 1: 写失败测试**

创建 `backend/tests/test_chat_models.py`：

```python
"""会话持久化模型：建表 + JSON payload 往返（MySQL 原生 JSON 与 sqlite 均须可用）。"""
import pytest

import app.db as dbmod
from app.db import session_scope
from app.models.chat import ChatMessage, ChatSession


@pytest.fixture(autouse=True)
def _db(monkeypatch):
    eng = dbmod._make_engine("sqlite:///:memory:")
    dbmod.init_db(eng)
    monkeypatch.setattr(dbmod, "_engine", eng)


def test_session_and_message_roundtrip():
    with session_scope() as s:
        s.add(ChatSession(id="s1", user_id=1, title="四君子汤由哪些中药组成？"))
        s.add(ChatMessage(session_id="s1", seq=1, role="user", content="四君子汤由哪些中药组成？"))
        s.add(ChatMessage(session_id="s1", seq=2, role="assistant", content="人参、白术、茯苓、炙甘草",
                          payload={"trace": [{"step": "understand"}], "references": [],
                                   "graph_facts": [{"source": "四君子汤", "relation": "组成",
                                                    "target": "人参"}],
                                   "safety": None}))
    with session_scope() as s:
        row = s.get(ChatSession, "s1")
        assert row.user_id == 1
        assert row.favorite is False
        msgs = s.query(ChatMessage).filter_by(session_id="s1").order_by(ChatMessage.seq).all()
    assert [m.role for m in msgs] == ["user", "assistant"]
    assert msgs[1].payload["graph_facts"][0]["target"] == "人参"
    assert msgs[0].payload is None
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd backend && .venv/Scripts/python -m pytest tests/test_chat_models.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.models.chat'`

- [ ] **Step 3: 写模型**

创建 `backend/app/models/chat.py`：

```python
"""会话持久化：chat_session / chat_message（问答会话列表与完整回放的数据源）。"""
from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class ChatSession(Base):
    __tablename__ = "chat_session"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, index=True)
    title: Mapped[str] = mapped_column(String(500))
    favorite: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class ChatMessage(Base):
    __tablename__ = "chat_message"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id: Mapped[str] = mapped_column(String(32), index=True)
    seq: Mapped[int] = mapped_column(Integer)
    role: Mapped[str] = mapped_column(String(16))
    content: Mapped[str] = mapped_column(Text)
    # 助手消息存 {trace, references, graph_facts, safety}，用户消息为 None
    payload: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
```

- [ ] **Step 4: 在 `init_db` 登记模型**

`backend/app/db.py` 第 73 行，把 `chat` 加进导入列表（否则 `create_all` 看不到这两张表）：

```python
    from app.models import chat, document, feedback, inference_config, retrieval_log, user  # noqa: F401  确保模型注册到 Base
```

- [ ] **Step 5: 跑测试确认通过**

Run: `cd backend && .venv/Scripts/python -m pytest tests/test_chat_models.py -v`
Expected: PASS（1 passed）

- [ ] **Step 6: 跑全量测试确认无回归**

Run: `cd backend && .venv/Scripts/python -m pytest`
Expected: 全绿

- [ ] **Step 7: 提交**

```bash
git add backend/app/models/chat.py backend/app/db.py backend/tests/test_chat_models.py
git commit -m "feat(db): 新增 chat_session / chat_message 会话持久化表"
```

---

### Task 2: 会话持久化服务层

**Files:**
- Create: `backend/app/services/chat_session.py`
- Test: `backend/tests/test_chat_sessions_service.py`

**Interfaces:**
- Consumes: `app.db.session_scope`、`app.models.chat.ChatSession` / `ChatMessage`
- Produces:
  - `create_session(user_id: int, title: str) -> str`
  - `owns(session_id: str, user_id: int) -> bool`
  - `list_sessions(user_id: int, favorite_only: bool = False) -> dict`（`{"sessions": [...], "total": int, "favorite_total": int}`，每项 `{"session_id","title","favorite","message_count","updated_at"}`）
  - `set_favorite(session_id: str, user_id: int, favorite: bool) -> bool`
  - `delete_session(session_id: str, user_id: int) -> bool`
  - `append_message(session_id: str, role: str, content: str, payload: dict | None = None) -> None`
  - `load_messages(session_id: str, user_id: int) -> list[dict] | None`
  - `recent_history(session_id: str, cap: int) -> list[dict]`

- [ ] **Step 1: 写失败测试**

创建 `backend/tests/test_chat_sessions_service.py`：

```python
"""会话持久化服务：列表统计、收藏过滤、归属隔离、回放 payload、最近历史上限。"""
from datetime import datetime

import pytest

import app.db as dbmod
from app.db import session_scope
from app.models.chat import ChatSession
from app.services import chat_session as cs


@pytest.fixture(autouse=True)
def _db(monkeypatch):
    eng = dbmod._make_engine("sqlite:///:memory:")
    dbmod.init_db(eng)
    monkeypatch.setattr(dbmod, "_engine", eng)


def test_list_orders_by_updated_desc_and_counts_messages():
    a = cs.create_session(1, "四君子汤由哪些中药组成？")
    b = cs.create_session(1, "脾气虚常见哪些症状？")
    # 显式设定时间：Windows 时钟粒度约 15ms，连续三次写入可能落在同一刻度上，
    # 靠 sleep 或真实时钟排序会让用例变成 flaky。这里直接验证 ORDER BY 语义。
    with session_scope() as s:
        s.get(ChatSession, b).updated_at = datetime(2026, 9, 15, 10, 0, 0)
        s.get(ChatSession, a).updated_at = datetime(2026, 9, 16, 10, 0, 0)
    cs.append_message(a, "user", "四君子汤由哪些中药组成？")
    cs.append_message(a, "assistant", "人参、白术、茯苓、炙甘草")
    r = cs.list_sessions(1)
    assert r["total"] == 2
    assert r["favorite_total"] == 0
    assert [x["session_id"] for x in r["sessions"]] == [a, b]
    assert r["sessions"][0]["message_count"] == 2
    assert r["sessions"][1]["message_count"] == 0


def test_favorite_toggle_and_filter():
    a = cs.create_session(1, "问一")
    cs.create_session(1, "问二")
    assert cs.set_favorite(a, 1, True) is True
    r = cs.list_sessions(1, favorite_only=True)
    assert r["total"] == 2          # 统计是全部会话数
    assert r["favorite_total"] == 1
    assert [x["session_id"] for x in r["sessions"]] == [a]
    assert cs.set_favorite(a, 1, False) is True
    assert cs.list_sessions(1, favorite_only=True)["sessions"] == []


def test_ownership_isolation():
    a = cs.create_session(1, "问一")
    assert cs.owns(a, 1) is True
    assert cs.owns(a, 2) is False
    assert cs.set_favorite(a, 2, True) is False
    assert cs.delete_session(a, 2) is False
    assert cs.load_messages(a, 2) is None
    assert cs.load_messages(a, 1) == []      # 归属正确但尚无消息
    assert cs.list_sessions(2)["total"] == 0


def test_delete_removes_messages_too():
    a = cs.create_session(1, "问一")
    cs.append_message(a, "user", "问一")
    assert cs.delete_session(a, 1) is True
    assert cs.list_sessions(1)["total"] == 0
    assert cs.load_messages(a, 1) is None    # 会话没了，消息也不该能读到


def test_append_bumps_updated_at():
    a = cs.create_session(1, "问一")
    with session_scope() as s:
        s.get(ChatSession, a).updated_at = datetime(2020, 1, 1)
    cs.append_message(a, "user", "问一")
    with session_scope() as s:
        assert s.get(ChatSession, a).updated_at.year > 2020


def test_recent_history_capped_and_chronological():
    a = cs.create_session(1, "问")
    for i in range(12):
        cs.append_message(a, "user", f"q{i}")
    h = cs.recent_history(a, 8)
    assert len(h) == 8
    assert h[0]["content"] == "q4"
    assert h[-1]["content"] == "q11"


def test_replay_payload_roundtrip_and_utc_suffix():
    a = cs.create_session(1, "问")
    cs.append_message(a, "user", "问")
    cs.append_message(a, "assistant", "答", payload={
        "trace": [{"step": "understand"}], "references": [],
        "graph_facts": [{"source": "四君子汤", "relation": "组成", "target": "人参"}],
        "safety": None})
    msgs = cs.load_messages(a, 1)
    assert [m["role"] for m in msgs] == ["user", "assistant"]
    assert msgs[0]["payload"] is None
    assert msgs[1]["payload"]["graph_facts"][0]["target"] == "人参"
    assert msgs[1]["payload"]["trace"] == [{"step": "understand"}]
    assert msgs[1]["created_at"].endswith("Z")   # naive UTC 必须带 Z，否则前端偏 8 小时
    assert msgs[1]["seq"] > msgs[0]["seq"]
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd backend && .venv/Scripts/python -m pytest tests/test_chat_sessions_service.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.services.chat_session'`

- [ ] **Step 3: 写服务**

创建 `backend/app/services/chat_session.py`：

```python
"""会话持久化服务：建会话 / 列表 / 收藏 / 删除 / 追加消息 / 完整回放 / 最近历史。

归属校验统一走 _owned()：不属于该用户的会话一律按「不存在」处理，由调用方映射 404。
"""
import uuid
from datetime import datetime

from sqlalchemy import func, select

from app.db import session_scope
from app.models.chat import ChatMessage, ChatSession


def _owned(s, session_id: str, user_id: int) -> ChatSession | None:
    row = s.get(ChatSession, session_id)
    return row if row is not None and row.user_id == user_id else None


def create_session(user_id: int, title: str) -> str:
    """建会话并返回 id；标题取首条提问，截 500 与列宽一致。"""
    sid = uuid.uuid4().hex
    with session_scope() as s:
        s.add(ChatSession(id=sid, user_id=user_id, title=title[:500]))
    return sid


def owns(session_id: str, user_id: int) -> bool:
    with session_scope() as s:
        return _owned(s, session_id, user_id) is not None


def list_sessions(user_id: int, favorite_only: bool = False) -> dict:
    """该用户会话（updated_at 倒序）+ 全部/收藏两项统计。"""
    with session_scope() as s:
        rows = list(s.execute(
            select(ChatSession).where(ChatSession.user_id == user_id)
            .order_by(ChatSession.updated_at.desc())
        ).scalars())
        counts = dict(s.execute(
            select(ChatMessage.session_id, func.count(ChatMessage.id))
            .where(ChatMessage.session_id.in_([r.id for r in rows] or [""]))
            .group_by(ChatMessage.session_id)
        ).all())
    return {
        "sessions": [
            {"session_id": r.id, "title": r.title, "favorite": bool(r.favorite),
             "message_count": int(counts.get(r.id, 0)),
             # naive UTC 补 Z：前端 Date.parse 否则按本地时区解析
             "updated_at": r.updated_at.isoformat() + "Z"}
            for r in rows if not favorite_only or r.favorite
        ],
        "total": len(rows),
        "favorite_total": sum(1 for r in rows if r.favorite),
    }


def set_favorite(session_id: str, user_id: int, favorite: bool) -> bool:
    with session_scope() as s:
        row = _owned(s, session_id, user_id)
        if row is None:
            return False
        row.favorite = favorite
    return True


def delete_session(session_id: str, user_id: int) -> bool:
    """删会话及其全部消息（两表无外键，显式删子表）。"""
    with session_scope() as s:
        row = _owned(s, session_id, user_id)
        if row is None:
            return False
        s.query(ChatMessage).filter(ChatMessage.session_id == session_id).delete()
        s.delete(row)
    return True


def append_message(session_id: str, role: str, content: str,
                   payload: dict | None = None) -> None:
    """追加一条消息并推进会话 updated_at；seq 取当前最大值 +1。"""
    with session_scope() as s:
        nxt = (s.execute(
            select(func.coalesce(func.max(ChatMessage.seq), 0))
            .where(ChatMessage.session_id == session_id)
        ).scalar_one()) + 1
        s.add(ChatMessage(session_id=session_id, seq=nxt, role=role,
                          content=content, payload=payload))
        row = s.get(ChatSession, session_id)
        if row is not None:
            row.updated_at = datetime.utcnow()


def load_messages(session_id: str, user_id: int) -> list[dict] | None:
    """完整回放数据（seq 升序）；不存在或不属于该用户返回 None。"""
    with session_scope() as s:
        if _owned(s, session_id, user_id) is None:
            return None
        rows = list(s.execute(
            select(ChatMessage).where(ChatMessage.session_id == session_id)
            .order_by(ChatMessage.seq)
        ).scalars())
    return [{"seq": r.seq, "role": r.role, "content": r.content, "payload": r.payload,
             "created_at": r.created_at.isoformat() + "Z"} for r in rows]


def recent_history(session_id: str, cap: int) -> list[dict]:
    """该会话最近 cap 条消息（时间正序），供 LLM 上下文拼接。"""
    with session_scope() as s:
        rows = list(s.execute(
            select(ChatMessage).where(ChatMessage.session_id == session_id)
            .order_by(ChatMessage.seq.desc()).limit(cap)
        ).scalars())
    return [{"role": r.role, "content": r.content} for r in reversed(rows)]
```

- [ ] **Step 4: 跑测试确认通过**

Run: `cd backend && .venv/Scripts/python -m pytest tests/test_chat_sessions_service.py -v`
Expected: PASS（7 passed）

- [ ] **Step 5: 跑全量测试确认无回归**

Run: `cd backend && .venv/Scripts/python -m pytest`
Expected: 全绿

- [ ] **Step 6: 提交**

```bash
git add backend/app/services/chat_session.py backend/tests/test_chat_sessions_service.py
git commit -m "feat(api): 会话持久化服务（建/列/收藏/删/追加/回放）"
```

---

### Task 3: `/chat/stream` 落库 + 鉴权 + 会话记忆改读库

> 这三件事必须同一个任务完成：`memory.py` 一旦删掉 `new_session` / `upsert_message`，未同步改造的 `chat.py` 会 import 失败，整棵树在任务之间会断。

**Files:**
- Modify: `backend/app/api/chat.py`
- Modify: `backend/app/agent/memory.py`
- Modify: `backend/tests/test_chat_stream.py`
- Modify: `backend/tests/test_retrieval_log.py`
- Test: `backend/tests/test_memory.py`（重写）

**Interfaces:**
- Consumes: Task 2 的 `create_session` / `owns` / `append_message` / `recent_history`；`app.api.auth.current_user`
- Produces: `app.agent.memory.get_history(session_id: str) -> list[dict]`（签名不变）

- [ ] **Step 1: 重写 `test_memory.py`（失败测试）**

整体替换 `backend/tests/test_memory.py`：

```python
"""多轮会话记忆读库（原进程内 dict 实现已由 chat_message 表取代）。

原 test_sessions_evict_oldest_beyond_max 随 MAX_SESSIONS 逐出逻辑一并删除：
会话数上界由「按用户列举」取代，隔离性改由 test_chat_sessions_service.py 的
test_ownership_isolation 覆盖。
"""
import pytest

import app.db as dbmod
from app.agent.memory import get_history
from app.services import chat_session as cs


@pytest.fixture(autouse=True)
def _db(monkeypatch):
    eng = dbmod._make_engine("sqlite:///:memory:")
    dbmod.init_db(eng)
    monkeypatch.setattr(dbmod, "_engine", eng)


def test_session_roundtrip():
    sid = cs.create_session(1, "四君子汤组成")
    cs.append_message(sid, "user", "四君子汤组成")
    cs.append_message(sid, "assistant", "人参白术茯苓炙甘草")
    h = get_history(sid)
    assert h[0]["role"] == "user"
    assert h[1]["content"] == "人参白术茯苓炙甘草"


def test_history_capped_at_8():
    sid = cs.create_session(1, "问")
    for i in range(12):
        cs.append_message(sid, "user", f"q{i}")
    assert len(get_history(sid)) == 8
    assert get_history(sid)[-1]["content"] == "q11"


def test_unknown_session_returns_empty():
    assert get_history("no-such-session") == []
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd backend && .venv/Scripts/python -m pytest tests/test_memory.py -v`
Expected: FAIL — `TypeError: recent_history() missing` 或 `AttributeError`（`memory.py` 仍用内存 dict，`get_history` 拿不到库里的数据）

- [ ] **Step 3: 改 `memory.py` 为读库**

整体替换 `backend/app/agent/memory.py`：

```python
"""多轮会话记忆：取自 chat_message 持久化表，供 understand / reflect 拼接上下文。

改造前是进程内 dict（重启即失，且与 DB 会话形成两套 id 空间）；改为读库后，
「界面上看到的历史」与「喂给 LLM 的历史」是同一份数据。
"""
from app.services.chat_session import recent_history

_HISTORY_CAP = 8


def get_history(session_id: str) -> list[dict]:
    """该会话最近 _HISTORY_CAP 条消息，形如 [{"role", "content"}, ...]。"""
    return recent_history(session_id, _HISTORY_CAP)
```

- [ ] **Step 4: 改 `chat.py` 的流式端点**

`backend/app/api/chat.py` 第 1-14 行（docstring + 全部 import）整体替换为：

```python
"""SSE 流式问答接口（合并方案 4.3 事件协议）。"""
import json

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.agent.memory import get_history
from app.agent.nodes.safety import LOW_CONFIDENCE_MESSAGE
from app.agent.workflow import get_agent
from app.api.auth import current_user
from app.db import session_scope
from app.llm.chat import chat_completion_stream
from app.models.retrieval_log import RetrievalLog
from app.models.user import User
from app.services import chat_session
from app.services.inference_config import defaults, load_inference_config
```

`_initial_state` 改为接收已取好的 history（不再自己去读，避免与写入顺序耦合）：

```python
def _initial_state(body: StreamBody, session_id: str, history: list[dict]) -> dict:
    try:
        cfg = load_inference_config()
    except Exception:
        cfg = defaults()  # DB 不可达时回落默认，主聊天端点不因日志/配置库故障 500
    return {
        "question": body.question, "session_id": session_id,
        "chat_history": history, "rewritten_query": body.question,
        # 以下字段与改造前完全一致，保持不变
        "entities": [], "entity_names": [], "intent": "", "plan": [],
        "vector_hits": [], "keyword_hits": [], "graph_facts": [], "fused": [],
        "evidence": [], "confidence": 0.0, "low_confidence": False, "reflect_count": 0,
        "safety_flag": None, "safety_message": "", "prompt": "", "answer": "",
        "trace": [],
        "inference": cfg,
    }
```

端点签名与前置落库改为：

```python
@router.post("/chat/stream")
def chat_stream(body: StreamBody, user: User = Depends(current_user)) -> StreamingResponse:
    # 归属校验：带上他人的 session_id 会被拒，否则可往别人的会话里灌消息
    if body.session_id and not chat_session.owns(body.session_id, user.id):
        raise HTTPException(status_code=404, detail="会话不存在")
    session_id = body.session_id or chat_session.create_session(user.id, body.question)
    # 顺序不可颠倒：先取历史再写当前提问，否则当前问题会重复进入 chat_history
    history = get_history(session_id)
    chat_session.append_message(session_id, "user", body.question)
    graph = get_agent()
    initial = _initial_state(body, session_id, history)
```

生成段的三条分支各赋值 `answer_text`（低置信分支此前不设 `final["answer"]`，导致兜底话术不入库、回放为空，这里一并修掉）：

```python
        try:
            if final["safety_flag"] == "emergency":
                yield sse("safety", {"type": "emergency", "message": final["safety_message"]})
                emg_system = "你是中医药知识助手。用户描述了可能的急症情况，请务必在回答开头用加粗文字明确提示立即就医或拨打 120，再提供知识性说明。"
                collected = []
                cfg = final.get("inference") or {}
                for chunk in chat_completion_stream(system=emg_system, user=final["prompt"],
                                                    temperature=cfg.get("answer_temp", 0.3),
                                                    model=cfg.get("model")):
                    collected.append(chunk)
                    yield sse("token", {"text": chunk})
                answer_text = "".join(collected)
            elif final["safety_flag"] == "low_confidence":
                # 低置信分支无 LLM 生成：只发 safety 事件，前端以框渲染兜底话术
                answer_text = final["safety_message"] or final["answer"] or LOW_CONFIDENCE_MESSAGE
                yield sse("safety", {"type": "low_confidence", "message": answer_text})
            else:
                collected = []
                cfg = final.get("inference") or {}
                for chunk in chat_completion_stream(system="你是中医药知识助手「本草智问」。", user=final["prompt"],
                                                    temperature=cfg.get("answer_temp", 0.3),
                                                    model=cfg.get("model")):
                    collected.append(chunk)
                    yield sse("token", {"text": chunk})
                answer_text = "".join(collected)
        except Exception as e:  # 生成阶段异常收口：LLM/网络错误 → 显式 error 事件
            yield sse("error", {"detail": f"生成阶段失败：{e}"})
            return

        final["answer"] = answer_text
```

收尾段（`refs` 之后）替换末尾的两次 `upsert_message`：

```python
        refs = [
            {"chunk_id": c["chunk_id"], "title": c["title"], "doc_name": c["doc_name"],
             "chapter": c["chapter"], "page_no": c["page_no"], "score": c["score"]}
            for c in final["evidence"]
        ]
        yield sse("references", {"docs": refs, "graph_facts": final["graph_facts"]})

        # 先落库再发 done：前端收到 done 即刷新会话列表，反序会读到未写完的条数
        chat_session.append_message(session_id, "assistant", answer_text, payload={
            "trace": final.get("trace", []),
            "references": refs,
            "graph_facts": final.get("graph_facts", []),
            "safety": ({"type": final["safety_flag"], "message": final.get("safety_message", "")}
                       if final.get("safety_flag") not in (None, "ok") else None),
        })

        _log_retrieval(session_id, final)

        yield sse("done", {"message_id": session_id, "metrics": {
            "vector_n": len(final.get("vector_hits", [])),
            "graph_n": len(final.get("graph_facts", [])),
            "evidence_n": len(final["evidence"]),
            "reflect_count": final.get("reflect_count", 0),
        }})
```

（`upsert_message` / `new_session` 两处调用整个删除，不要保留。）

- [ ] **Step 5: 给 `test_chat_stream.py` 补鉴权**

`_db` 夹具改为 `init_db`（需要 seed 出三个用户才能登录），并新增 `_auth` 助手。第 9-14 行替换为：

```python
@pytest.fixture(autouse=True)
def _db(monkeypatch):
    eng = dbmod._make_engine("sqlite:///:memory:")
    dbmod.init_db(eng)                      # 建表 + seed 三用户（登录取 Bearer 用）
    monkeypatch.setattr(dbmod, "_engine", eng)


def _auth(client) -> dict:
    tok = client.post("/api/auth/login",
                      json={"username": "admin", "password": "admin123"}).json()["token"]
    return {"Authorization": f"Bearer {tok}"}
```

然后 7 处请求全部带上 `headers=_auth(client)`（含第 97 行的空问题用例——依赖解析先于请求体校验，不加头会拿到 401 而不是期望的 422）：

```python
    with client.stream("POST", "/api/chat/stream",
                       json={"question": "四君子汤由哪些中药组成？"}, headers=_auth(client)) as resp:
```

```python
    resp = client.post("/api/chat/stream", json={"question": ""}, headers=_auth(client))
    assert resp.status_code == 422
```

并在文件末尾新增落库断言用例：

```python
def test_stream_persists_turn_and_claims_session(client, monkeypatch):
    """本轮问答落库：done 返回的 message_id 即会话 id，且消息可回放。"""
    import json as _json

    from app.db import session_scope
    from app.models.chat import ChatMessage, ChatSession
    from app.services import chat_session as cs

    _patch_agent(client, monkeypatch)
    with client.stream("POST", "/api/chat/stream",
                       json={"question": "四君子汤由哪些中药组成？"},
                       headers=_auth(client)) as resp:
        raw = "".join(resp.iter_text())
    done = [ln for ln in raw.splitlines() if ln.startswith("data:") and "message_id" in ln][0]
    sid = _json.loads(done[len("data:"):].strip())["message_id"]

    with session_scope() as s:
        assert s.get(ChatSession, sid).title == "四君子汤由哪些中药组成？"
        msgs = s.query(ChatMessage).filter_by(session_id=sid).order_by(ChatMessage.seq).all()
    assert [m.role for m in msgs] == ["user", "assistant"]
    assert msgs[0].payload is None
    assert msgs[1].payload["graph_facts"][0]["target"] == "人参"
    assert msgs[1].payload["safety"] is None
    assert cs.load_messages(sid, 1) is not None


def test_stream_rejects_foreign_session(client, monkeypatch):
    """带上不属于自己的 session_id → 404，不能往他人会话灌消息。"""
    from app.services import chat_session as cs

    _patch_agent(client, monkeypatch)
    foreign = cs.create_session(2, "user1 的会话")
    r = client.post("/api/chat/stream", json={"question": "问", "session_id": foreign},
                    headers=_auth(client))       # admin 的 token，id=1
    assert r.status_code == 404


def test_stream_requires_auth(client):
    assert client.post("/api/chat/stream", json={"question": "问"}).status_code == 401
```

- [ ] **Step 6: 给 `test_retrieval_log.py` 补鉴权与真实会话 id**

`_auth` 助手已存在于该文件第 19-23 行，直接复用。三个用例中的 `session_id` 字符串（`sess-1` / `sess-2` / `sess-3`）都不存在于库中，会命中 404，需改为用服务建出来的真实会话（admin 的 `user_id` 为 1，与 `_auth` 登录的账号一致）：

`test_chat_stream_writes_retrieval_log`（第 50-55 行附近）：

```python
def test_chat_stream_writes_retrieval_log(client, monkeypatch):
    from app.services import chat_session as cs
    headers = _auth(client)
    sid = cs.create_session(1, "四君子汤由哪些中药组成？")   # admin 的 id=1
    fake = { ... 保持原样 ... }
```

```python
    r = client.post("/api/chat/stream",
                    json={"question": "四君子汤由哪些中药组成？", "session_id": sid},
                    headers=headers)
    assert r.status_code == 200
    with session_scope() as s:
        log = s.execute(select(RetrievalLog)).scalar_one()
        assert log.session_id == sid
```

`test_fallback_marks_is_fallback`：

```python
    headers = _auth(client)
    sid = cs.create_session(1, "今天北京天气")
    ...
    r = client.post("/api/chat/stream", json={"question": "今天北京天气", "session_id": sid},
                    headers=headers)
    ...
        assert log.session_id == sid
```

`test_saved_config_reaches_llm_call`：

```python
    headers = _auth(client)
    sid = cs.create_session(1, "四君子汤组成")
    ...
    r = client.post("/api/chat/stream", json={"question": "四君子汤组成", "session_id": sid},
                    headers=headers)
```

（三处均在函数顶部补 `from app.services import chat_session as cs`，或统一提到文件头部 import 区。）

- [ ] **Step 7: 跑相关测试确认通过**

Run: `cd backend && .venv/Scripts/python -m pytest tests/test_memory.py tests/test_chat_stream.py tests/test_retrieval_log.py -v`
Expected: PASS

- [ ] **Step 8: 跑全量测试确认无回归**

Run: `cd backend && .venv/Scripts/python -m pytest`
Expected: 全绿。若 `tests/test_understand.py` 或 `tests/test_workflow.py` 因 `chat_history` 来源变化而失败，说明它们直接调了 `memory` 模块——按同样方式改为注入 sqlite 夹具，不要改回内存实现。

- [ ] **Step 9: 提交**

```bash
git add backend/app/api/chat.py backend/app/agent/memory.py backend/tests/test_memory.py backend/tests/test_chat_stream.py backend/tests/test_retrieval_log.py
git commit -m "feat(qa): 问答落库 + /chat/stream 鉴权 + 会话记忆改读库"
```

---

### Task 4: 会话管理四端点

**Files:**
- Modify: `backend/app/api/chat.py`（文件末尾追加）
- Test: `backend/tests/test_chat_sessions_api.py`

**Interfaces:**
- Consumes: Task 2 的 service 函数、`app.api.auth.current_user`
- Produces:
  - `GET /api/chat/sessions?favorite=<bool>` → `{"sessions": [...], "total": int, "favorite_total": int}`
  - `PATCH /api/chat/sessions/{sid}`，体 `{"favorite": bool}` → `{"session_id": str, "favorite": bool}`
  - `DELETE /api/chat/sessions/{sid}` → `{"ok": true}`
  - `GET /api/chat/sessions/{sid}/messages` → `{"session_id": str, "messages": [...]}`

- [ ] **Step 1: 写失败测试**

创建 `backend/tests/test_chat_sessions_api.py`：

```python
"""会话管理接口：列表统计 / 收藏过滤 / 删除 / 完整回放 / 越权一律 404。

id 假设：`_seed_users` 按 admin → user1 → tcm1 顺序插入，sqlite 自增即
admin=1、user1=2。因此 `_seed()` 把会话建在 user_id=1，而 `other` 夹具用
user1（id=2）验证越权。若将来调整 seed 顺序，这些用例需同步。
"""
import pytest

import app.db as dbmod
from app.services import chat_session as cs


@pytest.fixture(autouse=True)
def _db(monkeypatch):
    eng = dbmod._make_engine("sqlite:///:memory:")
    dbmod.init_db(eng)
    monkeypatch.setattr(dbmod, "_engine", eng)


@pytest.fixture
def admin(client) -> dict:
    tok = client.post("/api/auth/login",
                      json={"username": "admin", "password": "admin123"}).json()["token"]
    return {"Authorization": f"Bearer {tok}"}


@pytest.fixture
def other(client) -> dict:
    """user1 的头：越权用例（admin 的会话对 user1 不可见）。"""
    tok = client.post("/api/auth/login",
                      json={"username": "user1", "password": "admin123"}).json()["token"]
    return {"Authorization": f"Bearer {tok}"}


def _seed(sid: str = "s1") -> str:
    a = cs.create_session(1, "四君子汤由哪些中药组成？")
    cs.append_message(a, "user", "四君子汤由哪些中药组成？")
    cs.append_message(a, "assistant", "人参、白术、茯苓、炙甘草", payload={
        "trace": [{"step": "understand"}],
        "references": [{"chunk_id": "c1", "title": "四君子汤", "doc_name": "中药方剂学基础",
                        "chapter": "第1节", "page_no": 1, "score": 0.9}],
        "graph_facts": [{"source": "四君子汤", "relation": "组成", "target": "人参",
                         "source_type": "方剂", "target_type": "中药"}],
        "safety": None})
    return a


def test_list_returns_totals_and_counts(client, admin):
    a = _seed()
    cs.create_session(1, "脾气虚常见哪些症状和方剂？")
    r = client.get("/api/chat/sessions", headers=admin)
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 2
    assert body["favorite_total"] == 0
    item = next(x for x in body["sessions"] if x["session_id"] == a)
    assert item["message_count"] == 2
    assert item["favorite"] is False
    assert item["updated_at"].endswith("Z")


def test_list_requires_auth(client):
    assert client.get("/api/chat/sessions").status_code == 401


def test_favorite_toggle_then_filter(client, admin):
    a = _seed()
    r = client.patch(f"/api/chat/sessions/{a}", json={"favorite": True}, headers=admin)
    assert r.status_code == 200
    assert r.json() == {"session_id": a, "favorite": True}
    only = client.get("/api/chat/sessions?favorite=true", headers=admin).json()
    assert only["total"] == 1
    assert only["favorite_total"] == 1
    assert [x["session_id"] for x in only["sessions"]] == [a]
    # 取消后筛选为空
    client.patch(f"/api/chat/sessions/{a}", json={"favorite": False}, headers=admin)
    assert client.get("/api/chat/sessions?favorite=true", headers=admin).json()["sessions"] == []


def test_delete_then_404(client, admin):
    a = _seed()
    assert client.delete(f"/api/chat/sessions/{a}", headers=admin).status_code == 200
    assert client.get("/api/chat/sessions", headers=admin).json()["total"] == 0
    assert client.delete(f"/api/chat/sessions/{a}", headers=admin).status_code == 404


def test_messages_replay_full_payload(client, admin):
    a = _seed()
    r = client.get(f"/api/chat/sessions/{a}/messages", headers=admin)
    assert r.status_code == 200
    msgs = r.json()["messages"]
    assert [m["role"] for m in msgs] == ["user", "assistant"]
    assert msgs[0]["payload"] is None
    p = msgs[1]["payload"]
    assert p["graph_facts"][0]["target"] == "人参"
    assert p["references"][0]["chunk_id"] == "c1"
    assert p["trace"] == [{"step": "understand"}]


def test_cross_user_access_all_404(client, admin, other):
    a = _seed()
    assert client.patch(f"/api/chat/sessions/{a}", json={"favorite": True},
                        headers=other).status_code == 404
    assert client.delete(f"/api/chat/sessions/{a}", headers=other).status_code == 404
    assert client.get(f"/api/chat/sessions/{a}/messages", headers=other).status_code == 404
    assert client.get("/api/chat/sessions", headers=other).json()["total"] == 0
    # 未被越权操作影响
    assert client.get(f"/api/chat/sessions/{a}/messages", headers=admin).status_code == 200
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd backend && .venv/Scripts/python -m pytest tests/test_chat_sessions_api.py -v`
Expected: FAIL — 全部 404（路由不存在）

- [ ] **Step 3: 写端点**

追加到 `backend/app/api/chat.py` 末尾：

```python
class FavoriteBody(BaseModel):
    favorite: bool


@router.get("/chat/sessions")
def list_sessions(favorite: bool = False, u: User = Depends(current_user)) -> dict:
    """当前用户的会话列表（updated_at 倒序）+ 全部/收藏统计。"""
    return chat_session.list_sessions(u.id, favorite_only=favorite)


@router.patch("/chat/sessions/{sid}")
def patch_session(sid: str, body: FavoriteBody, u: User = Depends(current_user)) -> dict:
    if not chat_session.set_favorite(sid, u.id, body.favorite):
        raise HTTPException(status_code=404, detail="会话不存在")
    return {"session_id": sid, "favorite": body.favorite}


@router.delete("/chat/sessions/{sid}")
def remove_session(sid: str, u: User = Depends(current_user)) -> dict:
    if not chat_session.delete_session(sid, u.id):
        raise HTTPException(status_code=404, detail="会话不存在")
    return {"ok": True}


@router.get("/chat/sessions/{sid}/messages")
def session_messages(sid: str, u: User = Depends(current_user)) -> dict:
    """完整回放：消息按 seq 升序，助手消息带 trace/references/graph_facts/safety。"""
    msgs = chat_session.load_messages(sid, u.id)
    if msgs is None:
        raise HTTPException(status_code=404, detail="会话不存在")
    return {"session_id": sid, "messages": msgs}
```

- [ ] **Step 4: 跑测试确认通过**

Run: `cd backend && .venv/Scripts/python -m pytest tests/test_chat_sessions_api.py -v`
Expected: PASS（6 passed）

- [ ] **Step 5: 跑全量测试确认无回归**

Run: `cd backend && .venv/Scripts/python -m pytest`
Expected: 全绿

- [ ] **Step 6: 提交**

```bash
git add backend/app/api/chat.py backend/tests/test_chat_sessions_api.py
git commit -m "feat(api): 会话管理四端点（列表/收藏/删除/回放）"
```

---

### Task 5: 前端数据层（类型 + 相对时间 + API 封装 + store）

**Files:**
- Modify: `web/src/types/chat.ts`
- Create: `web/src/utils/time.ts`
- Modify: `web/src/api/chat.ts`
- Create: `web/src/stores/session.ts`

**Interfaces:**
- Produces:
  - `types/chat.ts`：`SessionSummary`、`StoredMessage`、`SessionListResponse`；`StreamHandlers.onDone` 改签名为 `(data: DonePayload) => void`
  - `utils/time.ts`：`relativeTime(iso: string): string`
  - `api/chat.ts`：`listSessions(favoriteOnly?: boolean)`、`setSessionFavorite(id, favorite)`、`deleteSession(id)`、`fetchSessionMessages(id)`
  - `stores/session.ts`：`useSessionStore`，state `{ sessions, total, favoriteTotal, favoriteOnly, activeId, loading }`，actions `{ refresh, toggleFavorite, remove, loadMessages }`

- [ ] **Step 1: 扩类型并改 `onDone` 签名**

`web/src/types/chat.ts` 末尾追加，并把 `onDone` 那行改掉：

```ts
export interface SessionSummary {
  session_id: string
  title: string
  favorite: boolean
  message_count: number
  updated_at: string   // ISO，末尾带 Z（UTC）
}

export interface StoredMessage {
  seq: number
  role: 'user' | 'assistant'
  content: string
  payload: {
    trace?: StepEvent[]
    references?: Reference[]
    graph_facts?: GraphFact[]
    safety?: { type: string; message: string } | null
  } | null
  created_at: string
}

export interface SessionListResponse {
  sessions: SessionSummary[]
  total: number
  favorite_total: number
}

/** done 事件载荷：message_id 即会话 id，前端据此认领本轮新建的会话 */
export interface DonePayload {
  message_id?: string
  metrics?: Record<string, number>
}
```

```ts
  onDone: (data: DonePayload) => void
```

- [ ] **Step 2: 写相对时间工具**

创建 `web/src/utils/time.ts`：

```ts
/** 相对时间（规格 P0-2 会话项元信息：`14小时前 · 2条`）。 */
export function relativeTime(iso: string): string {
  // 后端存 naive UTC 并补了 Z；按 UTC 解析，避免被当成本地时间而偏 8 小时
  const t = Date.parse(iso)
  if (Number.isNaN(t)) return ''
  const diff = Date.now() - t
  if (diff < 60_000) return '刚刚'
  if (diff < 3_600_000) return `${Math.floor(diff / 60_000)}分钟前`
  if (diff < 86_400_000) return `${Math.floor(diff / 3_600_000)}小时前`
  if (diff < 7 * 86_400_000) return `${Math.floor(diff / 86_400_000)}天前`
  const d = new Date(t)
  const p = (n: number) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}`
}
```

- [ ] **Step 3: 加 API 封装并给 streamChat 补鉴权**

`web/src/api/chat.ts` 头部 import 改为：

```ts
/** SSE 流式问答（fetch ReadableStream 解析，EventSource 不支持 POST） */
import { authHeaders } from './http'
import type {
  SessionListResponse, StoredMessage, StreamHandlers,
} from '../types/chat'
```

`streamChat` 的 fetch 头补 Bearer（`/api/chat/stream` 已挂 `current_user`）：

```ts
  const resp = await fetch('/api/chat/stream', {
    method: 'POST',
    headers: authHeaders({ 'Content-Type': 'application/json' }),
    body: JSON.stringify({ question, session_id: sessionId }),
  })
```

`dispatch` 的 done 分支改为透传整个载荷：

```ts
    case 'done': h.onDone(data); break
```

文件末尾追加四个封装与一个错误详情助手（`streamChat` 原有内联的错误解析也改用它）：

```ts
async function detail(resp: Response): Promise<string> {
  const body = await resp.json().catch(() => ({ detail: `HTTP ${resp.status}` }))
  return body.detail ?? `请求失败（${resp.status}）`
}

export async function listSessions(favoriteOnly = false): Promise<SessionListResponse> {
  const resp = await fetch(`/api/chat/sessions?favorite=${favoriteOnly}`, { headers: authHeaders() })
  if (!resp.ok) throw new Error(await detail(resp))
  return resp.json()
}

export async function setSessionFavorite(sessionId: string, favorite: boolean): Promise<void> {
  const resp = await fetch(`/api/chat/sessions/${sessionId}`, {
    method: 'PATCH',
    headers: authHeaders({ 'Content-Type': 'application/json' }),
    body: JSON.stringify({ favorite }),
  })
  if (!resp.ok) throw new Error(await detail(resp))
}

export async function deleteSession(sessionId: string): Promise<void> {
  const resp = await fetch(`/api/chat/sessions/${sessionId}`, {
    method: 'DELETE', headers: authHeaders(),
  })
  if (!resp.ok) throw new Error(await detail(resp))
}

export async function fetchSessionMessages(sessionId: string): Promise<StoredMessage[]> {
  const resp = await fetch(`/api/chat/sessions/${sessionId}/messages`, { headers: authHeaders() })
  if (!resp.ok) throw new Error(await detail(resp))
  return (await resp.json()).messages
}
```

- [ ] **Step 4: 写 store**

创建 `web/src/stores/session.ts`：

```ts
// 问答会话列表状态：侧栏与问答区共享（新建要清空问答区、点选要灌入历史、
// 提问完成后要刷新列表项的标题/时间/条数）。父子传参会形成环形依赖，故用 store。
import { defineStore } from 'pinia'
import {
  deleteSession as apiDelete, fetchSessionMessages, listSessions, setSessionFavorite,
} from '../api/chat'
import type { SessionSummary, StoredMessage } from '../types/chat'

export const useSessionStore = defineStore('session', {
  state: () => ({
    sessions: [] as SessionSummary[],
    total: 0,
    favoriteTotal: 0,
    favoriteOnly: false,
    activeId: '',
    loading: false,
  }),
  actions: {
    async refresh() {
      this.loading = true
      try {
        const r = await listSessions(this.favoriteOnly)
        this.sessions = r.sessions
        this.total = r.total
        this.favoriteTotal = r.favorite_total
      } finally {
        this.loading = false
      }
    },
    /** 收藏/取消：统计与「已收藏」筛选都在服务端，改完重新拉一次最省心 */
    async toggleFavorite(s: SessionSummary) {
      await setSessionFavorite(s.session_id, !s.favorite)
      await this.refresh()
    },
    /** 删除；不清 activeId——由调用方（Chat.vue）决定问答区是否复位 */
    async remove(id: string) {
      await apiDelete(id)
      await this.refresh()
    },
    loadMessages(id: string): Promise<StoredMessage[]> {
      return fetchSessionMessages(id)
    },
  },
})
```

- [ ] **Step 5: 类型检查**

Run: `cd web && npm run type-check`
Expected: 无错误。此时 `Chat.vue` 的 `onDone: () => {}` 仍兼容新签名（少参函数可赋值给多参签名），不应报错。

- [ ] **Step 6: 提交**

```bash
git add web/src/types/chat.ts web/src/utils/time.ts web/src/api/chat.ts web/src/stores/session.ts
git commit -m "feat(web): 会话数据层（类型/相对时间/API 封装/store）"
```

---

### Task 6: `SessionList.vue`

**Files:**
- Create: `web/src/views/qa/components/SessionList.vue`

**Interfaces:**
- Consumes: `useSessionStore`、`relativeTime`、`theme`
- Produces: 组件 `SessionList`，emits：`create: []`、`select: [id: string]`、`deleted: [id: string]`

- [ ] **Step 1: 写组件**

创建 `web/src/views/qa/components/SessionList.vue`：

```vue
<script setup lang="ts">
// 左侧「问答会话」列表（规格 P0-2）：区块标题+统计 / + 新对话 / 全部·已收藏筛选 / 会话项。
// 数据取自 session store；选中、新建、删除后的复位交由父组件处理（父组件负责加载消息）。
import { computed, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useSessionStore } from '../../../stores/session'
import { relativeTime } from '../../../utils/time'
import { theme } from '../../../styles/theme'
import type { SessionSummary } from '../../../types/chat'

const emit = defineEmits<{ create: []; select: [id: string]; deleted: [id: string] }>()
const store = useSessionStore()

const tabs = computed(() => [
  { key: false, label: `全部 ${store.total}` },
  { key: true, label: `已收藏 ${store.favoriteTotal}` },
])

async function switchTab(favoriteOnly: boolean) {
  store.favoriteOnly = favoriteOnly
  try {
    await store.refresh()
  } catch (e) {
    ElMessage.error((e as Error).message)
  }
}

async function toggleFavorite(s: SessionSummary) {
  try {
    await store.toggleFavorite(s)
  } catch (e) {
    ElMessage.error((e as Error).message)
  }
}

/** 删除：二次确认（不可恢复） */
async function remove(s: SessionSummary) {
  try {
    await ElMessageBox.confirm(`确定删除会话「${s.title}」？该操作不可恢复。`, '删除确认',
                               { type: 'warning', confirmButtonText: '删除', cancelButtonText: '取消' })
  } catch {
    return // 用户取消
  }
  try {
    await store.remove(s.session_id)
    emit('deleted', s.session_id)
  } catch (e) {
    ElMessage.error((e as Error).message)
  }
}

function onCommand(cmd: string, s: SessionSummary) {
  if (cmd === 'fav') return toggleFavorite(s)
  if (cmd === 'del') return remove(s)
  return undefined
}

onMounted(() => {
  store.refresh().catch(() => {})   // 列表拉取失败不阻断问答主链路
})
</script>

<template>
  <aside class="session-list">
    <div class="sl-head">
      <div class="sl-head-text">
        <div class="sl-title">问答会话</div>
        <div class="sl-stat">{{ store.total }} 个历史会话 · {{ store.favoriteTotal }} 个收藏</div>
      </div>
      <el-button type="primary" size="small" @click="emit('create')">+ 新对话</el-button>
    </div>

    <div class="sl-tabs">
      <button
        v-for="t in tabs"
        :key="String(t.key)"
        class="sl-tab"
        :class="{ on: store.favoriteOnly === t.key }"
        type="button"
        @click="switchTab(t.key)"
      >
        {{ t.label }}
      </button>
    </div>

    <div class="sl-items">
      <div
        v-for="s in store.sessions"
        :key="s.session_id"
        class="sl-item"
        :class="{ on: store.activeId === s.session_id }"
        @click="emit('select', s.session_id)"
      >
        <div class="sl-item-main">
          <div class="sl-item-title">{{ s.title }}</div>
          <div class="sl-item-meta">{{ relativeTime(s.updated_at) }} · {{ s.message_count }}条</div>
        </div>
        <button
          class="sl-star"
          :class="{ on: s.favorite }"
          type="button"
          :title="s.favorite ? '取消收藏' : '收藏'"
          @click.stop="toggleFavorite(s)"
        >
          {{ s.favorite ? '★' : '☆' }}
        </button>
        <el-dropdown trigger="click" @command="(c: string) => onCommand(c, s)">
          <button class="sl-more" type="button" title="更多操作" @click.stop>⋯</button>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item command="fav">{{ s.favorite ? '取消收藏' : '收藏' }}</el-dropdown-item>
              <el-dropdown-item command="del" divided>删除</el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
      </div>

      <div v-if="!store.sessions.length" class="sl-empty">
        {{ store.favoriteOnly ? '暂无收藏的会话' : '暂无历史会话' }}
      </div>
    </div>
  </aside>
</template>

<style scoped>
.session-list {
  width: 280px;
  flex: none;
  display: flex;
  flex-direction: column;
  background: v-bind(theme.cardBg);
  border: 1px solid v-bind(theme.borderColor);
  border-radius: v-bind(theme.borderRadius);
  overflow: hidden;
}

.sl-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 8px;
  padding: 14px 14px 10px;
}

.sl-title {
  font-size: 15px;
  font-weight: 600;
  color: v-bind(theme.textColorPrimary);
}

.sl-stat {
  font-size: 12px;
  color: v-bind(theme.textColorMuted);
  margin-top: 2px;
}

.sl-tabs {
  display: flex;
  gap: 6px;
  padding: 0 14px 10px;
}

.sl-tab {
  flex: 1;
  font-size: 13px;
  font-family: inherit;
  padding: 6px 0;
  border-radius: 6px;
  border: 1px solid v-bind(theme.borderColor);
  background: v-bind(theme.cardBg);
  color: v-bind(theme.textColorSecondary);
  cursor: pointer;
}

.sl-tab.on {
  border-color: v-bind(theme.colorPrimary);
  color: v-bind(theme.colorPrimary);
  background: v-bind(theme.hoverBg);
  font-weight: 600;
}

.sl-items {
  flex: 1;
  overflow-y: auto;
  padding: 0 10px 12px;
}

.sl-item {
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 10px;
  border-radius: 8px;
  border: 1px solid transparent;
  cursor: pointer;
  margin-bottom: 6px;
}

.sl-item:hover {
  background: v-bind(theme.hoverBg);
}

.sl-item.on {
  border-color: v-bind(theme.colorPrimary);
  background: v-bind(theme.hoverBg);
}

.sl-item-main {
  flex: 1;
  min-width: 0;
}

.sl-item-title {
  font-size: 13px;
  color: v-bind(theme.textColorBody);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.sl-item-meta {
  font-size: 12px;
  color: v-bind(theme.textColorMuted);
  margin-top: 3px;
}

.sl-star,
.sl-more {
  flex: none;
  border: none;
  background: transparent;
  cursor: pointer;
  font-family: inherit;
  font-size: 14px;
  line-height: 1;
  padding: 4px;
  color: v-bind(theme.textColorMuted);
}

.sl-star.on {
  color: v-bind(theme.colorWarning);
}

.sl-empty {
  padding: 24px 12px;
  text-align: center;
  font-size: 13px;
  color: v-bind(theme.textColorMuted);
}
</style>
```

- [ ] **Step 2: 类型检查**

Run: `cd web && npm run type-check`
Expected: 无错误

- [ ] **Step 3: 提交**

```bash
git add web/src/views/qa/components/SessionList.vue
git commit -m "feat(web): 问答会话侧栏 SessionList（规格 P0-2）"
```

---

### Task 7: `Chat.vue` 左右分栏 + 历史会话回放接线

**Files:**
- Modify: `web/src/views/qa/Chat.vue`

**Interfaces:**
- Consumes: `SessionList` 组件、`useSessionStore`、`StoredMessage`
- Produces: 无对外导出

- [ ] **Step 1: 改 script：去掉本地 sessionId，接入 store**

`web/src/views/qa/Chat.vue` 的 import 区（第 5-11 行）追加两行：

```ts
import SessionList from './components/SessionList.vue'
import { useSessionStore } from '../../stores/session'
```

删除第 39 行这行（会话 id 改由后端下发）：

```ts
const sessionId = (globalThis.crypto?.randomUUID?.() ?? `s-${Math.random().toString(36).slice(2)}`)
```

在 `const traceVisible = ref(false)` 之后追加：

```ts
const sessionStore = useSessionStore()

/** 新建对话：清空问答区并解绑当前会话（首个提问由后端建会话） */
function newSession() {
  messages.value = []
  sessionStore.activeId = ''
  currentTrace.value = []
}

/** 打开历史会话：把落库 payload 还原成现有 QA 结构，复用同一套卡片渲染 */
async function openSession(id: string) {
  if (loading.value) return
  try {
    const msgs = await sessionStore.loadMessages(id)
    const built: QA[] = []
    for (let i = 0; i < msgs.length; i += 1) {
      const m = msgs[i]
      if (m.role !== 'user') continue
      const a = msgs[i + 1]?.role === 'assistant' ? msgs[i + 1] : null
      built.push(reactive<QA>({
        question: m.content,
        answer: a?.content ?? '',
        references: a?.payload?.references ?? [],
        graphFacts: a?.payload?.graph_facts ?? [],
        safety: a?.payload?.safety ?? null,
        trace: a?.payload?.trace ?? [],
        thinkingExpanded: false,
      }))
    }
    messages.value = built
    sessionStore.activeId = id
    currentTrace.value = []
    await scrollToBottom()
  } catch (e) {
    ElMessage.error((e as Error).message)
  }
}

/** 删除的若是当前会话，问答区复位到空态 */
function onDeleted(id: string) {
  if (sessionStore.activeId === id) newSession()
}
```

- [ ] **Step 2: 改 `send()`：用 store 的 activeId，并从 done 认领会话 id**

第 68-99 行的调用改为：

```ts
    await streamChat(question, {
      onStep: (ev) => {
        item.trace.push(ev)
        currentTrace.value = [...item.trace]
      },
      onToken: (text) => {
        if (!item.answer && item.trace.length) {
          // 首个 token 到达：点亮第 5 步「生成回答」
          item.trace.push({ step: 'generate' })
          currentTrace.value = [...item.trace]
        }
        if (!item.answer && !item.thinkingInteracted) {
          // 首个 token：思考完成，自动折叠为「已深度思考」（用户已手动操作过则保留其展开态）
          item.thinkingExpanded = false
        }
        item.answer += text
        scrollToBottom()
      },
      onReferences: (refs, gfs) => {
        item.references = refs
        item.graphFacts = gfs
        scrollToBottom()
      },
      onSafety: (type, message) => {
        item.safety = { type, message }
      },
      onError: (detail) => {
        // 后端 error 事件：保留已流式内容，仅在尚无输出时给失败话术
        if (!item.answer) item.answer = `请求失败：${detail}`
      },
      onDone: (data) => {
        // 认领会话 id：新会话由后端在本轮创建，前端据此激活并刷新列表
        if (data.message_id) sessionStore.activeId = data.message_id
        sessionStore.refresh().catch(() => {})   // 列表刷新失败不影响本轮回答
      },
    }, sessionStore.activeId || undefined)
```

`sendFeedback` 里的 `sessionId`（第 119 行）改为 `sessionStore.activeId`：

```ts
      body: JSON.stringify({ session_id: sessionStore.activeId, useful }),
```

- [ ] **Step 3: 改 template：外面包一层左右分栏**

把根节点 `<div class="chat-page">` 替换为：

```vue
  <div class="chat-wrap">
    <SessionList @create="newSession" @select="openSession" @deleted="onDeleted" />

    <div class="chat-page">
      <!-- 原有内容：空态 / 消息列表 / 输入区 / 免责声明 / TraceDialog 原样保留 -->
    </div>
  </div>
```

（`.chat-page` 内部原有内容不动，仅调整闭合层级。）

- [ ] **Step 4: 改样式**

`.chat-page` 原有规则保持不动（已是 `height: 100%` 的 flex column）。在其前追加：

```css
.chat-wrap {
  display: flex;
  gap: 14px;
  height: 100%;
  align-items: stretch;
}

.chat-page {
  flex: 1;
  min-width: 0;
}
```

- [ ] **Step 5: 类型检查**

Run: `cd web && npm run type-check`
Expected: 无错误

- [ ] **Step 6: 构建验证**

Run: `cd web && npm run build`
Expected: 构建成功

- [ ] **Step 7: 提交**

```bash
git add web/src/views/qa/Chat.vue
git commit -m "feat(qa): 问答页左右分栏 + 历史会话回放接线"
```

---

### Task 8: 端到端实测验收

**Files:**
- Create: `docs/superpowers/plans/chat-session-list-verification.md`

**Interfaces:**
- Consumes: 前 7 个任务的全部产出
- Produces: 验收记录文档

- [ ] **Step 1: 起后端与中间件**

```bash
docker compose -f deploy/docker-compose.yml up -d mysql
```
```bash
cd backend && .venv/Scripts/python -m uvicorn app.main:app --port 8000 --reload --reload-dir app
```

- [ ] **Step 2: 起前端并登录**

Run: `cd web && npm run dev`，浏览器打开 `http://localhost:5173`，用 `admin / admin123` 登录，进入辨证问答页。

- [ ] **Step 3: 逐项核对规格 P0-2**

- [ ] 左栏宽约 280px，区块标题「问答会话」，统计形如「N 个历史会话 · M 个收藏」
- [ ] 「+ 新对话」为绿色填充按钮
- [ ] 筛选页签显示「全部 N」「已收藏 M」
- [ ] 会话项：标题截断、`相对时间 · N条`、右侧 ☆ 与 ⋯
- [ ] ⋯ 悬停/点击弹「收藏 / 删除」两项
- [ ] 右侧问答区（空态引导 + 常用问题卡片 + 输入区）与改造前一致

- [ ] **Step 4: 核对交互闭合**

- [ ] 点常用问题发问 → 回答流式输出 → 左栏出现该会话，标题为该提问，条数为 2
- [ ] 刷新页面 → 会话仍在（持久化生效）
- [ ] 点 ☆ → 变 ★，「已收藏 M」计数 +1；切到「已收藏」页签只见该会话；再点 ★ 取消
- [ ] 点历史会话 → 右侧还原出正文、图谱依据、证据来源、思考过程
- [ ] 在还原的会话里追问一句 → 回答体现上文（多轮上下文来自库，不是内存）
- [ ] 点 ⋯ → 删除 → 二次确认 → 该项消失；删当前会话后问答区回到空态
- [ ] 点「+ 新对话」→ 问答区清空，右栏不再高亮任何会话

- [ ] **Step 5: 核对鉴权**

浏览器 DevTools → Application → Local Storage 删掉 `medirag_token`，刷新后调用 `/api/chat/stream` 应为 401。

- [ ] **Step 6: 记录实测结果**

把实际观察到的数字与结论写进 `docs/superpowers/plans/chat-session-list-verification.md`（沿用 `docs/superpowers/plans/stage5-verification.md` 的体例：逐项 ✅/❌ + 证据）。**只写实跑观察到的结果，推测性结论不得写入。**

- [ ] **Step 7: 跑全量测试与类型检查收尾**

Run: `cd backend && .venv/Scripts/python -m pytest`
```bash
cd web && npm run type-check
```
Expected: 两者均通过

- [ ] **Step 8: 提交**

```bash
git add docs/superpowers/plans/chat-session-list-verification.md
git commit -m "docs(verification): 会话列表端到端实测验收记录"
```

---

## 自查记录

**规格覆盖**：设计文档第 2 节 → Task 1；第 3 节接口表 → Task 3（stream 落库与鉴权）+ Task 4（四个管理端点）；第 4 节 `memory.py` → Task 3；第 5 节前端结构 → Task 5/6/7；第 6 节交互闭合 → Task 7 + Task 8 Step 4；第 7 节测试策略 → 各任务内；第 8 节验收标准 → Task 8；第 9 节明确不做 → 无对应任务（符合预期）；第 10 节偏离（不实现 `POST /api/chat/session`）→ 全计划无该端点。

**类型一致性**：`session_id`（后端）/ `session_id`（前端 `SessionSummary`）一致；`favorite_total`→`favoriteTotal` 仅在 store 层转换一次；`message_count`→`message_count` 前端直接使用；`graph_facts`（后端）→ `graph_facts`（`StoredMessage.payload`）→ `graphFacts`（`QA`）转换点集中在 `openSession` 一处；`answer_text` 在 Task 3 生成段三个分支均赋值后使用，无未定义路径。

**已知风险**：Windows 时钟粒度约 15ms，列表排序用例已改为显式设定 `updated_at`，不依赖真实时钟；`sqlalchemy.JSON` 在 sqlite 上以 TEXT 落地，往返测试已覆盖；`user_id` 字面量依赖 seed 顺序（admin=1 / user1=2），已在 `test_chat_sessions_api.py` 文件头注明。

**未提交项**：本计划与设计文档均为本地文件，按用户要求不提交 git；各任务内的代码提交照常执行。
