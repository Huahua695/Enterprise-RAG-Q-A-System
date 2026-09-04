from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from typing import Optional, List
import asyncio
import json
import logging

from app.core.database import get_db, SessionLocal
from app.models.models import User, Session as SessionModel, Message, KnowledgeBase as KBModel
from app.schemas.chat import ChatRequest, ChatResponse, SessionCreate, SessionInfo, MessageInfo
from app.core.security import get_current_user
from app.services.rag_service import rag_engine, LLMNotConfiguredError

logger = logging.getLogger(__name__)

router = APIRouter()


def _sse(payload: dict) -> str:
    """构造一条 SSE 消息（注意：必须是真实换行 \n\n，不能是字面量）"""
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


# ==================== 会话管理 ====================

@router.get("/sessions", response_model=List[SessionInfo])
async def list_sessions(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    sessions = db.query(SessionModel).filter(
        SessionModel.user_id == current_user.id
    ).order_by(SessionModel.updated_at.desc()).all()
    return sessions


@router.post("/sessions", response_model=SessionInfo)
async def create_session(
    session_data: SessionCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    kb_ids_json = json.dumps(session_data.knowledge_base_ids) if session_data.knowledge_base_ids else None
    new_session = SessionModel(
        title=session_data.title,
        user_id=current_user.id,
        knowledge_base_ids=kb_ids_json
    )
    db.add(new_session)
    db.commit()
    db.refresh(new_session)
    return new_session


@router.delete("/sessions/{session_id}")
async def delete_session(
    session_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    session = db.query(SessionModel).filter(
        SessionModel.id == session_id,
        SessionModel.user_id == current_user.id
    ).first()
    if not session:
        raise HTTPException(status_code=404, detail="会话不存在")
    db.delete(session)
    db.commit()
    return {"message": "会话已删除"}


@router.get("/sessions/{session_id}/messages", response_model=List[MessageInfo])
async def get_messages(
    session_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    session = db.query(SessionModel).filter(
        SessionModel.id == session_id,
        SessionModel.user_id == current_user.id
    ).first()
    if not session:
        raise HTTPException(status_code=404, detail="会话不存在")
    messages = db.query(Message).filter(
        Message.session_id == session_id
    ).order_by(Message.created_at).all()
    return messages


# ==================== 流式问答 ====================

@router.post("/send")
async def send_question(
    request: ChatRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """流式问答接口：SSE 推送 引用来源 -> 答案分片 -> 完成标记，并持久化消息"""

    session = db.query(SessionModel).filter(
        SessionModel.id == request.session_id,
        SessionModel.user_id == current_user.id
    ).first()
    if not session:
        raise HTTPException(status_code=404, detail="会话不存在")

    # 1. 持久化用户消息；首条消息自动用作会话标题
    user_msg = Message(
        session_id=session.id,
        role="user",
        content=request.message,
    )
    db.add(user_msg)
    if session.title == "新对话" and request.message.strip():
        session.title = request.message.strip()[:30]
    db.commit()

    # 2. 确定检索范围：会话绑定的知识库；未绑定时检索当前用户可见的全部知识库
    collection_names: List[str] = []
    if session.knowledge_base_ids:
        try:
            kb_ids = json.loads(session.knowledge_base_ids)
            if kb_ids:
                collection_names = [f"kb_{kb_id}" for kb_id in kb_ids]
        except (ValueError, TypeError):
            logger.debug("会话 %s 的 knowledge_base_ids 解析失败，回退到全部可见知识库", session.id)
    if not collection_names:
        kbs = db.query(KBModel).filter(
            (KBModel.owner_id == current_user.id) | (KBModel.is_public == True)
        ).all()
        collection_names = [f"kb_{kb.id}" for kb in kbs] or ["default"]

    # ORM 对象在流式期间可能随请求 db 会话关闭而过期，先取出纯值
    session_id = session.id
    user_id = current_user.id

    async def event_generator():
        full_answer = ""
        references: List[dict] = []
        try:
            # 3. 检索（同步 LangChain 调用放入线程池，避免阻塞事件循环）
            docs = await asyncio.to_thread(
                rag_engine.retrieve, request.message, collection_names
            )
            references = [
                {"content": doc.page_content[:200], "metadata": doc.metadata}
                for doc in docs  # 全部引用，保证多知识库结果都返回
            ]
            yield _sse({"type": "references", "references": references})

            # 4. 真流式生成答案
            async for chunk in rag_engine.astream_answer(request.message, docs):
                full_answer += chunk
                yield _sse({"type": "answer", "content": chunk})

            yield _sse({"type": "done"})
        except LLMNotConfiguredError as exc:
            # 配置缺失属于可自助修复的问题，把具体指引透传给前端展示
            logger.warning("问答失败：LLM 未配置。session=%s user=%s", session_id, user_id)
            yield _sse({"type": "error", "message": str(exc)})
        except Exception:
            # 原始异常只进日志，不透传给前端（避免泄漏内部实现细节）
            logger.exception("问答生成失败：session=%s user=%s", session_id, user_id)
            yield _sse({"type": "error", "message": "服务内部错误，请稍后重试"})
        finally:
            # 5. 持久化助手消息（流式响应期间原 request 作用域的 db 可能已关闭，另开会话）
            if full_answer:
                try:
                    with SessionLocal() as s:
                        s.add(Message(
                            session_id=session_id,
                            role="assistant",
                            content=full_answer,
                            references=json.dumps(references, ensure_ascii=False),
                        ))
                        s.commit()
                except Exception:
                    logger.exception("助手消息持久化失败：session=%s", session_id)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
