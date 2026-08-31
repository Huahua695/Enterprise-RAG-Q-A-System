# -*- coding: utf-8 -*-
"""Embedding 工厂测试：默认本地哈希、provider 切换、非法值报错。"""
import pytest
from langchain_openai import OpenAIEmbeddings

from app.core.config import settings
from app.services.embeddings_factory import build_embeddings
from app.services.local_embeddings import LocalHashEmbeddings


def test_default_provider_is_local_hash():
    embeddings = build_embeddings()
    assert isinstance(embeddings, LocalHashEmbeddings)
    assert embeddings.dim == settings.EMBEDDING_DIM


def test_openai_provider(monkeypatch):
    monkeypatch.setattr(settings, "EMBEDDING_PROVIDER", "openai")
    monkeypatch.setattr(settings, "AGNES_API_KEY", "dummy-key")
    embeddings = build_embeddings()
    assert isinstance(embeddings, OpenAIEmbeddings)


def test_unknown_provider_raises(monkeypatch):
    monkeypatch.setattr(settings, "EMBEDDING_PROVIDER", "no-such-provider")
    with pytest.raises(ValueError, match="EMBEDDING_PROVIDER"):
        build_embeddings()
