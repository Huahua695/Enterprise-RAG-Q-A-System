# -*- coding: utf-8 -*-
"""上传安全与删除清理测试：类型白名单、大小限制、删除知识库时的磁盘清理。"""
import io
import os

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.config import settings
from app.core.database import Base, get_db
from app.core.security import get_current_user
from app.models.models import KnowledgeBase as KBModel
from app.routes.knowledge_base import router


class FakeUser:
    id = 1


@pytest.fixture()
def client(tmp_path, monkeypatch):
    """独立 SQLite + 独立磁盘目录的 TestClient，不触碰真实 db_data。"""
    engine = create_engine(
        f"sqlite:///{tmp_path / 'test.db'}",
        connect_args={"check_same_thread": False},
    )
    TestingSession = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    Base.metadata.create_all(bind=engine)

    upload_dir = tmp_path / "uploads"
    vector_dir = tmp_path / "vector_db"
    monkeypatch.setattr(settings, "UPLOAD_DIR", str(upload_dir))
    monkeypatch.setattr(settings, "VECTOR_STORE_DIR", str(vector_dir))

    test_app = FastAPI()
    test_app.include_router(router)

    def override_db():
        db = TestingSession()
        try:
            yield db
        finally:
            db.close()

    test_app.dependency_overrides[get_db] = override_db
    test_app.dependency_overrides[get_current_user] = lambda: FakeUser()

    with TestingSession() as db:
        db.add(KBModel(id=1, name="测试库", owner_id=1, is_public=False))
        db.commit()

    with TestClient(test_app) as c:
        c.upload_dir = upload_dir
        c.vector_dir = vector_dir
        yield c


def _listdir(path) -> list:
    """目录可能尚未创建（请求在校验阶段就被拒绝），不存在视为空。"""
    return os.listdir(path) if os.path.isdir(path) else []


def _upload(client, name: str, payload: bytes, mime: str = "application/octet-stream"):
    return client.post(
        "/documents/upload",
        data={"knowledge_base_id": "1"},
        files={"file": (name, io.BytesIO(payload), mime)},
    )


def test_upload_txt_ok(client):
    resp = _upload(client, "商品.txt", "## 商品A\n性价比很高".encode("utf-8"), "text/plain")
    assert resp.status_code == 200, resp.text
    assert resp.json()["chunks"] >= 1
    assert len(_listdir(client.upload_dir)) == 1


def test_upload_rejects_disallowed_type(client):
    resp = _upload(client, "evil.exe", b"MZ-fake-binary")
    assert resp.status_code == 400
    assert "不支持的文件类型" in resp.json()["detail"]
    assert _listdir(client.upload_dir) == []  # 拒绝时不落盘


def test_upload_rejects_no_extension(client):
    resp = _upload(client, "README", b"some text")
    assert resp.status_code == 400


def test_upload_rejects_empty_file(client):
    resp = _upload(client, "empty.txt", b"", "text/plain")
    assert resp.status_code == 400
    assert "空文件" in resp.json()["detail"]


def test_upload_rejects_oversize(client, monkeypatch):
    monkeypatch.setattr(settings, "MAX_UPLOAD_SIZE", "1KB")
    resp = _upload(client, "big.txt", b"x" * 2048, "text/plain")
    assert resp.status_code == 413
    assert _listdir(client.upload_dir) == []


def test_max_upload_size_parsing(monkeypatch):
    cases = {"10MB": 10 * 1024 ** 2, "512KB": 512 * 1024, "100": 100, "2GB": 2 * 1024 ** 3}
    for raw, expected in cases.items():
        monkeypatch.setattr(settings, "MAX_UPLOAD_SIZE", raw)
        assert settings.max_upload_size_bytes == expected, raw
    monkeypatch.setattr(settings, "MAX_UPLOAD_SIZE", "not-a-number")
    assert settings.max_upload_size_bytes == 10 * 1024 ** 2  # 回退默认


def test_delete_kb_cleans_disk(client):
    assert _upload(client, "商品.txt", "## 商品A\n内容".encode("utf-8"), "text/plain").status_code == 200
    assert len(_listdir(client.upload_dir)) == 1
    assert (client.vector_dir / "kb_1" / "index.faiss").exists()

    resp = client.delete("/knowledge-bases/1")
    assert resp.status_code == 200, resp.text
    assert resp.json()["cleaned_files"] == 1
    assert _listdir(client.upload_dir) == []          # 上传文件已清理
    assert not (client.vector_dir / "kb_1").exists()    # 索引目录已清理
