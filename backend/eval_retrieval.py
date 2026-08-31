# -*- coding: utf-8 -*-
"""检索质量评测：对示例商品知识库计算 Recall@k 与 MRR@k。

用法（在 backend 目录下）：
    python eval_retrieval.py --provider local
    python eval_retrieval.py --provider fastembed
    python eval_retrieval.py --provider openai --k 5

- 评测集：sample_data/eval_qa.jsonl（query + 期望命中的商品标题关键词）
- 语料：sample_data/ecommerce_products.txt，按 rag_engine.split_document 分块
- 指标：Recall@k（top-k 内至少命中一个期望商品的查询占比）、
        MRR@k（首个命中结果排名倒数的均值）
- 索引构建在临时目录，不触碰真实 db_data
"""
import argparse
import json
import os
import sys
import tempfile
from dataclasses import dataclass

from langchain_community.vectorstores import FAISS

from app.core.config import settings
from app.services.embeddings_factory import build_embeddings
from app.services.rag_service import rag_engine

CORPUS_PATH = os.path.join(os.path.dirname(__file__), "sample_data", "ecommerce_products.txt")
EVAL_PATH = os.path.join(os.path.dirname(__file__), "sample_data", "eval_qa.jsonl")


@dataclass
class Case:
    query: str
    expected: list


def load_cases() -> list:
    cases = []
    with open(EVAL_PATH, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                item = json.loads(line)
                cases.append(Case(query=item["query"], expected=item["expected"]))
    return cases


def chunk_titles(chunks: list) -> list:
    """每个分块的标题 = 首行（split_document 保证块首是 ## 标题或原文首行）"""
    return [chunk.split("\n", 1)[0] for chunk in chunks]


def hit_rank(title_line: str, expected: list) -> bool:
    return any(keyword in title_line for keyword in expected)


def evaluate(provider: str, k: int) -> dict:
    with open(CORPUS_PATH, encoding="utf-8") as f:
        text = f.read()
    chunks = rag_engine.split_document(text)
    titles = chunk_titles(chunks)

    # 本地哈希实现有全局单例预热，这里直接复用 rag_engine 的分块逻辑与工厂构建向量端
    settings.EMBEDDING_PROVIDER = provider
    embeddings = build_embeddings()

    tmp_dir = tempfile.mkdtemp(prefix=f"rag_eval_{provider}_")
    store = FAISS.from_texts(chunks, embeddings)
    store.save_local(tmp_dir)
    store = FAISS.load_local(tmp_dir, embeddings, allow_dangerous_deserialization=True)

    recalls, rr_sum = 0, 0.0
    details = []
    for case in load_cases():
        docs = store.similarity_search(case.query, k=k)
        rank = next(
            (i + 1 for i, doc in enumerate(docs) if hit_rank(titles[chunks.index(doc.page_content)], case.expected)),
            None,
        ) if docs else None
        hit = rank is not None
        recalls += 1 if hit else 0
        rr_sum += (1.0 / rank) if rank else 0.0
        details.append((case.query, rank))

    n = len(details)
    return {
        "provider": provider,
        "k": k,
        "recall_at_k": recalls / n,
        "mrr_at_k": rr_sum / n,
        "details": details,
        "total": n,
    }


def main():
    parser = argparse.ArgumentParser(description="RAG 检索质量评测")
    parser.add_argument("--provider", default="local", help="local / fastembed / openai")
    parser.add_argument("--k", type=int, default=5)
    args = parser.parse_args()

    result = evaluate(args.provider, args.k)
    print(f"\n===== 评测结果 provider={result['provider']} k={result['k']} =====")
    print(f"用例数: {result['total']}")
    print(f"Recall@{result['k']}: {result['recall_at_k']:.2%}")
    print(f"MRR@{result['k']}:   {result['mrr_at_k']:.3f}")
    print("---- 逐条 ----")
    for query, rank in result["details"]:
        flag = f"hit@{rank}" if rank else "miss"
        print(f"[{flag:>6}] {query}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
