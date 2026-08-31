# -*- coding: utf-8 -*-
"""认证安全测试：token jti 与 logout 吊销、登录限流（持久化到 SQLite）。"""
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from jose import jwt as jose_jwt
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.config import settings
from app.core.database import Base, get_db
from app.core.rate_limit import LoginRateLimiter
from app.core.security import get_password_hash
from app.models.models import LoginFailure, User
from app.routes.auth import router as auth_router


@pytest.fixture()
def client(tmp_path):
    engine = create_engine(
        f"sqlite:///{tmp_path / 'auth.db'}",
        connect_args={"check_same_thread": False},
    )
    TestingSession = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    Base.metadata.create_all(bind=engine)

    test_app = FastAPI()
    test_app.include_router(auth_router)

    def override_db():
        db = TestingSession()
        try:
            yield db
        finally:
            db.close()

    test_app.dependency_overrides[get_db] = override_db

    with TestingSession() as db:
        db.add(User(username="alice", hashed_password=get_password_hash("correct-password"), role="user"))
        db.commit()

    with TestClient(test_app) as c:
        c.db_session_factory = TestingSession
        yield c


def _login(client, username="alice", password="correct-password"):
    return client.post("/login", json={"username": username, "password": password})


def test_login_token_contains_jti(client):
    resp = _login(client)
    assert resp.status_code == 200, resp.text
    payload = jose_jwt.decode(resp.json()["access_token"], settings.SECRET_KEY, algorithms=["HS256"])
    assert payload.get("jti")  # 吊销机制依赖 jti


def test_logout_revokes_token(client):
    token = _login(client).json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    assert client.get("/me", headers=headers).status_code == 200
    assert client.post("/logout", headers=headers).status_code == 200
    # 已吊销 token 再访问受保护接口 → 401
    assert client.get("/me", headers=headers).status_code == 401


def test_login_rate_limit_blocks_after_failures(client):
    for _ in range(5):
        assert _login(client, password="wrong-password").status_code == 401
    # 达到上限后：即使密码正确也拒绝
    assert _login(client).status_code == 429


def test_rate_limit_state_persisted_in_db(client):
    """失败计数落库：跨请求、跨进程重启可见（同一条 DB 记录）。"""
    for _ in range(3):
        assert _login(client, password="wrong-password").status_code == 401
    with client.db_session_factory() as db:
        row = db.get(LoginFailure, "alice|testclient")
    assert row is not None
    assert row.failure_count == 3
    assert row.locked_until is None


def test_rate_limiter_resets_on_success(client):
    assert _login(client, password="wrong-password").status_code == 401
    assert _login(client).status_code == 200  # 成功登录清零计数
    for _ in range(4):
        assert _login(client, password="wrong-password").status_code == 401
    # 第 5 次失败：刚好达到阈值，本次仍返回 401，下一次才 429
    assert _login(client, password="wrong-password").status_code == 401
    assert _login(client).status_code == 429


def test_rate_limiter_window_expiry():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    TestingSession = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    Base.metadata.create_all(bind=engine)
    limiter = LoginRateLimiter(max_attempts=1, window_seconds=0)
    with TestingSession() as db:
        limiter.record_failure(db, "k")
        assert not limiter.is_blocked(db, "k")  # 窗口为 0，记录立即过期
