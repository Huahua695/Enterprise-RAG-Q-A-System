# -*- coding: utf-8 -*-
"""配置与安全基线测试：SECRET_KEY 启动校验、路径默认值统一。"""
import os
import subprocess
import sys

import pytest
from jose import jwt

from app.core.config import ensure_secret_key, settings


# ---------- SECRET_KEY 启动校验 ----------

def test_ensure_secret_key_raises_when_empty(monkeypatch):
    monkeypatch.setattr(settings, "SECRET_KEY", "")
    with pytest.raises(RuntimeError, match="SECRET_KEY"):
        ensure_secret_key()


def test_ensure_secret_key_passes_when_configured(monkeypatch):
    monkeypatch.setattr(settings, "SECRET_KEY", "x" * 32)
    ensure_secret_key()  # 不应抛异常


def test_jwt_library_allows_empty_key():
    """特性记录：python-jose 对空密钥不报错，这正是启动校验必须存在的原因。"""
    token = jwt.encode({"sub": "admin", "role": "admin"}, "", algorithm="HS256")
    payload = jwt.decode(token, "", algorithms=["HS256"])
    assert payload["role"] == "admin"


def test_main_refuses_to_boot_without_secret_key():
    """集成：SECRET_KEY 为空时，uvicorn 加载 app.main 必须直接失败。"""
    env = os.environ.copy()
    env["SECRET_KEY"] = ""
    env["LLM_API_KEY"] = "dummy-key-for-test"  # 隔离本机 .env，排除无关报错
    result = subprocess.run(
        [sys.executable, "-c", "import app.main"],
        cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=120,
    )
    assert result.returncode != 0
    assert "SECRET_KEY" in result.stderr


# ---------- 路径默认值（db_data 方案） ----------

def test_vector_store_dir_under_db_data():
    assert settings.VECTOR_STORE_DIR.replace("\\", "/").startswith("./db_data/")


def test_upload_dir_under_db_data():
    assert settings.UPLOAD_DIR.replace("\\", "/").startswith("./db_data/")


def test_database_url_points_to_main_db():
    assert settings.DATABASE_URL.startswith("sqlite:///./db_data/main.db")
