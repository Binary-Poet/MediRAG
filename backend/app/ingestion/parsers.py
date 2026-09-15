"""多格式解析分发：字节 → 纯文本（方案 6.1 ingestion/parsers.py）。

格式族：
  纯文本族（txt/md/csv/tsv/json/xml/yaml/yml/log/html/rtf）→ 直接解码
  PDF → pypdf（逐页提取，页间以 \\f 分隔，供切片器识别页码）
  DOCX → python-docx（段落）    XLSX/XLS → openpyxl    PPTX/PPT → python-pptx
"""
import io
import json

PLAIN_EXTS = {"txt", "md", "csv", "tsv", "json", "xml", "yaml", "yml", "log", "html", "rtf"}
SUPPORTED_EXTS = PLAIN_EXTS | {"pdf", "docx", "xlsx", "xls", "pptx", "ppt", "doc"}


class ParseError(Exception):
    """解析失败或格式不支持。"""


def _decode(data: bytes) -> str:
    for enc in ("utf-8", "gb18030", "utf-16"):
        try:
            return data.decode(enc)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="replace")


def _parse_pdf(data: bytes) -> str:
    from pypdf import PdfReader

    reader = PdfReader(io.BytesIO(data))
    return "\f".join((page.extract_text() or "") for page in reader.pages)


def _parse_docx(data: bytes) -> str:
    from docx import Document as Docx

    doc = Docx(io.BytesIO(data))
    return "\n".join(p.text for p in doc.paragraphs if p.text.strip())


def _parse_xlsx(data: bytes) -> str:
    from openpyxl import load_workbook

    wb = load_workbook(io.BytesIO(data), read_only=True, data_only=True)
    lines = []
    for ws in wb.worksheets:
        lines.append(f"## {ws.title}")
        for row in ws.iter_rows(values_only=True):
            cells = [str(c) for c in row if c is not None]
            if cells:
                lines.append(" | ".join(cells))
    return "\n".join(lines)


def _parse_pptx(data: bytes) -> str:
    from pptx import Presentation

    prs = Presentation(io.BytesIO(data))
    lines = []
    for i, slide in enumerate(prs.slides, start=1):
        lines.append(f"## 第 {i} 页")
        for shape in slide.shapes:
            if shape.has_text_frame and shape.text_frame.text.strip():
                lines.append(shape.text_frame.text)
    return "\n".join(lines)


def parse_document(data: bytes, ext: str) -> str:
    """按扩展名解析为纯文本。不支持/失败抛 ParseError。"""
    ext = ext.lower().lstrip(".")
    if ext not in SUPPORTED_EXTS:
        raise ParseError(f"不支持的格式：{ext}")
    try:
        if ext == "pdf":
            return _parse_pdf(data)
        if ext == "docx":
            return _parse_docx(data)
        if ext in ("xlsx", "xls"):
            return _parse_xlsx(data)
        if ext in ("pptx", "ppt"):
            return _parse_pptx(data)
        if ext == "doc":
            raise ParseError("老版 .doc 二进制格式不支持，请另存为 .docx 后上传")
        if ext == "rtf":
            return _decode(data)          # RTF 为文本标记格式，直接解码
        text = _decode(data)
        if ext == "json":
            try:
                text = json.dumps(json.loads(text), ensure_ascii=False, indent=2)
            except json.JSONDecodeError:
                pass  # 非合法 JSON 按原文返回
        return text
    except ParseError:
        raise
    except Exception as e:  # 解析器的任何内部错误统一归类
        raise ParseError(f"{ext} 解析失败：{e}") from e