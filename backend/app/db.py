"""业务库接入：SQLAlchemy 2 引擎 / Session / Base。

生产用 MySQL（config.sqlalchemy_url）；测试注入 sqlite:///:memory:。
"""
from contextlib import contextmanager

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.config import get_settings


class Base(DeclarativeBase):
    pass


def _make_engine(url: str):
    kwargs = {"echo": False}
    if url.startswith("sqlite"):
        kwargs["connect_args"] = {"check_same_thread": False}
        if url == "sqlite:///:memory:":
            # :memory: 库默认 SingletonThreadPool 按线程隔离连接，TestClient 在独立
            # 线程跑 app 会看到空库；StaticPool 让同一引擎的所有会话共用一条连接。
            kwargs["poolclass"] = StaticPool
    return create_engine(url, **kwargs)


def get_engine():
    """进程级引擎（按 sqlalchemy_url 创建一次）。"""
    global _engine
    if _engine is None:
        _engine = _make_engine(get_settings().sqlalchemy_url)
    return _engine


_engine = None


@contextmanager
def session_scope(engine=None):
    """事务作用域：正常提交，异常回滚。"""
    maker = sessionmaker(bind=engine or get_engine(), expire_on_commit=False)
    session: Session = maker()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


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


def init_db(engine=None) -> None:
    """建表（幂等）+ 演示账号 seed。应用启动时调用。"""
    from app.models import chat, document, feedback, inference_config, retrieval_log, user  # noqa: F401  确保模型注册到 Base

    eng = engine or get_engine()
    Base.metadata.create_all(eng)
    _seed_users(eng)