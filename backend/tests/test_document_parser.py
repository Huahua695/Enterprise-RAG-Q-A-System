# -*- coding: utf-8 -*-
"""文档解析器测试：编码回退、docx 表格、扫描件 PDF、空块与 xls 依赖提示。

这几项此前都是"静默成功"或"必失败"的路径，缺乏覆盖。
"""
import io
import os

import pytest

from app.services import document_parser as dp


# ---------------------------------------------------------------- 编码回退

def test_parse_txt_reads_utf8(tmp_path):
    p = tmp_path / "a.txt"
    p.write_bytes("## 商品\n中文内容".encode("utf-8"))
    assert "中文内容" in dp.parse_txt(str(p))


def test_parse_txt_reads_gbk(tmp_path):
    """Windows 记事本另存的 GBK 文本，硬编码 utf-8 会 UnicodeDecodeError。"""
    p = tmp_path / "gbk.txt"
    p.write_bytes("## 商品\n中文内容测试".encode("gbk"))
    assert "中文内容测试" in dp.parse_txt(str(p))


def test_parse_txt_reads_gb18030_with_bom(tmp_path):
    p = tmp_path / "bom.txt"
    p.write_bytes(b"\xef\xbb\xbf" + "带 BOM 的中文".encode("utf-8"))
    text = dp.parse_txt(str(p))
    assert "带 BOM 的中文" in text
    assert not text.startswith("\ufeff"), "BOM 应被剥离"


def test_parse_txt_empty_file(tmp_path):
    p = tmp_path / "empty.txt"
    p.write_bytes(b"")
    assert dp.parse_txt(str(p)) == ""


def test_parse_txt_never_raises_on_binary(tmp_path):
    """二进制内容不应抛编码异常（latin-1 兜底），交由切块阶段判空。"""
    p = tmp_path / "bin.txt"
    p.write_bytes(bytes(range(256)))
    assert isinstance(dp.parse_txt(str(p)), str)


# ---------------------------------------------------------------- docx

def test_parse_word_includes_tables(tmp_path):
    """此前只遍历 paragraphs，Word 表格数据整块丢失。"""
    from docx import Document

    path = tmp_path / "t.docx"
    d = Document()
    d.add_paragraph("正文段落")
    table = d.add_table(rows=2, cols=2)
    table.cell(0, 0).text = "型号"
    table.cell(0, 1).text = "价格"
    table.cell(1, 0).text = "iPhone"
    table.cell(1, 1).text = "9999"
    d.save(str(path))

    text = dp.parse_word(str(path))
    assert "正文段落" in text
    assert "iPhone" in text, "表格内容必须被提取"
    assert "9999" in text


def test_parse_word_falls_back_for_nonstandard_docx(tmp_path):
    """命名空间异常的 docx：结构化解析失败时走 XML 文本提取。"""
    import zipfile

    path = tmp_path / "weird.docx"
    xml = (
        '<?xml version="1.0"?><document>'
        "<p><t>降级路径提取到的文本</t></p>"
        "</document>"
    )
    with zipfile.ZipFile(str(path), "w") as z:
        z.writestr("word/document.xml", xml)

    text = dp.parse_word(str(path))
    assert "降级路径提取到的文本" in text


# ---------------------------------------------------------------- PDF

def test_parse_pdf_raises_on_image_only_pdf(tmp_path):
    """扫描件 PDF 无文字层：必须显式报错，而不是返回空串当成功。"""
    import fitz

    path = tmp_path / "scan.pdf"
    doc = fitz.open()
    page = doc.new_page()
    # 只画一个矩形，不写任何文字
    page.draw_rect(fitz.Rect(50, 50, 200, 200), color=(0, 0, 0))
    doc.save(str(path))
    doc.close()

    with pytest.raises(ValueError, match="未提取到任何文本|扫描件"):
        dp.parse_pdf(str(path))


def test_parse_pdf_reads_text_layer(tmp_path):
    import fitz

    path = tmp_path / "ok.pdf"
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), "Hello RAG")
    doc.save(str(path))
    doc.close()

    assert "Hello RAG" in dp.parse_pdf(str(path))


# ---------------------------------------------------------------- Excel

def test_parse_excel_reads_all_sheets(tmp_path):
    """此前只读第一个 sheet，其余工作表内容丢失。"""
    import pandas as pd

    path = tmp_path / "t.xlsx"
    with pd.ExcelWriter(str(path)) as w:
        pd.DataFrame({"商品": ["iPhone"]}).to_excel(w, sheet_name="SheetA", index=False)
        pd.DataFrame({"商品": ["Mate 60"]}).to_excel(w, sheet_name="SheetB", index=False)

    text = dp.parse_excel(str(path))
    assert "iPhone" in text
    assert "Mate 60" in text, "多 sheet 必须都提取"
    assert "SheetB" in text


def test_parse_excel_empty_workbook_raises(tmp_path):
    import pandas as pd

    path = tmp_path / "empty.xlsx"
    pd.DataFrame().to_excel(str(path), index=False)
    with pytest.raises(ValueError, match="未提取到任何数据"):
        dp.parse_excel(str(path))


def test_parse_excel_xls_without_xlrd_gives_actionable_error(tmp_path, monkeypatch):
    """.xls 缺 xlrd 时应给出可操作提示，而不是 pandas 的晦涩报错。"""
    import builtins

    import pandas as pd

    path = tmp_path / "t.xls"
    path.write_bytes(b"\xd0\xcf\x11\xe0")  # 伪 OLE 头，够触发分支

    real_import = builtins.__import__

    def fake_import(name, *a, **kw):
        if name == "xlrd":
            raise ImportError("No module named 'xlrd'")
        return real_import(name, *a, **kw)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    with pytest.raises(ValueError, match="xlrd"):
        dp.parse_excel(str(path))


# ---------------------------------------------------------------- 分发

def test_parse_document_dispatch(tmp_path):
    p = tmp_path / "a.md"
    p.write_bytes("# 标题\n内容".encode("utf-8"))
    assert "内容" in dp.parse_document(str(p), "md")

    with pytest.raises(ValueError, match="不支持的文件类型"):
        dp.parse_document(str(p), "exe")
