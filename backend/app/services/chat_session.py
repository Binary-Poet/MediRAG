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


def delete_all_sessions(user_id: int, favorite_only: bool = False) -> int:
    """清空该用户的会话，返回删除的会话数。

    favorite_only=True 只清收藏（对应前端停在「已收藏」筛选页时的清空），
    未收藏的会话不动。

    只按 user_id 过滤：别人的会话一条都不能碰（消息表无外键，子表删除同样只能按
    自己的 session_id 集合来删，否则会误删他人消息）。
    """
    with session_scope() as s:
        cond = [ChatSession.user_id == user_id]
        if favorite_only:
            cond.append(ChatSession.favorite.is_(True))
        ids = list(s.execute(select(ChatSession.id).where(*cond)).scalars())
        if not ids:
            return 0
        s.query(ChatMessage).filter(ChatMessage.session_id.in_(ids)).delete(
            synchronize_session=False)
        s.query(ChatSession).filter(ChatSession.id.in_(ids)).delete(
            synchronize_session=False)
        return len(ids)


def append_message(session_id: str, role: str, content: str,
                   payload: dict | None = None) -> int:
    """追加一条消息并推进会话 updated_at；seq 取当前最大值 +1，返回该 seq。

    返回 seq 是为了让调用方能回传本轮定位（前端「撤回」需要精确删掉指定轮，
    而不是"删掉最后两条"——后者在撤回非末轮时会删错）。
    """
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
        return nxt


def withdraw_round(session_id: str, user_id: int, seq: int | None = None) -> dict | None:
    """撤回一轮问答：回到「该提问还没问」时的对话状态。

    语义是**回滚**而不是挖洞：撤掉该轮及其之后的所有轮次，该轮之前的轮次原样保留。
    只删中间一轮会留下「第1轮 → 第3轮」的断档——后续轮次本就建立在该轮上下文之上，
    单独抽掉它反而让历史自相矛盾。会话剩空（撤的就是首轮）时连会话一并删除，
    这正是「回到该提问之前」：会话本就是随首条提问创建的。

    seq 为该轮 user 消息的 seq；缺省撤回最后一轮（前端刚答完、尚未拿到 seq 时的兜底）。
    会话不存在或不属于该用户返回 None（调用方映射 404）；指定 seq 找不到对应轮同样返回 None。

    只删前端会让被撤回的问答继续留在服务端：重新打开会话会重新冒出来，而且会通过
    recent_history 进入后续提问的多轮上下文——所以撤必须是两端一致的动作。
    """
    with session_scope() as s:
        row = _owned(s, session_id, user_id)
        if row is None:
            return None
        rows = list(s.execute(
            select(ChatMessage).where(ChatMessage.session_id == session_id)
            .order_by(ChatMessage.seq.desc())
        ).scalars())
        if not rows:
            return {"deleted": 0, "session_deleted": False}
        if seq is None:
            # 末轮：回答在最后则一起删，只有提问（生成阶段失败）时只删提问
            targets = rows[:2] if rows[0].role == "assistant" else rows[:1]
        else:
            start = next((i for i, r in enumerate(rows) if r.seq == seq), None)
            if start is None or rows[start].role != "user":
                return None
            # rows 为 seq 倒序（新的在前），故「该提问及其之后」= 列表前 start+1 条
            targets = rows[:start + 1]
        removed = {r.id for r in targets}
        for r in targets:
            s.delete(r)
        keep = [r for r in rows if r.id not in removed]
        if not keep:
            s.delete(row)
            return {"deleted": len(targets), "session_deleted": True}
        first = min(keep, key=lambda r: r.seq)
        if first.role == "user":
            # 维持「标题 = 首条提问」这一不变式（回滚只删尾部，正常不会改变首条，
            # 留作防御：一旦别的路径删了首条，标题也不会指向已不存在的提问）
            row.title = first.content[:500]
        row.updated_at = datetime.utcnow()
        return {"deleted": len(targets), "session_deleted": False}


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
