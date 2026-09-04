# -*- coding: utf-8 -*-
"""Embedding 工厂：按 EMBEDDING_PROVIDER 构建向量化实例。

- local（默认）：本地哈希向量化，零依赖、离线可用、跨进程确定性
- fastembed：ONNX 本地推理的真实语义模型（默认 bge-small-zh-v1.5，
  首次运行需下载模型，可设 HF_ENDPOINT=https://hf-mirror.com 加速）
- openai：任意 OpenAI 兼容 /embeddings 接口（复用 LLM_API_KEY / LLM_BASE_URL）

注意：不同 provider 的向量空间互不兼容——切换 provider 或模型后，
必须删除 db_data/vector_db/ 并执行 rebuild_index.py（或重新上传文档）重建索引。
"""
import logging

from app.core.config import settings

logger = logging.getLogger(__name__)


def build_embeddings():
    provider = settings.EMBEDDING_PROVIDER.strip().lower()
    if provider in ("local", "hash", ""):
        from app.services.local_embeddings import LocalHashEmbeddings

        return LocalHashEmbeddings(dim=settings.EMBEDDING_DIM)
    if provider == "fastembed":
        from langchain_community.embeddings import FastEmbedEmbeddings

        # 模型缓存显式放 db_data（随 Docker 卷持久化），避免落 Temp 被系统清理
        return FastEmbedEmbeddings(
            model_name=settings.EMBEDDING_MODEL,
            cache_dir=settings.EMBEDDING_CACHE_DIR,
        )
    if provider == "openai":
        if not settings.LLM_API_KEY:
            raise ValueError(
                "EMBEDDING_PROVIDER=openai 需要 LLM_API_KEY：请在 backend/.env 中设置"
                "（任意提供 /embeddings 接口的 OpenAI 兼容服务，配合 LLM_BASE_URL）"
            )
        from langchain_openai import OpenAIEmbeddings

        return OpenAIEmbeddings(
            model=settings.EMBEDDING_MODEL,
            api_key=settings.LLM_API_KEY,
            base_url=settings.LLM_BASE_URL or None,
        )
    raise ValueError(f"未知 EMBEDDING_PROVIDER: {provider}（可选 local / fastembed / openai）")
