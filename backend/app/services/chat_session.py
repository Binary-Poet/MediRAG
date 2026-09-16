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
