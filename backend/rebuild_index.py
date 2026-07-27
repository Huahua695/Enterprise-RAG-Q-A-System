"""重建向量索引脚本：按最新分块逻辑重新索引数据库中所有文档。

使用场景：分块策略调整、Embedding 模型更换后，无需重新上传文档。
用法： ./.venv/Scripts/python.exe rebuild_index.py
"""
import os
import shutil

from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import engine
from app.models.models import Document
from app.services.document_parser import parse_document
from app.services.rag_service import rag_engine


def rebuild():
    # 1. 清空全部 FAISS 索引
    store_dir = settings.VECTOR_STORE_DIR
    if os.path.exists(store_dir):
        shutil.rmtree(store_dir)
    os.makedirs(store_dir, exist_ok=True)
    print(f"[1/2] 已清空向量索引目录: {store_dir}")

    # 2. 逐文档重新解析、分块、索引
    ok, failed = 0, 0
    with Session(engine) as db:
        docs = db.query(Document).all()
        for doc in docs:
            try:
                if not os.path.exists(doc.file_path):
                    raise FileNotFoundError(f"文件不存在: {doc.file_path}")
                text = parse_document(doc.file_path, doc.file_type)
                chunks = rag_engine.split_document(text)
                rag_engine.add_documents(chunks, collection_name=f"kb_{doc.knowledge_base_id}")
                doc.chunk_count = len(chunks)
                doc.status = "completed"
                doc.error_message = None
                ok += 1
                print(f"  [OK] {doc.filename} -> kb_{doc.knowledge_base_id}, {len(chunks)} chunks")
            except Exception as e:
                doc.status = "failed"
                doc.error_message = str(e)
                failed += 1
                print(f"  [FAIL] {doc.filename}: {e}")
        db.commit()
    print(f"[2/2] 重建完成：成功 {ok} 个，失败 {failed} 个")


if __name__ == "__main__":
    rebuild()
