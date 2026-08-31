"""本地确定性哈希 Embedding

背景：Agnes API 不提供 embedding 模型（仅有对话/图像/视频模型），
因此检索侧使用本地向量化方案，无需联网、无需下载模型。

原理：
1. jieba 分词 + 中文 bigram 扩充，兼顾中英文
2. 每个 token 经 MD5 哈希映射到固定维度桶（hashing trick）
3. 词频累加后做 L2 归一化，FAISS 内积检索等价于余弦相似度

注意：MD5 保证跨进程确定性（Python 内置 hash() 每次启动随机，
会导致重启后查询向量与已持久化索引空间不一致，禁止使用）。

如需切换真实 Embedding 模型（如 bge / OpenAI / fastembed），
只需实现同样的 LangChain Embeddings 接口并替换 rag_service 中的实例。
"""
import hashlib
import logging
import re
from typing import List

import jieba
from langchain_core.embeddings import Embeddings

# jieba 在 import 时会把自身 logger 强制设为 DEBUG，需在导入后再压制，
# 否则分词词典构建日志会刷进 app 日志（此处仅本模块负责 jieba 的导入时机）
logging.getLogger("jieba").setLevel(logging.WARNING)


class LocalHashEmbeddings(Embeddings):
    def __init__(self, dim: int = 1024):
        self.dim = dim
        # 预热 jieba 词典，避免首次调用卡顿
        jieba.initialize()

    def _tokenize(self, text: str) -> List[str]:
        text = text.lower()
        tokens: List[str] = []
        for word in jieba.lcut(text):
            word = word.strip()
            if not word or re.fullmatch(r"[\s\W]+", word):
                continue
            tokens.append(word)
            # 中文词补充 bigram，提升短查询召回
            if len(word) > 1 and not word.isascii():
                tokens.extend(word[i : i + 2] for i in range(len(word) - 1))
        return tokens

    def _bucket(self, token: str) -> int:
        digest = hashlib.md5(token.encode("utf-8")).digest()
        return int.from_bytes(digest[:4], "little") % self.dim

    def _embed(self, text: str) -> List[float]:
        vec = [0.0] * self.dim
        for token in self._tokenize(text):
            vec[self._bucket(token)] += 1.0
        norm = sum(v * v for v in vec) ** 0.5
        if norm > 0:
            vec = [v / norm for v in vec]
        return vec

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        return [self._embed(t) for t in texts]

    def embed_query(self, text: str) -> List[float]:
        return self._embed(text)
