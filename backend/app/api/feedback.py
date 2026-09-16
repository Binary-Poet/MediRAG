"""反馈 API：有用/无用（前端回答卡片底部按钮）。"""
from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.api.auth import current_user
from app.db import session_scope
from app.models.feedback import Feedback
from app.models.user import User

router = APIRouter()


class FeedbackBody(BaseModel):
    session_id: str
    useful: bool


@router.post("/feedback")
def submit_feedback(body: FeedbackBody, _: User = Depends(current_user)) -> dict:
    with session_scope() as s:
        s.add(Feedback(session_id=body.session_id, useful=body.useful))
    return {"ok": True}