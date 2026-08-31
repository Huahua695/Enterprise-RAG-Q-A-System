from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from sqlalchemy.orm import Session
from typing import Optional, List
import logging
import os
import uuid

from app.core.database import get_db
from app.models.models import User, Document as DocumentModel, KnowledgeBase as KBModel
from app.schemas.chat import DocumentInfo, KnowledgeBaseCreate, KnowledgeBaseInfo
from app.core.security import get_current_user
from app.services.rag_service import rag_engine
from app.services.document_parser import parse_document
from app.core.config import settings

logger = logging.getLogger(__name__)

router = APIRouter()


# ==================== 知识库管理 ====================

@router.get("/knowledge-bases", response_model=List[KnowledgeBaseInfo])
async def list_knowledge_bases(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    kbs = db.query(KBModel).filter(
        (KBModel.owner_id == current_user.id) | (KBModel.is_public == True)
    ).order_by(KBModel.created_at.desc()).all()
    result = []
    for kb in kbs:
        result.append({
            "id": kb.id,
            "name": kb.name,
            "description": kb.description,
            "owner_id": kb.owner_id,
            "is_public": kb.is_public,
            "document_count": len(kb.documents),
            "created_at": kb.created_at
        })
    return result


@router.post("/knowledge-bases", response_model=dict)
async def create_knowledge_base(
    kb_data: KnowledgeBaseCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    new_kb = KBModel(
        name=kb_data.name,
        description=kb_data.description,
        owner_id=current_user.id,
        is_public=kb_data.is_public
    )
    db.add(new_kb)
    db.commit()
    db.refresh(new_kb)
    return {
        "id": new_kb.id,
        "name": new_kb.name,
        "description": new_kb.description,
        "owner_id": new_kb.owner_id,
        "is_public": new_kb.is_public,
        "document_count": 0,
        "created_at": new_kb.created_at
    }


@router.delete("/knowledge-bases/{kb_id}")
async def delete_knowledge_base(
    kb_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    kb = db.query(KBModel).filter(
        KBModel.id == kb_id,
        KBModel.owner_id == current_user.id
    ).first()
    if not kb:
        raise HTTPException(status_code=404, detail="知识库不存在或无权限")

    kb_id_value = kb.id
    file_paths = [doc.file_path for doc in kb.documents]
    db.delete(kb)
    db.commit()
    logger.info("知识库已删除：kb=%s owner=%s 文档数=%s", kb_id_value, current_user.id, len(file_paths))

    # 磁盘清理（尽力而为：失败只记日志，不影响删除结果）
    upload_root = os.path.abspath(settings.UPLOAD_DIR)
    removed_files = 0
    for path in file_paths:
        try:
            abs_path = os.path.abspath(path)
            # 只清理上传目录内的文件，防止 DB 数据异常时误删任意路径
            if abs_path.startswith(upload_root + os.sep) and os.path.exists(abs_path):
                os.remove(abs_path)
                removed_files += 1
        except OSError:
            logger.warning("上传文件清理失败：%s", path, exc_info=True)
    try:
        rag_engine.delete_collection(f"kb_{kb_id_value}")
    except OSError:
        logger.warning("知识库 %s 索引目录清理失败", kb_id_value, exc_info=True)

    return {"message": "知识库已删除", "cleaned_files": removed_files}


# ==================== 文档管理 ====================

@router.get("/documents", response_model=List[DocumentInfo])
async def list_documents(
    knowledge_base_id: Optional[int] = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    query = db.query(DocumentModel).filter(DocumentModel.uploaded_by == current_user.id)
    if knowledge_base_id:
        query = query.filter(DocumentModel.knowledge_base_id == knowledge_base_id)
    return query.order_by(DocumentModel.created_at.desc()).all()


@router.get("/documents/{doc_id}/content")
async def get_document_content(
    doc_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """获取文档的完整解析内容，用于前端预览"""
    doc = db.query(DocumentModel).filter(
        DocumentModel.id == doc_id,
        DocumentModel.uploaded_by == current_user.id
    ).first()
    if not doc:
        raise HTTPException(status_code=404, detail="文档不存在或无权限")

    text = doc.content or ""
    # 兼容旧文档：如果 content 为空，尝试从文件重新解析
    if not text and doc.file_path:
        try:
            if os.path.exists(doc.file_path):
                text = parse_document(doc.file_path, doc.file_type)
        except Exception:
            logger.warning("文档 %s（%s）重新解析失败", doc.id, doc.filename, exc_info=True)
            text = "[文件已不存在或无法解析]"

    return {
        "document_id": doc.id,
        "filename": doc.filename,
        "file_type": doc.file_type,
        "content": text
    }


@router.post("/documents/upload")
async def upload_document(
    file: UploadFile = File(...),
    knowledge_base_id: int = Form(...),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    # 检查知识库是否存在且属于当前用户
    kb = db.query(KBModel).filter(
        KBModel.id == knowledge_base_id,
        KBModel.owner_id == current_user.id
    ).first()
    if not kb:
        raise HTTPException(status_code=404, detail="知识库不存在或无权限")

    # 类型白名单：与 document_parser 支持的解析格式保持一致
    original_name = file.filename or ""
    file_ext = os.path.splitext(original_name)[1].lower()
    file_type = file_ext.lstrip(".")
    allowed_types = {t.strip().lower() for t in settings.ALLOWED_UPLOAD_TYPES.split(",") if t.strip()}
    if not file_type or file_type not in allowed_types:
        raise HTTPException(
            status_code=400,
            detail=f"不支持的文件类型: {file_ext or '(无扩展名)'}，允许: {', '.join(sorted(allowed_types))}",
        )

    # 大小限制：分块读取，超限立即拒绝（避免整文件读入内存）
    max_bytes = settings.max_upload_size_bytes
    parts: list[bytes] = []
    file_size = 0
    while chunk := await file.read(1024 * 1024):
        file_size += len(chunk)
        if file_size > max_bytes:
            raise HTTPException(status_code=413, detail=f"文件超过大小限制 {settings.MAX_UPLOAD_SIZE}")
        parts.append(chunk)
    if file_size == 0:
        raise HTTPException(status_code=400, detail="不能上传空文件")
    content = b"".join(parts)

    # 校验全部通过后才落盘
    upload_dir = settings.UPLOAD_DIR
    os.makedirs(upload_dir, exist_ok=True)
    unique_filename = f"{uuid.uuid4().hex}{file_ext}"
    file_path = os.path.join(upload_dir, unique_filename)
    with open(file_path, "wb") as f:
        f.write(content)

    # 创建文档记录
    new_doc = DocumentModel(
        filename=file.filename,
        file_path=file_path,
        file_type=file_type,
        file_size=len(content),
        knowledge_base_id=knowledge_base_id,
        uploaded_by=current_user.id,
        status="processing"
    )
    db.add(new_doc)
    db.commit()
    db.refresh(new_doc)

    # 解析文档并构建向量索引（同步处理，后续可改为 Celery 异步）
    try:
        text = parse_document(file_path, file_type)
        chunks = rag_engine.split_document(text)
        rag_engine.add_documents(chunks, collection_name=f"kb_{knowledge_base_id}")

        new_doc.content = text  # 保存解析文本，前端可预览
        new_doc.chunk_count = len(chunks)
        new_doc.status = "completed"
        db.commit()
        logger.info("文档上传并索引成功：doc=%s kb=%s %s（%s 块）", new_doc.id, knowledge_base_id, original_name, len(chunks))

        return {
            "message": "文档上传并索引成功",
            "document_id": new_doc.id,
            "chunks": len(chunks)
        }
    except Exception as e:
        logger.exception("文档处理失败：doc=%s kb=%s", new_doc.id, knowledge_base_id)
        new_doc.status = "failed"
        new_doc.error_message = str(e)
        db.commit()
        raise HTTPException(status_code=500, detail=f"文档处理失败: {str(e)}")
