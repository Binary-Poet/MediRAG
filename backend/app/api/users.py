"""账户管理（P2）：列表/新建/删除（修改档案字段并入 PUT，简单实现）。"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.api.auth import _hash, require_admin
from app.db import session_scope
from app.models.user import ROLES, User

router = APIRouter()


class UserBody(BaseModel):
    username: str
    display_name: str = ""
    role: str = "知识用户"
    password: str = ""


@router.get("/users")
def list_users(_: User = Depends(require_admin)) -> dict:
    with session_scope() as s:
        items = [{"id": u.id, "username": u.username, "display_name": u.display_name,
                  "role": u.role} for u in s.query(User).order_by(User.id).all()]
    return {"items": items}


@router.post("/users")
def create_user(body: UserBody, _: User = Depends(require_admin)) -> dict:
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
def delete_user(user_id: int, u: User = Depends(require_admin)) -> dict:
    if user_id == u.id:
        raise HTTPException(status_code=403, detail="不能删除当前登录用户")
    with session_scope() as s:
        row = s.get(User, user_id)
        if row is None:
            raise HTTPException(status_code=404, detail="用户不存在")
        s.delete(row)
    return {"deleted": user_id}