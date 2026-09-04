# -*- coding: utf-8 -*-
import re

from pydantic_settings import BaseSettings
from typing import List


class Settings(BaseSettings):
    # 数据库配置
    DATABASE_URL: str = "sqlite:///./db_data/main.db"  # 默认本地 SQLite；生产请通过 .env 覆盖

    # JWT 配置
    SECRET_KEY: str = ""  # 必须通过 .env 的 SECRET_KEY 提供，切勿硬编码默认值
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 1440

    # 登录限流（单进程内存实现；多 worker / 多实例部署需改用 Redis 等共享存储）
    LOGIN_RATE_LIMIT_ATTEMPTS: int = 5  # 窗口内允许的连续失败次数
    LOGIN_RATE_LIMIT_WINDOW_MINUTES: int = 15  # 限流窗口时长

    # LLM API 配置（任意 OpenAI 兼容接口：DeepSeek / 通义千问 / Ollama / one-api 等）
    LLM_API_KEY: str = ""  # 必须通过 .env 的 LLM_API_KEY 提供，切勿硬编码
    LLM_BASE_URL: str = ""  # 留空走 OpenAI 官方接口；第三方网关一般填到 /v1 一级
    LLM_MODEL: str = ""  # 留空时问答接口会返回明确的配置提示

    # 向量库配置（FAISS 本地持久化目录）
    VECTOR_STORE_DIR: str = "./db_data/vector_db"

    # Embedding 配置（切换 provider/模型后必须重建向量索引，见 embeddings_factory 文档）
    EMBEDDING_PROVIDER: str = "fastembed"  # fastembed（默认，真实语义）/ local（哈希）/ openai
    EMBEDDING_MODEL: str = "BAAI/bge-small-zh-v1.5"  # fastembed 模型；openai 模式下为接口模型名
    EMBEDDING_DIM: int = 1024  # 仅 local 哈希方案使用
    EMBEDDING_CACHE_DIR: str = "./db_data/models"  # 语义模型缓存（首次运行自动下载约 90MB）

    # 日志配置
    LOG_LEVEL: str = "INFO"  # DEBUG / INFO / WARNING / ERROR
    LOG_DIR: str = "./db_data/logs"

    # 文件上传配置
    UPLOAD_DIR: str = "./db_data/uploads"
    MAX_UPLOAD_SIZE: str = "10MB"
    # 允许上传的扩展名白名单（与 document_parser 支持的解析格式一致）
    ALLOWED_UPLOAD_TYPES: str = "pdf,docx,txt,md,markdown,xlsx,xls"

    # Redis 配置
    REDIS_URL: str = "redis://localhost:6379/0"

    # CORS 配置（逗号分隔的字符串，通过 allowed_origins_list 使用）
    ALLOWED_ORIGINS: str = "http://localhost:5173,http://localhost:3000"

    @property
    def allowed_origins_list(self) -> List[str]:
        return [o.strip() for o in self.ALLOWED_ORIGINS.split(",") if o.strip()]

    @property
    def max_upload_size_bytes(self) -> int:
        """把 '10MB' / '512KB' 这类字符串解析为字节数；解析失败回退 10MB。"""
        m = re.fullmatch(r"(\d+(?:\.\d+)?)\s*(B|KB|MB|GB)?", self.MAX_UPLOAD_SIZE.strip(), re.IGNORECASE)
        if not m:
            return 10 * 1024 * 1024
        multiplier = {"B": 1, "KB": 1024, "MB": 1024 ** 2, "GB": 1024 ** 3}[(m.group(2) or "B").upper()]
        return int(float(m.group(1)) * multiplier)

    class Config:
        env_file = ".env"
        case_sensitive = True


settings = Settings()


def ensure_secret_key() -> None:
    """启动校验：SECRET_KEY 必须显式配置。

    空密钥下 python-jose 仍可正常签发/校验 JWT（实测），服务不会报错，
    但任何人都能伪造任意用户的 token。因此只在 Web 入口（main.py）调用，
    离线脚本（init_db / rebuild_index）不调用，避免阻碍无 .env 的初始化流程。
    """
    if not settings.SECRET_KEY:
        raise RuntimeError(
            "SECRET_KEY 未配置：请复制 backend/.env.example 为 backend/.env 并填写 SECRET_KEY"
            "（可用 python -c \"import secrets; print(secrets.token_hex(32))\" 生成）"
        )
