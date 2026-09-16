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
    # u 来自 current_user 的独立 session，已 detach——必须在新 session 里重查后落库。
    with session_scope() as s:
        uu = s.get(User, u.id)
        uu.password_hash = _hash(u.username, body.new_password)
    return {"ok": True}