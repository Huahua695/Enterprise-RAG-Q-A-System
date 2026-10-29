import logging
import os
import pickle
import shutil
import threading
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


class LLMNotConfiguredError(RuntimeError):
    """LLM 接口未配置（LLM_API_KEY / LLM_MODEL 为空）时抛出，携带可操作的配置指引。"""


PROMPT_TEMPLATE = """你是一个知识库问答助手。请根据以下知识库内容回答用户的问题。

知识库内容：
{context}

历史对话（供理解指代，可能为空）：
{history}

用户问题：{question}

请基于知识库内容给出准确、详细的回答。如果知识库中没有相关信息，请明确说明"知识库中没有找到相关信息"，不要编造。
回答时请注明答案依据来自哪部分内容。
若用户问题中的指代（如"它""这个""那款"）需结合历史对话才能确定，请按历史对话理解后再作答。"""


class RAGEngine:
    """RAG 引擎：文档分块 -> Embedding -> FAISS 向量索引 -> 检索 -> LLM 生成

    向量库按知识库隔离：每个知识库对应一个独立的 FAISS 索引目录
    （{VECTOR_STORE_DIR}/{collection_name}/），与原先 ChromaDB 的
    collection 概念一一对应。
    """

    def __init__(self):
        # 向量化改为后台任务后，同一索引可能被并发读写，全部索引操作串行化
        self._index_lock = threading.Lock()
        # 索引内存缓存：{collection_name: (index.faiss 的 mtime, FAISS)}
        # 此前每次检索都全量 deserialize + pickle.load，多知识库时读放大严重
        self._store_cache: dict[str, tuple[float, FAISS]] = {}
        # 检索向量化：默认本地哈希，可经 EMBEDDING_PROVIDER 切换真实语义模型
        self.embeddings = build_embeddings()
        logger.info("Embedding provider=%s model=%s", settings.EMBEDDING_PROVIDER, settings.EMBEDDING_MODEL)
        # LLM 客户端惰性构建：未配置 LLM_API_KEY/LLM_MODEL 时后端仍可正常启动
        # （上传/检索不受影响），首次问答时才实例化并给出明确配置提示
        self._llm: ChatOpenAI | None = None
        self.text_splitter = RecursiveCharacterTextSplitter(
            # 预算扣掉标题占位，保证「标题 + 正文」整体不超过 MAX_CHUNK_SIZE
            chunk_size=max(self.MAX_CHUNK_SIZE - self._TITLE_RESERVE, 100),
            chunk_overlap=50,
            # 中文没有空格，默认分隔符会一路退化到逐字符硬切、腰斩句子；
            # 显式按句末标点优先切分
            separators=["\n\n", "\n", "。", "！", "？", "；", "，", " ", ""],
            length_function=len,
        )
        self.prompt_template = PromptTemplate(
            input_variables=["context", "history", "question"],
            template=PROMPT_TEMPLATE,
        )
        os.makedirs(settings.VECTOR_STORE_DIR, exist_ok=True)

    @property
    def llm(self) -> ChatOpenAI:
        if self._llm is None:
            if not settings.LLM_MODEL or not settings.LLM_API_KEY:
                missing = [
                    name for name, val in (
                        ("LLM_API_KEY", settings.LLM_API_KEY),
                        ("LLM_MODEL", settings.LLM_MODEL),
                    ) if not val
                ]
                raise LLMNotConfiguredError(
                    f"LLM 接口未配置：请在 backend/.env 中设置 {' 和 '.join(missing)}"
                    "（任意 OpenAI 兼容接口；第三方网关另按需设置 LLM_BASE_URL，"
                    "无需鉴权的本地服务可将 LLM_API_KEY 填任意占位值）"
                )
            self._llm = ChatOpenAI(
                api_key=settings.LLM_API_KEY,
                base_url=settings.LLM_BASE_URL or None,
                model=settings.LLM_MODEL,
                temperature=0,
                streaming=True,
                timeout=settings.LLM_TIMEOUT,
                max_retries=settings.LLM_MAX_RETRIES,
            )
        return self._llm

    # ---------- 向量索引管理 ----------

    def _index_path(self, collection_name: str) -> str:
        # 防止路径穿越，只允许字母数字下划线
        safe_name = "".join(c for c in collection_name if c.isalnum() or c == "_")
        return os.path.join(settings.VECTOR_STORE_DIR, safe_name)

    def _load_vectorstore(self, collection_name: str) -> FAISS | None:
        """取索引：优先内存缓存，未命中才读盘。

        命中缓存前比对 index.faiss 的 mtime：索引可能被 rebuild_index.py 等
        其他进程重写，靠 mtime 失效可避免读到过期缓存。
        """
        path = self._index_path(collection_name)
        faiss_file = os.path.join(path, "index.faiss")
        if not os.path.exists(faiss_file):
            return None

        mtime = os.path.getmtime(faiss_file)
        cached = self._store_cache.get(collection_name)
        if cached is not None and cached[0] == mtime:
            return cached[1]

        vectorstore = self._read_index(path)
        self._store_cache[collection_name] = (mtime, vectorstore)
        return vectorstore

    def _invalidate_cache(self, collection_name: str) -> None:
        self._store_cache.pop(collection_name, None)

    # ---------- 索引文件读写（绕开 faiss C++ 文件层的路径限制） ----------

    def _save_index(self, vectorstore: FAISS, path: str) -> None:
        """落盘索引与 docstore，文件格式与 langchain save_local 完全一致。

        不用 langchain 的 save_local/faiss.write_index：其 C++ 文件层在 Windows
        上无法写非 ASCII 路径（如 E:\\vibe项目\\...），这里先在内存序列化，
        再用 Python 文件 IO 落盘；faiss.deserialize_index 可无损读回。

        先写临时文件再 os.replace 原子替换：否则 index.faiss 与 index.pkl 的
        写入之间存在窗口，并发检索可能读到「新 faiss + 旧 pkl」的撕裂状态。
        """
        os.makedirs(path, exist_ok=True)
        faiss_path = os.path.join(path, "index.faiss")
        pkl_path = os.path.join(path, "index.pkl")

        index_bytes = faiss.serialize_index(vectorstore.index).tobytes()
        with open(faiss_path + ".tmp", "wb") as f:
            f.write(index_bytes)
        with open(pkl_path + ".tmp", "wb") as f:
            pickle.dump((vectorstore.docstore, vectorstore.index_to_docstore_id), f)

        # os.replace 在 Windows/POSIX 上都是原子操作
        os.replace(faiss_path + ".tmp", faiss_path)
        os.replace(pkl_path + ".tmp", pkl_path)

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

    # 单块上限（字符）。依据实测而非估计：bge-small-zh-v1.5 有效窗口 512 token，
    # 纯中文文本经实测为 1 字符 ≈ 1 token（500 字符 = 502 token），含英文型号/
    # 数字的混合文本约 1 字符 ≈ 0.63 token。超过窗口的内容在 embedding 时会被
    # 静默截断，块尾永远检索不到，因此按最坏情况（纯中文）取值。
    MAX_CHUNK_SIZE = 500
    # 二次切分时每块携带章节标题，标题计入上面的上限，故正文预算要扣掉标题
    _TITLE_RESERVE = 40

    def split_document(self, text: str) -> List[str]:
        """结构化分块：优先按 Markdown 标题切分，保持商品/章节完整归属；
        超大块二次切分；无标题结构的纯文本回退到字符切分。

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
                title = self._top_title(section)
                for sub in self.text_splitter.split_text(section):
                    if title and not sub.lstrip("\ufeff").startswith(title):
                        sub = f"{title}\n{sub}"
                    chunks.append(sub)
        return chunks

    @staticmethod
    def _split_by_headers(text: str) -> List[str]:
        """按 Markdown 二级标题切分，二级以下（###/####）保留在父章节内。

        为什么只切到二级：
        - 示例/常见知识库文档里，商品、制度条目通常是 ##，其下 ### 是「核心参数」
          「产品特点」这类子小节。若按 ### 也切，参数块的首行会变成 "### 核心参数"，
          商品归属彻底丢失——检索到参数却不知道是哪款商品，正是要修的问题。
        - 一级标题（#）视为文档整体标题，出现在节首时也作为分隔。

        同时兼容只有 # 或同时有 #/## 的文档；无标题时整体返回。
        """
        sections: List[str] = []
        current: List[str] = []
        for line in text.split("\n"):
            is_section_head = line.startswith("## ") or line.startswith("# ")
            if is_section_head and current:
                sections.append("\n".join(current))
                current = [line]
            else:
                current.append(line)
        if current:
            sections.append("\n".join(current))
        return sections

    @staticmethod
    def _top_title(section: str) -> str:
        """取章节的顶级标题行（跳过 BOM 与空行），用于二次切分时保持归属。"""
        for line in section.split("\n"):
            stripped = line.lstrip("\ufeff").strip()
            if not stripped:
                continue
            return stripped if stripped.startswith("#") else ""
        return ""

    def add_documents(
        self,
        texts: List[str],
        collection_name: str = "default",
        metadatas: List[dict] | None = None,
    ) -> None:
        if not texts:
            return
        with self._index_lock:
            vectorstore = self._load_vectorstore(collection_name)
            if vectorstore is None:
                vectorstore = FAISS.from_texts(texts, self.embeddings, metadatas=metadatas)
            else:
                vectorstore.add_texts(texts, metadatas=metadatas)
            path = self._index_path(collection_name)
            self._save_index(vectorstore, path)
            # 用刚写入的对象回填缓存（不必立刻重新读盘），mtime 与磁盘一致
            self._store_cache[collection_name] = (
                os.path.getmtime(os.path.join(path, "index.faiss")),
                vectorstore,
            )

    def delete_collection(self, collection_name: str) -> bool:
        """删除整个知识库的索引目录；目录不存在时返回 False。"""
        path = self._index_path(collection_name)
        with self._index_lock:
            self._invalidate_cache(collection_name)
            if os.path.isdir(path):
                shutil.rmtree(path)
                logger.info("已删除向量索引目录：%s", path)
                return True
            return False

    # ---------- 检索 ----------

    @staticmethod
    def _dedupe_key(doc: Document) -> str:
        """去重键：优先用 metadata 里的来源+块内容，避免不同文件的同前缀块被误删。"""
        source = (doc.metadata or {}).get("source", "")
        return f"{source}\x00{doc.page_content[:100]}"

    def retrieve(
        self,
        question: str,
        collection_names: List[str],
        k: int = 5,
        min_cos: float | None = None,
    ) -> List[Document]:
        """从多个知识库检索，跨库按相似度全局排序后返回 top-k。

        三个修复：
        1. 用 similarity_search_with_score 拿到真实距离，不再丢弃分数；
        2. 跨库合并后按距离全局升序排序——此前按「库的顺序」追加，第一个库的
           第 5 名会排在第三个库的第 1 名之前；
        3. 低于相似度阈值的结果直接丢弃，避免无关内容进 prompt 诱导幻觉。

        注意索引是 IndexFlatL2：返回值是 L2 距离，越小越相似，排序必须升序。
        向量已 L2 归一化，故 cos = 1 - d^2 / 2。
        """
        if min_cos is None:
            min_cos = settings.RETRIEVAL_MIN_COS

        scored: List[tuple[float, Document]] = []
        seen = set()
        for name in collection_names:
            try:
                vectorstore = self._load_vectorstore(name)
                if vectorstore is None:
                    continue
                # 每库多取一些，合并后再全局截断，避免各库配额失衡
                pairs = vectorstore.similarity_search_with_score(question, k=max(k, 5))
                for doc, distance in pairs:
                    cos = 1.0 - (float(distance) ** 2) / 2.0
                    if cos < min_cos:
                        continue
                    key = self._dedupe_key(doc)
                    if key in seen:
                        continue
                    seen.add(key)
                    # metadata 里补上来源库，便于前端/日志溯源
                    doc.metadata = {**(doc.metadata or {}), "kb": name}
                    scored.append((float(distance), doc))
            except Exception:
                # 单个索引损坏不应拖垮整次检索，但必须留痕
                logger.warning("知识库 %s 检索失败，已跳过", name, exc_info=True)
                continue

        scored.sort(key=lambda x: x[0])  # L2 距离升序 = 相似度降序
        return [doc for _, doc in scored[:k]]

    # ---------- 生成 ----------

    def _build_history_block(self, history: List[dict] | None) -> str:
        """把多轮历史压成 prompt 里的一段文本。

        此前历史消息全部存在 messages 表里却从未进入 prompt，导致「那它的价格
        呢？」这类指代性追问完全失效。这里按 token 预算截断：优先保留最近的
        轮次，单条过长则截断，整体超预算则从最旧开始丢弃。
        """
        if not history:
            return ""

        per_msg = settings.CHAT_HISTORY_MSG_CHARS
        budget = settings.CHAT_HISTORY_MAX_CHARS
        picked: List[str] = []
        used = 0

        # 从最新往旧回溯，凑满预算为止
        for item in reversed(history):
            role = "用户" if item.get("role") == "user" else "助手"
            content = (item.get("content") or "").strip().replace("\n", " ")
            if not content:
                continue
            if len(content) > per_msg:
                content = content[:per_msg] + "…"
            line = f"{role}：{content}"
            if used + len(line) > budget:
                break
            picked.append(line)
            used += len(line)

        if not picked:
            return ""
        picked.reverse()  # 恢复时间顺序
        return "\n".join(picked)

    async def astream_answer(
        self,
        question: str,
        context_docs: List[Document],
        history: List[dict] | None = None,
    ) -> AsyncGenerator[str, None]:
        """基于检索结果流式生成答案（真流式，逐 token 输出）

        history: [{"role": "user"|"assistant", "content": str}, ...]，按时间正序。
        """
        context = "\n\n".join(doc.page_content for doc in context_docs)
        if not context.strip():
            context = "（知识库暂无相关内容）"
        prompt_text = self.prompt_template.format(
            context=context,
            history=self._build_history_block(history),
            question=question,
        )
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
