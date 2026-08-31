# -*- coding: utf-8 -*-
"""Embedding 工厂：按 EMBEDDING_PROVIDER 构建向量化实例。

- local（默认）：本地哈希向量化，零依赖、离线可用、跨进程确定性
- fastembed：ONNX 本地推理的真实语义模型（默认 bge-small-zh-v1.5，
  首次运行需下载模型，可设 HF_ENDPOINT=https://hf-mirror.com 加速）
- openai：任意 OpenAI 兼容 /embeddings 接口（复用 AGNES_API_KEY / AGNES_BASE_URL）

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

        return FastEmbedEmbeddings(model_name=settings.EMBEDDING_MODEL)
    if provider == "openai":
        from langchain_openai import OpenAIEmbeddings

        return OpenAIEmbeddings(
            model=settings.EMBEDDING_MODEL,
            api_key=settings.AGNES_API_KEY,
            base_url=settings.AGNES_BASE_URL,
        )
    raise ValueError(f"未知 EMBEDDING_PROVIDER: {provider}（可选 local / fastembed / openai）")
