# -*- coding: utf-8 -*-
"""端到端测试夹具：服务地址、就绪探测、管理员登录、测试文档。

运行前提：后端 run.py 与前端 npm run dev 已启动；服务不可达或账号
不可用时自动跳过（E2E 依赖真实环境，不适合硬失败）。
"""
import os
import pathlib

import httpx
import pytest

BASE_URL = os.environ.get("E2E_FRONTEND_URL", "http://localhost:5173")
ADMIN_USER = os.environ.get("E2E_ADMIN_USER", "admin")
ADMIN_PASS = os.environ.get("E2E_ADMIN_PASS", "123456")
FIXTURE_DIR = pathlib.Path(__file__).parent / "fixtures"


def _server_ready() -> bool:
    try:
        # 未带 token 访问受保护接口返回 401，同样说明后端已就绪
        resp = httpx.get(f"{BASE_URL}/api/auth/me", timeout=5)
        return resp.status_code in (200, 401)
    except httpx.HTTPError:
        return False


@pytest.fixture(scope="session")
def base_url():
    if not _server_ready():
        pytest.skip(f"前后端服务未就绪（{BASE_URL}），请先启动 backend/run.py 与 frontend npm run dev")
    return BASE_URL


@pytest.fixture(scope="session")
def admin_headers(base_url):
    resp = httpx.post(
        f"{base_url}/api/auth/login",
        json={"username": ADMIN_USER, "password": ADMIN_PASS},
        timeout=10,
    )
    if resp.status_code != 200:
        pytest.skip(f"管理员账号登录失败（{resp.status_code}），请确认默认账户 admin/123456 可用")
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


@pytest.fixture(scope="session")
def llm_ready():
    """问答链路依赖外部 LLM（AGNES_API_KEY），未配置时跳过问答用例。"""
    if os.environ.get("AGNES_API_KEY"):
        return
    env_path = pathlib.Path(__file__).parent.parent / "backend" / ".env"
    if env_path.exists():
        for line in env_path.read_text(encoding="utf-8", errors="ignore").splitlines():
            if line.strip().startswith("AGNES_API_KEY=") and line.split("=", 1)[1].strip():
                return
    pytest.skip("未配置 AGNES_API_KEY，跳过依赖大模型问答的用例")


@pytest.fixture(scope="session")
def product_doc_path():
    return FIXTURE_DIR / "星尘X1Pro商品.md"
