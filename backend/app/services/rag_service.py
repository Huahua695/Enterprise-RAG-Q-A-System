import logging
import os
import pickle
import shutil
from typing import List, Dict, AsyncGenerator

import faiss
import numpy as np
from langchain_openai import ChatOpenAI
from langchain_community.vectorstores import FAISS
from langchain_core.documents import Document
from langchain_core.prompts import PromptTemplate
from langchain_text_splitters import RecursiveCharacterTextSplitter

from app.core.config import settings
from app.services.embeddings_factory import build_embeddings

logger = logging.getLogger(__name__)


PROMPT_TEMPLATE = """你是一个知识库问答助手。请根据以下知识库内容回答用户的问题。

知识库内容：
{context}

用户问题：{question}

请基于知识库内容给出准确、详细的回答。如果知识库中没有相关信息，请明确说明"知识库中没有找到相关信息"，不要编造。
回答时请注明答案依据来自哪部分内容。"""


class RAGEngine:
    """RAG 引擎：文档分块 -> Embedding -> FAISS 向量索引 -> 检索 -> LLM 生成

    向量库按知识库隔离：每个知识库对应一个独立的 FAISS 索引目录
    （{VECTOR_STORE_DIR}/{collection_name}/），与原先 ChromaDB 的
    collection 概念一一对应。
    """

    def __init__(self):
        # 检索向量化：默认本地哈希，可经 EMBEDDING_PROVIDER 切换真实语义模型
        self.embeddings = build_embeddings()
        logger.info("Embedding provider=%s model=%s", settings.EMBEDDING_PROVIDER, settings.EMBEDDING_MODEL)
        self.llm = ChatOpenAI(
            api_key=settings.AGNES_API_KEY,
            base_url=settings.AGNES_BASE_URL,
            model=settings.AGNES_MODEL,
            temperature=0,
            streaming=True,
        )
        self.text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=500,
            chunk_overlap=50,
            length_function=len,
        )
        self.prompt_template = PromptTemplate(
            input_variables=["context", "question"],
            template=PROMPT_TEMPLATE,
        )
        os.makedirs(settings.VECTOR_STORE_DIR, exist_ok=True)

    # ---------- 向量索引管理 ----------

    def _index_path(self, collection_name: str) -> str:
        # 防止路径穿越，只允许字母数字下划线
        safe_name = "".join(c for c in collection_name if c.isalnum() or c == "_")
        return os.path.join(settings.VECTOR_STORE_DIR, safe_name)

    def _load_vectorstore(self, collection_name: str) -> FAISS | None:
        path = self._index_path(collection_name)
        if os.path.exists(os.path.join(path, "index.faiss")):
            return self._read_index(path)
        return None

    # ---------- 索引文件读写（绕开 faiss C++ 文件层的路径限制） ----------

    def _save_index(self, vectorstore: FAISS, path: str) -> None:
        """落盘索引与 docstore，文件格式与 langchain save_local 完全一致。

        不用 langchain 的 save_local/faiss.write_index：其 C++ 文件层在 Windows
        上无法写非 ASCII 路径（如 E:\\vibe项目\\...），这里先在内存序列化，
        再用 Python 文件 IO 落盘；faiss.deserialize_index 可无损读回。
        """
        os.makedirs(path, exist_ok=True)
        index_bytes = faiss.serialize_index(vectorstore.index).tobytes()
        with open(os.path.join(path, "index.faiss"), "wb") as f:
            f.write(index_bytes)
        with open(os.path.join(path, "index.pkl"), "wb") as f:
            pickle.dump((vectorstore.docstore, vectorstore.index_to_docstore_id), f)

    def _read_index(self, path: str) -> FAISS:
        """从磁盘读回索引（对应 _save_index / 旧版 save_local 的文件格式）。"""
        with open(os.path.join(path, "index.faiss"), "rb") as f:
            index = faiss.deserialize_index(np.frombuffer(f.read(), dtype="uint8"))
        with open(os.path.join(path, "index.pkl"), "rb") as f:
            docstore, index_to_docstore_id = pickle.load(f)
        return FAISS(
            embedding_function=self.embeddings,
            index=index,
            docstore=docstore,
            index_to_docstore_id=index_to_docstore_id,
        )

    # 单块超过该长度时做二次切分（字符数）
    MAX_CHUNK_SIZE = 1500

    def split_document(self, text: str) -> List[str]:
        """结构化分块：优先按 Markdown 标题（## ）切分，保持商品/章节完整归属；
        超大块二次字符切分；无标题结构的纯文本回退到字符切分。

        修复的问题：此前一律按 500 字符硬切，会把商品参数与标题分离到不同块，
        导致检索到的块丢失商品归属（如 iPhone 参数被拼到大疆条目下）。
        """
        sections = self._split_by_headers(text)
        chunks: List[str] = []
        for section in sections:
            section = section.strip()
            if not section:
                continue
            if len(section) <= self.MAX_CHUNK_SIZE:
                chunks.append(section)
            else:
                # 超大章节二次切分，每块携带章节标题保持归属
                title = section.split("\n", 1)[0]
                for sub in self.text_splitter.split_text(section):
                    if not sub.startswith(title):
                        sub = f"{title}\n{sub}"
                    chunks.append(sub)
        return chunks

    @staticmethod
    def _split_by_headers(text: str) -> List[str]:
        """按 Markdown 二级标题（## ）切分；无标题时整体返回"""
        sections: List[str] = []
        current: List[str] = []
        for line in text.split("\n"):
            if line.startswith("## ") and current:
                sections.append("\n".join(current))
                current = [line]
            else:
                current.append(line)
        if current:
            sections.append("\n".join(current))
        return sections

    def add_documents(self, texts: List[str], collection_name: str = "default") -> None:
        if not texts:
            return
        vectorstore = self._load_vectorstore(collection_name)
        if vectorstore is None:
            vectorstore = FAISS.from_texts(texts, self.embeddings)
        else:
            vectorstore.add_texts(texts)
        self._save_index(vectorstore, self._index_path(collection_name))

    def delete_collection(self, collection_name: str) -> bool:
        """删除整个知识库的索引目录；目录不存在时返回 False。"""
        path = self._index_path(collection_name)
        if os.path.isdir(path):
            shutil.rmtree(path)
            logger.info("已删除向量索引目录：%s", path)
            return True
        return False

    # ---------- 检索 ----------

    def retrieve(
        self,
        question: str,
        collection_names: List[str],
        k: int = 5,
    ) -> List[Document]:
        """从多个知识库索引中检索相似文档，合并去重后返回结果。

        修复：之前 merged[:k] 会在多知识库场景下只返回第一个知识库的结果。
        改为每个知识库各检索 k 条，合并后返回全部（最多 k*3 条），保证各知识库的文档都有机会被召回。
        """
        merged: List[Document] = []
        seen = set()
        for name in collection_names:
            try:
                vectorstore = self._load_vectorstore(name)
                if vectorstore is None:
                    continue
                docs = vectorstore.similarity_search(question, k=k)
                for doc in docs:
                    key = doc.page_content[:100]
                    if key not in seen:
                        seen.add(key)
                        merged.append(doc)
            except Exception:
                # 单个索引损坏不应拖垮整次检索，但必须留痕
                logger.warning("知识库 %s 索引加载失败，已跳过", name, exc_info=True)
                continue
        return merged[: min(k * 3, 15)]

    # ---------- 生成 ----------

    async def astream_answer(
        self,
        question: str,
        context_docs: List[Document],
    ) -> AsyncGenerator[str, None]:
        """基于检索结果流式生成答案（真流式，逐 token 输出）"""
        context = "\n\n".join(doc.page_content for doc in context_docs)
        if not context.strip():
            context = "（知识库暂无相关内容）"
        prompt_text = self.prompt_template.format(context=context, question=question)
        async for chunk in self.llm.astream(prompt_text):
            if chunk.content:
                yield chunk.content

    def ask_question(self, question: str, collection_name: str = "default") -> Dict:
        """同步问答（保留用于非流式场景/测试）"""
        docs = self.retrieve(question, [collection_name])
        context = "\n\n".join(doc.page_content for doc in docs)
        prompt_text = self.prompt_template.format(context=context, question=question)
        result = self.llm.invoke(prompt_text)
        references = [
            {"content": doc.page_content[:200], "metadata": doc.metadata}
            for doc in docs[:3]
        ]
        return {"answer": result.content, "references": references}


rag_engine = RAGEngine()
