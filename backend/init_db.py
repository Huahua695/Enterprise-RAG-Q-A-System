"""数据库初始化脚本（幂等：已有数据时不会覆盖）

关键：必须在此文件所有 import 之前设置 os.environ，
因为 app.core.config.Settings 是模块级单例，在首次导入时即完成初始化。
"""
import os

# === 必须在所有 app import 之前设置 ===
os.environ.setdefault("DATABASE_URL", "sqlite:///./db_data/main.db")
os.environ.setdefault("VECTOR_STORE_DIR", "./db_data/vector_db")
os.environ.setdefault("UPLOAD_DIR", "./db_data/uploads")

os.makedirs("db_data", exist_ok=True)
os.makedirs("db_data/uploads", exist_ok=True)

# === 所有 app 导入必须在 os.environ 设置之后 ===
from app.core.database import engine, Base
from app.models import models  # noqa
from sqlalchemy.orm import Session
from app.models.models import User, KnowledgeBase, Document
from app.core.security import get_password_hash
from app.core.config import settings


def init_database():
    Base.metadata.create_all(bind=engine)
    print("[1/3] 数据表就绪")

    # 数据库迁移：为已有 documents 表添加 content 列（若不存在）
    import sqlite3
    db_path = settings.DATABASE_URL.replace("sqlite:///", "").replace("sqlite:///", "")
    conn = sqlite3.connect(db_path)
    cols = [row[1] for row in conn.execute("PRAGMA table_info(documents)").fetchall()]
    if "content" not in cols:
        conn.execute("ALTER TABLE documents ADD COLUMN content TEXT")
        conn.commit()
        print("[migration] documents 表已添加 content 列")
    conn.close()

    with Session(engine) as db:
        # 管理员：不存在则创建
        admin = db.query(User).filter(User.username == "admin").first()
        if not admin:
            admin = User(
                username="admin",
                hashed_password=get_password_hash("123456"),
                role="admin",
                is_active=True,
            )
            db.add(admin)
            db.commit()
            print("[2/3] 管理员账户创建成功 (admin / 123456)")
        else:
            print("[2/3] 管理员账户已存在，跳过")

        # 示例知识库：不存在则创建
        kb = db.query(KnowledgeBase).filter(KnowledgeBase.name == "电商商品知识库").first()
        if kb:
            print("[3/3] 示例知识库已存在，跳过")
        else:
            sample_path = "sample_data/ecommerce_products.txt"
            if os.path.exists(sample_path):
                kb = KnowledgeBase(
                    name="电商商品知识库",
                    description="示例数据：6 款电商商品",
                    owner_id=admin.id,
                    is_public=True,
                )
                db.add(kb)
                db.commit()

                doc = Document(
                    filename="ecommerce_products.txt",
                    file_path=os.path.abspath(sample_path),
                    file_type="txt",
                    file_size=os.path.getsize(sample_path),
                    knowledge_base_id=kb.id,
                    uploaded_by=admin.id,
                    status="pending",
                )
                db.add(doc)
                db.commit()

                try:
                    from app.services.rag_service import rag_engine
                    from app.services.document_parser import parse_document

                    text = parse_document(sample_path, "txt")
                    chunks = rag_engine.split_document(text)
                    rag_engine.add_documents(chunks, collection_name=f"kb_{kb.id}")
                    doc.content = text  # 保存原始文本
                    doc.chunk_count = len(chunks)
                    doc.status = "completed"
                    db.commit()
                    print(f"[3/3] 示例知识库构建成功（{len(chunks)} 个块）")
                except Exception as e:
                    doc.status = "failed"
                    doc.error_message = str(e)
                    db.commit()
                    print(f"[3/3] 向量化失败: {e}")
            else:
                print("[3/3] 示例数据文件不存在，跳过")

    print("数据库初始化完成！")


if __name__ == "__main__":
    init_database()
