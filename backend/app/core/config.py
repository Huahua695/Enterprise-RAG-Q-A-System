from pydantic_settings import BaseSettings
from typing import List


class Settings(BaseSettings):
    # 数据库配置
    DATABASE_URL: str = "postgresql://postgres:postgres@localhost:5432/rag_knowledge_base"

    # JWT 配置
    SECRET_KEY: str = "rag-knowledge-base-secret-key-2026-change-in-production"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 1440

    # Agnes AI API 配置
    AGNES_API_KEY: str = "sk-x8zRR5mR8Q6xYDrZRheUidKNGC4R2TcDlnMU1W7a0OrKw6zs"
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
