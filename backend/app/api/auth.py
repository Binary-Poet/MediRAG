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
        _, uid, sig = token.split(":")
        uid_i = int(uid)
    except ValueError:
        return None
    with session_scope() as s:
        u = s.get(User, uid_i)
    # 签名分量必须校验，否则任意 `user:<id>:任意串` 都能冒充该用户。
    if u is None or sig != _hash(u.username, SESSION_SECRET)[:16]:
        return None
    return u


def current_user(cred: HTTPAuthorizationCredentials | None = Depends(_bearer)) -> User:
    if cred is None or (u := _user_from_token(cred.credentials)) is None:
        raise HTTPException(status_code=401, detail="未登录或登录已失效")
    return u


def require_admin(u: User = Depends(current_user)) -> User:
    """账户管理类接口的窄依赖：仅管理员可操作。"""
    if u.role != "管理员":
        raise HTTPException(status_code=403, detail="需要管理员权限")
    return u


class LoginBody(BaseModel):
    username: str
    password: str


def _user_dict(u: User) -> dict:
    return {"id": u.id, "username": u.username, "display_name": u.display_name,
            "role": u.role}


@router.post("/auth/login")
def login(body: LoginBody) -> dict:
    with session_scope() as s:
        u = s.query(User).filter(User.username == body.username).first()
        if u is None or u.password_hash != _hash(body.username, body.password):
            raise HTTPException(status_code=401, detail="用户名或密码错误")
        return {"token": _token(u), "user": _user_dict(u)}


# 自助注册只能拿到最低权限角色。角色**刻意不从请求体读取**：一旦可传 role，
# 任何人构造一条请求就能把自己注册成管理员。
SELF_REGISTER_ROLE = "知识用户"


class RegisterBody(BaseModel):
    username: str
    password: str
    display_name: str = ""


@router.post("/auth/register")
def register(body: RegisterBody) -> dict:
    """自助注册（登录页「立即注册」）：成功后直接返回 token，前端免二次登录。"""
    username = body.username.strip()
    if not 3 <= len(username) <= 20:
        raise HTTPException(status_code=422, detail="用户名需 3–20 个字符")
    if len(body.password) < 6:
        raise HTTPException(status_code=422, detail="密码至少 6 位")
    display_name = body.display_name.strip() or username
    if len(display_name) > 50:
        raise HTTPException(status_code=422, detail="姓名不超过 50 字")
    with session_scope() as s:
        if s.query(User).filter(User.username == username).first() is not None:
            raise HTTPException(status_code=409, detail="用户名已被占用")
        u = User(username=username, display_name=display_name,
                 role=SELF_REGISTER_ROLE, password_hash=_hash(username, body.password))
        s.add(u)
        s.flush()
        return {"token": _token(u), "user": _user_dict(u)}


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


class ProfileBody(BaseModel):
    display_name: str


@router.put("/auth/profile")
def update_profile(body: ProfileBody, u: User = Depends(current_user)) -> dict:
    name = body.display_name.strip()
    if not name:
        raise HTTPException(status_code=422, detail="姓名不能为空")
    if len(name) > 50:
        raise HTTPException(status_code=422, detail="姓名不超过 50 字")
    with session_scope() as s:
        uu = s.get(User, u.id)
        uu.display_name = name
    return {"id": u.id, "username": u.username, "display_name": name, "role": u.role}