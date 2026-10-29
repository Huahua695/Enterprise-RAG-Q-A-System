# -*- coding: utf-8 -*-
"""文档后台处理：解析 -> 切块 -> 向量化 -> 回写文档状态。

由上传接口经 FastAPI BackgroundTasks 调度，请求立即返回"已接收"，
前端按 status 轮询展示；生产环境可平滑升级为 Celery + Redis 任务队列，
接口层无需改动。
"""
import logging

from app.core.database import SessionLocal
from app.models.models import Document as DocumentModel
from app.services.document_parser import parse_document
from app.services.rag_service import rag_engine

logger = logging.getLogger(__name__)


def process_document(doc_id: int, kb_id: int, file_path: str, file_type: str) -> None:
    """后台执行文档向量化并回写状态。

    请求的 DB 会话在响应返回后即关闭，这里自建会话；任何异常都落入
    status="failed" + error_message，不向外抛（后台任务无调用方接错）。
    """
    db = SessionLocal()
    try:
        text = parse_document(file_path, file_type)
        chunks = rag_engine.split_document(text)
        # 解析出文本却没有切出任何块 => 入索引会是空的，却回报 completed、
        # chunk_count=0。此前这属于"静默成功"，用户完全无感知，必须显式失败。
        if not chunks:
            raise ValueError(
                "文档解析后没有可索引的内容（切块数为 0）："
                f"解析得到 {len(text or '')} 个字符。请确认文件非空且包含可提取的文本。"
            )

        # 写入来源 metadata：否则所有块的 metadata 为空，引用无法溯源到文件
        doc_row = db.get(DocumentModel, doc_id)
        metadatas = [
            {
                "source": doc_row.filename if doc_row else file_path,
                "doc_id": doc_id,
                "kb_id": kb_id,
            }
            for _ in chunks
        ]
        rag_engine.add_documents(chunks, collection_name=f"kb_{kb_id}", metadatas=metadatas)

        doc = db.get(DocumentModel, doc_id)
        if doc is not None:
            doc.content = text  # 保存解析文本，前端可预览
            doc.chunk_count = len(chunks)
            doc.status = "completed"
        db.commit()
        logger.info("文档后台索引成功：doc=%s kb=%s（%s 块）", doc_id, kb_id, len(chunks))
    except Exception as e:
        db.rollback()
        logger.exception("文档后台处理失败：doc=%s kb=%s", doc_id, kb_id)
        try:
            doc = db.get(DocumentModel, doc_id)
            if doc is not None:
                doc.status = "failed"
                # 只存可读的原因并截断，避免把含服务器路径的完整异常栈透传前端
                doc.error_message = str(e)[:500]
                db.commit()
        except Exception:
            db.rollback()
            logger.exception("文档失败状态回写失败：doc=%s", doc_id)
    finally:
        db.close()
