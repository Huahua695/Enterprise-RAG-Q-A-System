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
    VECTOR_STORE_DIR: str = "./vector_db"

    # 文件上传配置
    UPLOAD_DIR: str = "./uploads"
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
