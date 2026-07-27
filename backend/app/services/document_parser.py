import os
from typing import List, Optional
from pathlib import Path


def parse_pdf(file_path: str) -> str:
    try:
        import fitz  # PyMuPDF
        text = ""
        with fitz.open(file_path) as doc:
            for page in doc:
                text += page.get_text()
        return text
    except ImportError:
        raise ValueError("请安装 pymupdf: pip install pymupdf")


def parse_word(file_path: str) -> str:
    """解析 Word 文档；对非标准 docx（命名空间缺失等）自动降级为 XML 文本提取"""
    try:
        from docx import Document
        doc = Document(file_path)
        return "\n".join([para.text for para in doc.paragraphs])
    except ImportError:
        raise ValueError("请安装 python-docx: pip install python-docx")
    except Exception:
        # 容错路径：部分工具/WPS 生成的 docx 未声明 w: 命名空间，
        # python-docx 无法解析，但 <t> 文本节点完整，可直接提取
        import zipfile
        import re
        import html

        with zipfile.ZipFile(file_path) as z:
            xml = z.read("word/document.xml").decode("utf-8", errors="replace")
        paragraphs = []
        for p in re.findall(r"<p[ >].*?</p>", xml, re.S):
            texts = re.findall(r"<t[^>]*>(.*?)</t>", p, re.S)
            if texts:
                paragraphs.append("".join(texts))
        text = html.unescape("\n".join(paragraphs))
        if not text.strip():
            raise ValueError("docx 解析失败：无法提取文本内容")
        return text


def parse_txt(file_path: str) -> str:
    with open(file_path, "r", encoding="utf-8") as f:
        return f.read()


def parse_excel(file_path: str) -> str:
    try:
        import pandas as pd
        df = pd.read_excel(file_path)
        text_parts = []
        for _, row in df.iterrows():
            text_parts.append(" | ".join([f"{col}: {val}" for col, val in row.items()]))
        return "\n".join(text_parts)
    except ImportError:
        raise ValueError("请安装 pandas 和 openpyxl")


def parse_document(file_path: str, file_type: str) -> str:
    parsers = {
        "pdf": parse_pdf,
        "docx": parse_word,
        "txt": parse_txt,
        "md": parse_txt,
        "markdown": parse_txt,
        "xlsx": parse_excel,
        "xls": parse_excel
    }

    parser = parsers.get(file_type.lower())
    if not parser:
        raise ValueError(f"不支持的文件类型: {file_type}")

    return parser(file_path)


def save_uploaded_file(file, upload_dir: str) -> str:
    os.makedirs(upload_dir, exist_ok=True)
    file_path = os.path.join(upload_dir, file.filename)
    with open(file_path, "wb") as f:
        f.write(file.read())
    return file_path
