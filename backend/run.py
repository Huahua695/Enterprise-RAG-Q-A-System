"""启动脚本：必须在所有 app 导入之前设置环境变量"""
import os

os.environ.setdefault("DATABASE_URL", "sqlite:///./db_data/main.db")
os.environ.setdefault("VECTOR_STORE_DIR", "./db_data/vector_db")
os.environ.setdefault("UPLOAD_DIR", "./db_data/uploads")

os.makedirs("db_data", exist_ok=True)
os.makedirs("db_data/uploads", exist_ok=True)

from app.core.config import settings
import uvicorn

if __name__ == "__main__":
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
    )
