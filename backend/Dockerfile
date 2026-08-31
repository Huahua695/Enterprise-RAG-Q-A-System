# RAG 后端镜像：FastAPI + LangChain + FAISS（SQLite 版，无需外部数据库）
FROM python:3.13-slim

WORKDIR /app

# 先复制依赖清单利用构建缓存
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

ENV PYTHONUNBUFFERED=1

# 非 root 运行；数据目录预创建并赋权（Windows/macOS 的 bind mount 权限由 Docker Desktop 透传）
RUN useradd -m -u 1000 appuser \
    && mkdir -p /app/db_data \
    && chown -R appuser:appuser /app
USER appuser

EXPOSE 8000

# 生产启动：不开 --reload；SECRET_KEY 必须经环境变量注入（缺失时启动校验会拒绝）
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
