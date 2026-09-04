# -*- coding: utf-8 -*-
"""Embedding 工厂测试：默认 fastembed、provider 分发、非法值报错。

注意：所有用例都不真实加载 fastembed 模型（避免测试期下载/加载 90MB 权重），
fastembed 分发通过替换 langchain 侧类来验证。
"""
import pytest

from app.core.config import settings
from app.services.embeddings_factory import build_embeddings
from app.services.local_embeddings import LocalHashEmbeddings


def test_default_provider_is_fastembed():
    # 断言「出厂默认」而非环境变量生效值：CI 可能显式注入 EMBEDDING_PROVIDER=local 保持封闭
    from app.core.config import Settings

    assert Settings.model_fields["EMBEDDING_PROVIDER"].default == "fastembed"


def test_local_provider(monkeypatch):
    monkeypatch.setattr(settings, "EMBEDDING_PROVIDER", "local")
    embeddings = build_embeddings()
    assert isinstance(embeddings, LocalHashEmbeddings)
    assert embeddings.dim == settings.EMBEDDING_DIM


def test_fastembed_dispatch(monkeypatch):
    """替换 langchain 的 FastEmbedEmbeddings，验证分发与参数，不加载真实模型。"""
    import langchain_community.embeddings as lce

    captured = {}

    class DummyEmbeddings:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    monkeypatch.setattr(lce, "FastEmbedEmbeddings", DummyEmbeddings)
    embeddings = build_embeddings()
    assert isinstance(embeddings, DummyEmbeddings)
    assert captured["model_name"] == settings.EMBEDDING_MODEL
    assert captured["cache_dir"] == settings.EMBEDDING_CACHE_DIR


def test_openai_provider(monkeypatch):
    from langchain_openai import OpenAIEmbeddings

    monkeypatch.setattr(settings, "EMBEDDING_PROVIDER", "openai")
    monkeypatch.setattr(settings, "LLM_API_KEY", "dummy-key")
    assert isinstance(build_embeddings(), OpenAIEmbeddings)


def test_unknown_provider_raises(monkeypatch):
    monkeypatch.setattr(settings, "EMBEDDING_PROVIDER", "no-such-provider")
    with pytest.raises(ValueError, match="EMBEDDING_PROVIDER"):
        build_embeddings()
