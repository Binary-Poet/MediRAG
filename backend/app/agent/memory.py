"""多轮会话记忆：取自 chat_message 持久化表，供 understand / reflect 拼接上下文。

改造前是进程内 dict（重启即失，且与 DB 会话形成两套 id 空间）；改为读库后，
「界面上看到的历史」与「喂给 LLM 的历史」是同一份数据。
"""
from app.services.chat_session import recent_history

_HISTORY_CAP = 8


def get_history(session_id: str) -> list[dict]:
    """该会话最近 _HISTORY_CAP 条消息，形如 [{"role", "content"}, ...]。"""
    return recent_history(session_id, _HISTORY_CAP)
