import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.core.config import ensure_secret_key, settings
from app.core.logging_config import setup_logging
from app.core.database import engine, Base
from app.models import models  # noqa: F401  确保所有表注册到 metadata 后再建表

logger = logging.getLogger(__name__)

setup_logging()
ensure_secret_key()  # 缺少 SECRET_KEY 时快速失败，拒绝启动

Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="RAG 企业级知识库问答系统",
    description="基于 LangChain 的电商平台商品知识问答系统",
    version="1.0.0"
)

logger.info(
    "RAG 后端初始化：DB=%s 向量库=%s 上传目录=%s 日志级别=%s",
    settings.DATABASE_URL, settings.VECTOR_STORE_DIR, settings.UPLOAD_DIR, settings.LOG_LEVEL,
)

# CORS 配置
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
async def root():
    return {
        "message": "RAG 企业级知识库问答系统 API",
        "version": "1.0.0"
    }


@app.get("/health")
async def health_check():
    return {"status": "healthy"}


# 导入路由
from app.routes import auth, chat, knowledge_base  # noqa: E402

app.include_router(auth.router, prefix="/api/auth", tags=["认证"])
app.include_router(chat.router, prefix="/api/chat", tags=["问答"])
app.include_router(knowledge_base.router, prefix="/api/knowledge", tags=["知识库"])
