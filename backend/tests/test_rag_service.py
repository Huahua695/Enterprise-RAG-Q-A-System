# -*- coding: utf-8 -*-
"""RAG 核心逻辑单测：分块归属、跨库全局排序、相似度阈值、索引缓存与原子落盘。

此前 retrieve / split_document 没有任何直接单测，这两个函数恰恰是检索质量的
关键。这里用独立临时目录与确定性假向量，不依赖模型下载。
"""
import os

import numpy as np
import pytest
from langchain_core.embeddings import Embeddings

from app.core.config import settings
from app.services.rag_service import RAGEngine


class FakeEmbeddings(Embeddings):
    """确定性向量：关键词映射到固定方向，其余字符贡献一个正交的「噪声」分量。

    噪声分量让「命中同样关键词、但夹杂其他内容」的文本相似度略低，
    才能验证全局排序不是碰巧按插入顺序。
    """

    def __init__(self, dim: int = 8):
        self.dim = dim
        self.matched_chars = set("手机耳机吸尘器 ")
        self.directions = {
            "手机": [1.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
            "耳机": [0.0, 1.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
            "吸尘器": [0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 0.0, 0.0],
        }

    def _embed(self, text: str):
        vec = np.zeros(self.dim, dtype="float32")
        for kw, direction in self.directions.items():
            if kw in text:
                vec += np.array(direction, dtype="float32")
        # 未参与关键词匹配的字符 -> 最后一个维度的噪声分量
        noise = sum(1 for c in text if c not in self.matched_chars and not c.isspace())
        vec[-1] += 0.1 * noise
        if not vec.any():
            vec[-1] = 1.0
        norm = np.linalg.norm(vec)
        return (vec / norm).tolist()

    def embed_documents(self, texts):
        return [self._embed(t) for t in texts]

    def embed_query(self, text):
        return self._embed(text)


@pytest.fixture()
def engine(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "VECTOR_STORE_DIR", str(tmp_path / "vec"))
    monkeypatch.setattr(settings, "EMBEDDING_PROVIDER", "local")
    eng = RAGEngine.__new__(RAGEngine)  # 绕过 __init__ 里的 build_embeddings
    import threading

    eng._index_lock = threading.Lock()
    eng._store_cache = {}
    eng.embeddings = FakeEmbeddings()
    eng._llm = None
    from langchain_core.prompts import PromptTemplate

    from app.services.rag_service import PROMPT_TEMPLATE

    eng.prompt_template = PromptTemplate(
        input_variables=["context", "history", "question"], template=PROMPT_TEMPLATE
    )
    from langchain_text_splitters import RecursiveCharacterTextSplitter

    eng.text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=RAGEngine.MAX_CHUNK_SIZE - RAGEngine._TITLE_RESERVE,
        chunk_overlap=50,
        separators=["\n\n", "\n", "。", "！", "？", "；", "，", " ", ""],
        length_function=len,
    )
    return eng


# ---------------------------------------------------------------- 分块

def test_split_by_headers_keeps_title_with_body(engine):
    text = "## 商品A\n参数：很好\n## 商品B\n参数：也不错"
    chunks = engine.split_document(text)
    assert len(chunks) == 2
    assert chunks[0].startswith("## 商品A")
    assert chunks[1].startswith("## 商品B")


def test_split_keeps_h3_subsections_with_parent(engine):
    """二级以下（###）不单独切块，必须留在商品章节内。

    这条是回归护栏：曾把切分放宽到所有 # 前缀，导致「### 核心参数」成为独立
    块，块首行丢失商品名，引用无法溯源——正是本轮要修的问题。
    """
    text = (
        "# 总标题\n"
        "## 商品A\n"
        "### 核心参数\n参数内容\n"
        "### 产品特点\n特点内容\n"
        "## 商品B\n"
        "### 核心参数\n另一组参数\n"
    )
    chunks = engine.split_document(text)
    heads = [c.split("\n", 1)[0] for c in chunks]
    assert heads == ["# 总标题", "## 商品A", "## 商品B"]
    # 子小节内容仍在父章节块内
    assert "### 核心参数" in chunks[1]
    assert "### 产品特点" in chunks[1]


def test_every_chunk_starts_with_its_owning_heading(engine):
    """每个块的首行都应是标题，且块内只有一个顶级商品标题。

    首行是正文的块会让引用溯源失效（不知道内容属于哪个商品）。
    """
    text = "# 文档\n" + "\n".join(
        f"## 商品{i}\n" + ("### 核心参数\n" + "参数内容。" * 80 + "\n") for i in range(3)
    )
    chunks = engine.split_document(text)
    for c in chunks:
        assert c.split("\n", 1)[0].startswith("#"), f"首行不是标题: {c[:40]!r}"
        # 块内不应混入其他商品
        assert c.count("## 商品") <= 1, f"块内混入多个商品: {c[:40]!r}"


def test_oversized_section_is_split_and_keeps_title(engine):
    body = "这是一句用于填充的中文内容。" * 60  # 远超 MAX_CHUNK_SIZE
    text = f"## 大章节\n{body}"
    chunks = engine.split_document(text)
    assert len(chunks) > 1, "超长章节必须被二次切分"
    for c in chunks:
        assert c.startswith("## 大章节"), "二次切分后每块都要带上标题"


def test_chunks_respect_size_limit(engine):
    body = "测试内容。" * 200
    chunks = engine.split_document(f"## 段落\n{body}")
    for c in chunks:
        assert len(c) <= RAGEngine.MAX_CHUNK_SIZE + 10, f"块超长: {len(c)}"


# ---------------------------------------------------------------- 检索排序

def test_retrieve_sorts_globally_across_collections(engine):
    """跨库结果必须按相似度全局排序，而不是按知识库顺序拼接。

    这里显式放低阈值，确保两个库的块都保留下来，才能验证「顺序」本身；
    阈值的行为由下面的 test_retrieve_applies_similarity_threshold 单独覆盖。
    """
    engine.add_documents(["手机 相关的第一条"], "kb_1")
    engine.add_documents(["耳机 降噪相关内容"], "kb_2")

    docs = engine.retrieve("手机", ["kb_1", "kb_2"], k=2, min_cos=-1.0)
    assert len(docs) == 2
    # 与查询最相近的"手机"必须排第一
    assert "手机" in docs[0].page_content
    # 反转知识库顺序，结果顺序不应改变——这才是「全局排序」的证据
    docs_rev = engine.retrieve("手机", ["kb_2", "kb_1"], k=2, min_cos=-1.0)
    assert [d.page_content for d in docs] == [d.page_content for d in docs_rev]


def test_retrieve_prefers_better_match_regardless_of_kb_order(engine):
    """第二个库里更匹配的块，必须排在第一个库的弱匹配块之前。"""
    engine.add_documents(["手机 弱匹配 无关补充"], "kb_1")
    engine.add_documents(["手机"], "kb_2")
    docs = engine.retrieve("手机", ["kb_1", "kb_2"], k=2, min_cos=-1.0)
    # "手机"（完全命中）应排第一，尽管它所在的知识库排在第二个被检索
    assert docs[0].page_content == "手机"


def test_retrieve_applies_similarity_threshold(engine):
    """与查询正交的内容应被阈值挡掉，而不是凑数进 prompt。"""
    engine.add_documents(["手机 相关"], "kb_1")
    engine.add_documents(["耳机 无关内容"], "kb_2")

    # 阈值设高：只有"手机"能过
    docs = engine.retrieve("手机", ["kb_1", "kb_2"], k=5, min_cos=0.9)
    assert len(docs) == 1
    assert "手机" in docs[0].page_content


def test_retrieve_returns_empty_when_nothing_passes(engine):
    engine.add_documents(["耳机 无关"], "kb_1")
    docs = engine.retrieve("手机", ["kb_1"], k=5, min_cos=0.99)
    assert docs == []


def test_retrieve_tags_kb_in_metadata(engine):
    engine.add_documents(["手机 内容"], "kb_1", metadatas=[{"source": "a.txt"}])
    docs = engine.retrieve("手机", ["kb_1"], k=1)
    assert docs[0].metadata["kb"] == "kb_1"
    assert docs[0].metadata["source"] == "a.txt"


def test_retrieve_missing_collection_is_skipped(engine):
    engine.add_documents(["手机 内容"], "kb_1")
    docs = engine.retrieve("手机", ["kb_missing", "kb_1"], k=1)
    assert len(docs) == 1


# ---------------------------------------------------------------- 缓存与落盘

def test_index_is_cached_between_calls(engine):
    engine.add_documents(["手机 内容"], "kb_1")
    cached_after_add = engine._store_cache.get("kb_1")
    assert cached_after_add is not None, "写入后应留下缓存条目"

    engine.retrieve("手机", ["kb_1"], k=1)
    # 再检索时应命中同一个对象（不必重新反序列化）
    assert engine._store_cache["kb_1"][1] is cached_after_add[1]


def test_save_index_leaves_no_temp_files(engine, tmp_path):
    engine.add_documents(["手机 内容"], "kb_1")
    path = engine._index_path("kb_1")
    leftovers = [f for f in os.listdir(path) if f.endswith(".tmp")]
    assert leftovers == [], f"临时文件未清理: {leftovers}"


def test_delete_collection_invalidates_cache(engine):
    engine.add_documents(["手机 内容"], "kb_1")
    assert engine.delete_collection("kb_1") is True
    assert "kb_1" not in engine._store_cache


# ---------------------------------------------------------------- 历史预算

def test_history_block_keeps_recent_and_reverses_order(engine):
    history = [
        {"role": "user", "content": "第一问"},
        {"role": "assistant", "content": "第一答"},
        {"role": "user", "content": "那它的价格呢"},
    ]
    block = engine._build_history_block(history)
    lines = block.split("\n")
    assert lines[0].startswith("用户：第一问"), "应按时间正序"
    assert "那它的价格呢" in lines[-1]


def test_history_block_truncates_long_message(engine, monkeypatch):
    monkeypatch.setattr(settings, "CHAT_HISTORY_MSG_CHARS", 10)
    block = engine._build_history_block([{"role": "user", "content": "长" * 100}])
    assert len(block) <= 20 + len("用户："), "单条历史必须按预算截断"
    assert "…" in block


def test_history_block_respects_total_budget(engine, monkeypatch):
    monkeypatch.setattr(settings, "CHAT_HISTORY_MAX_CHARS", 60)
    history = [{"role": "user", "content": f"消息{i}"} for i in range(20)]
    block = engine._build_history_block(history)
    assert len(block) <= 60 + 10
    # 预算不足时优先保留最新的
    assert "消息19" in block


def test_empty_history_yields_empty_block(engine):
    assert engine._build_history_block(None) == ""
    assert engine._build_history_block([]) == ""
