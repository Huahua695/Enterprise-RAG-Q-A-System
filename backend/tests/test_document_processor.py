# -*- coding: utf-8 -*-
"""document_processor 状态流转测试：completed / failed 两条路径。"""
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import app.services.document_processor as document_processor
from app.core.config import settings
from app.core.database import Base
from app.models.models import Document as DocumentModel, KnowledgeBase as KBModel
from app.services.document_processor import process_document


@pytest.fixture()
def db_env(tmp_path, monkeypatch):
    """独立 SQLite + 独立向量目录，后台任务会话指向测试库。"""
    engine = create_engine(
        f"sqlite:///{tmp_path / 'proc.db'}",
        connect_args={"check_same_thread": False},
    )
    TestingSession = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    Base.metadata.create_all(bind=engine)
    monkeypatch.setattr(document_processor, "SessionLocal", TestingSession)
    monkeypatch.setattr(settings, "VECTOR_STORE_DIR", str(tmp_path / "vector_db"))

    with TestingSession() as db:
        db.add(KBModel(id=1, name="kb", owner_id=1))
        db.add(DocumentModel(
            id=1, filename="a.txt", file_path=str(tmp_path / "a.txt"),
            file_type="txt", file_size=10, knowledge_base_id=1,
            uploaded_by=1, status="processing",
        ))
        db.commit()
    return TestingSession, tmp_path


def test_process_success(db_env):
    TestingSession, tmp_path = db_env
    (tmp_path / "a.txt").write_text("## 商品A\n电池容量 5000mAh", encoding="utf-8")

    process_document(1, 1, str(tmp_path / "a.txt"), "txt")

    with TestingSession() as db:
        doc = db.get(DocumentModel, 1)
    assert doc.status == "completed"
    assert doc.chunk_count >= 1
    assert "5000mAh" in doc.content
    assert (tmp_path / "vector_db" / "kb_1" / "index.faiss").exists()


def test_process_failure_marks_doc_failed(db_env):
    TestingSession, tmp_path = db_env

    process_document(1, 1, str(tmp_path / "missing.txt"), "txt")  # 文件不存在 → 解析抛错

    with TestingSession() as db:
        doc = db.get(DocumentModel, 1)
    assert doc.status == "failed"
    assert doc.error_message
