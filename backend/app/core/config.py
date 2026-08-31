from pydantic_settings import BaseSettings
from typing import List


class Settings(BaseSettings):
    # 数据库配置
    DATABASE_URL: str = "sqlite:///./db_data/main.db"  # 默认本地 SQLite；生产请通过 .env 覆盖

    # JWT 配置
    SECRET_KEY: str = ""  # 必须通过 .env 的 SECRET_KEY 提供，切勿硬编码默认值
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 1440

    # Agnes AI API 配置
    AGNES_API_KEY: str = ""  # 必须通过 .env 的 AGNES_API_KEY 提供，切勿硬编码
    AGNES_BASE_URL: str = "https://apihub.agnes-ai.com/v1"
    AGNES_MODEL: str = "agnes-2.0-flash"
    AGNES_EMBEDDING_MODEL: str = "text-embedding-3-small"

    # 向量库配置（FAISS 本地持久化目录）
    VECTOR_STORE_DIR: str = "./db_data/vector_db"

    # 日志配置
    LOG_LEVEL: str = "INFO"  # DEBUG / INFO / WARNING / ERROR
    LOG_DIR: str = "./db_data/logs"

    # 文件上传配置
    UPLOAD_DIR: str = "./db_data/uploads"
    MAX_UPLOAD_SIZE: str = "10MB"

    # Redis 配置
    REDIS_URL: str = "redis://localhost:6379/0"

    # CORS 配置（逗号分隔的字符串，通过 allowed_origins_list 使用）
    ALLOWED_ORIGINS: str = "http://localhost:5173,http://localhost:3000"

    @property
    def allowed_origins_list(self) -> List[str]:
        return [o.strip() for o in self.ALLOWED_ORIGINS.split(",") if o.strip()]

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
