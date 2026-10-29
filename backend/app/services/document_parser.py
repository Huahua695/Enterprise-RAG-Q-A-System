import os
from typing import List, Optional
from pathlib import Path


def parse_pdf(file_path: str) -> str:
    try:
        import fitz  # PyMuPDF
        text = ""
        with fitz.open(file_path) as doc:
            page_count = doc.page_count
            for page in doc:
                text += page.get_text()
    except ImportError:
        raise ValueError("请安装 pymupdf: pip install pymupdf")

    # 扫描版（图片型）PDF 提取不到文字层，此前会返回空串并被当作成功入索引，
    # 结果是 chunk_count=0 却状态 completed——用户完全无感知。这里显式报错。
    if not text.strip():
        raise ValueError(
            f"PDF 未提取到任何文本（共 {page_count} 页），可能是扫描件或纯图片 PDF。"
            "当前不支持 OCR，请改用带文字层的 PDF 或先做 OCR。"
        )
    return text


def parse_word(file_path: str) -> str:
    """解析 Word 文档；对非标准 docx（命名空间缺失等）自动降级为 XML 文本提取"""
    try:
        from docx import Document
        doc = Document(file_path)
        parts = [para.text for para in doc.paragraphs]

        # 表格数据此前整块丢失（doc.paragraphs 不包含表格）。
        # 转成 CSV 风格的行，保持"列名: 值"的可检索形态。
        for table in doc.tables:
            for row in table.rows:
                cells = [cell.text.strip().replace("\n", " ") for cell in row.cells]
                if any(cells):
                    parts.append(" | ".join(cells))

        text = "\n".join(p for p in parts if p is not None)
        if text.strip():
            return text
        # 走降级路径：可能是命名空间异常的 docx
        raise _FallbackToXml()
    except ImportError:
        raise ValueError("请安装 python-docx: pip install python-docx")
    except _FallbackToXml:
        pass
    except Exception:
        pass

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


class _FallbackToXml(Exception):
    """内部信号：结构化解析没拿到文本，转 XML 降级路径。"""


# 常见中文文本编码，按优先级尝试。
# Windows 记事本另存的 GBK/GB18030 文本用 utf-8 硬读会 UnicodeDecodeError。
_TEXT_ENCODINGS = ("utf-8-sig", "utf-8", "gb18030", "gbk", "big5", "latin-1")


def _read_text_with_fallback(file_path: str) -> str:
    raw = Path(file_path).read_bytes()
    if not raw:
        return ""

    # 先按 BOM / 常见编码逐个严格解码；latin-1 兜底保证不抛异常
    for enc in _TEXT_ENCODINGS:
        try:
            text = raw.decode(enc)
        except (UnicodeDecodeError, LookupError):
            continue
        # 极少数情况下 gb18030 能解出乱码但无异常，交给 charset 探测交叉确认
        return text

    # 理论不可达（latin-1 不会失败），保留以防编码表被改
    from charset_normalizer import from_bytes

    best = from_bytes(raw).best()
    return str(best) if best else raw.decode("utf-8", errors="replace")


def parse_txt(file_path: str) -> str:
    return _read_text_with_fallback(file_path)


def parse_excel(file_path: str) -> str:
    try:
        import pandas as pd
    except ImportError:
        raise ValueError("请安装 pandas 和 openpyxl")

    path = Path(file_path)
    if path.suffix.lower() == ".xls":
        # pandas 读老版 .xls 依赖 xlrd（2.x 只支持 .xls，需 >=2.0）
        try:
            import xlrd  # noqa: F401
        except ImportError:
            raise ValueError(
                "读取 .xls 需要 xlrd：请执行 pip install 'xlrd>=2.0.1'，"
                "或将该文件另存为 .xlsx 后重新上传。"
            )

    # 多 sheet 一并提取，避免只读到第一个工作表导致内容缺失
    try:
        sheets = pd.read_excel(file_path, sheet_name=None)
    except Exception as e:
        raise ValueError(f"Excel 解析失败：{e}")

    text_parts: List[str] = []
    for sheet_name, df in sheets.items():
        if df is None or df.empty:
            continue
        text_parts.append(f"## 工作表：{sheet_name}")
        for _, row in df.iterrows():
            pairs = [f"{col}: {val}" for col, val in row.items() if pd.notna(val)]
            if pairs:
                text_parts.append(" | ".join(pairs))

    text = "\n".join(text_parts)
    if not text.strip():
        raise ValueError("Excel 未提取到任何数据（所有工作表为空）")
    return text


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
