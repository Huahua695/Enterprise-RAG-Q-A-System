# -*- coding: utf-8 -*-
"""LLM 接口配置测试：超时/重试参数是否按配置下发到 ChatOpenAI。

注意：全部用例都不发起真实网络请求——ChatOpenAI 的构造是惰性的
（只在真正调用时才连网关），embedding 也替换为哑实现，不加载模型。
"""
import pytest

from app.core.config import Settings, settings
from app.services.rag_service import LLMNotConfiguredError, RAGEngine


# ---------- 出厂默认值 ----------

def test_llm_timeout_defaults():
    """断言「出厂默认」而非运行值：CI/本机可能用环境变量覆盖。"""
    assert Settings.model_fields["LLM_TIMEOUT"].default == 60
    assert Settings.model_fields["LLM_MAX_RETRIES"].default == 2


# ---------- 参数下发 ----------

class _DummyEmbeddings:
    """替身：避免测试期加载真实 embedding 模型。"""

    dim = 4

    def embed_documents(self, texts):
        return [[0.0] * self.dim for _ in texts]

    def embed_query(self, _text):
        return [0.0] * self.dim


def _make_engine(monkeypatch) -> RAGEngine:
    import app.services.rag_service as rs

    monkeypatch.setattr(rs, "build_embeddings", lambda: _DummyEmbeddings())
    return rs.RAGEngine()


def test_llm_receives_timeout_and_retries(monkeypatch):
    engine = _make_engine(monkeypatch)
    monkeypatch.setattr(settings, "LLM_API_KEY", "dummy-key")
    monkeypatch.setattr(settings, "LLM_MODEL", "dummy-model")
    monkeypatch.setattr(settings, "LLM_TIMEOUT", 42)
    monkeypatch.setattr(settings, "LLM_MAX_RETRIES", 7)

    # langchain_openai 把构造时的 timeout 别名存为 request_timeout 字段
    assert engine.llm.request_timeout == 42
    assert engine.llm.max_retries == 7


def test_llm_uses_configured_base_url_and_model(monkeypatch):
    engine = _make_engine(monkeypatch)
    monkeypatch.setattr(settings, "LLM_API_KEY", "dummy-key")
    monkeypatch.setattr(settings, "LLM_MODEL", "qwen2.5-7b-instruct")
    monkeypatch.setattr(settings, "LLM_BASE_URL", "http://localhost:1234/v1")

    assert engine.llm.model_name == "qwen2.5-7b-instruct"
    assert str(engine.llm.openai_api_base) == "http://localhost:1234/v1"


def test_llm_constructed_once(monkeypatch):
    """惰性构建 + 缓存：多次访问 llm 只实例化一次。"""
    engine = _make_engine(monkeypatch)
    monkeypatch.setattr(settings, "LLM_API_KEY", "dummy-key")
    monkeypatch.setattr(settings, "LLM_MODEL", "dummy-model")

    assert engine.llm is engine.llm


# ---------- 未配置时的报错口径（回归） ----------

@pytest.mark.parametrize("missing", ["LLM_API_KEY", "LLM_MODEL"])
def test_llm_not_configured_error_is_actionable(monkeypatch, missing):
    engine = _make_engine(monkeypatch)
    monkeypatch.setattr(settings, "LLM_API_KEY", "dummy-key")
    monkeypatch.setattr(settings, "LLM_MODEL", "dummy-model")
    monkeypatch.setattr(settings, missing, "")

    with pytest.raises(LLMNotConfiguredError) as exc:
        _ = engine.llm
    # 报错必须点明缺哪个变量、去哪里补，便于用户自助修复
    assert missing in str(exc.value)
    assert "backend/.env" in str(exc.value)
