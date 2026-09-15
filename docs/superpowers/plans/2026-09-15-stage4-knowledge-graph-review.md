# 阶段 4：知识库管理 + 图谱审核闭环 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让知识真正"进得来、审得过、查得到"——多格式文档上传后异步入库（解析→切片→向量化→可检索），LLM 从文档抽取实体关系三元组进入候选区，人工审核发布后才进入问答图谱，前端上线典籍知识库页与本草图谱页（含候选审核）。

**Architecture:** MySQL（SQLAlchemy 2 + pymysql）存文档元数据与状态机（上传中/处理中/就绪/失败）；上传走 multipart + FastAPI BackgroundTasks 异步入库，前端轮询状态；解析器按扩展名分发（纯文本族 decode / pypdf / python-docx / openpyxl / python-pptx），切片沿用"带元数据切片"策略写入既有 LocalVectorStore 并重建 BM25 索引；图谱侧 LLM 抽取三元组写入 Neo4j 标 `status='候选'`，审核 API 改成 `'已发布'`（问答链路只查已发布，既有查询不变）；前端典籍知识库页（P0-6）与本草图谱页（P0-5，ECharts force 图 + 候选审核 Tab）按《前端还原规格.md》实现。

**Tech Stack:** Python 3.12、FastAPI（multipart/BackgroundTasks）、SQLAlchemy 2、pymysql、pypdf、python-docx、openpyxl、python-pptx、Neo4j driver、Vue 3 + Element Plus + ECharts。

**Spec:** `docs/MediRAG-合并改造方案.md`（6.1 目录结构、6.5 候选审核闭环、6.6 MySQL 核心表、第八节 API 清单、阶段 4 段落）+ `docs/前端还原规格.md`（P0-5 本草图谱、P0-6 典籍知识库）。

## Global Constraints

- **测试不得依赖真实网络 / MySQL / Neo4j / LLM**：数据库测试用 `sqlite:///:memory:`（注入 `DATABASE_URL`），LLM 与图谱用 monkeypatch 注入 fake，解析器测试用内存构造的样本字节。
- **上传限制（规格 P0-6 逐字）**：单文件 ≤ 100MB；知识主题**必选**，枚举 8 类：`内科 / 外科 / 儿科 / 妇科 / 情志脑病 / 筋骨伤科 / 皮肤病证 / 五官病证`；支持格式：`PDF/DOC/DOCX/RTF/PPT/PPTX、XLS/XLSX/CSV/TSV、TXT/MD/HTML/JSON/XML/YAML/LOG`。
- **文档状态机**：`上传中 → 处理中 → 就绪 / 失败`（规格 P0-6 与方案 6.6）。
- **图谱审核闭环（方案 6.5）**：LLM 抽取的三元组一律 `status='候选'`；人工审核后改 `'已发布'`；**问答链路只查 `已发布`**（`neo4j_client` 现有过滤不变，禁止放开）。
- **切片唯一性与可追溯**：上传文档切片 `chunk_id = f"{doc_name}#{seq:04d}"`（与 seed 语料的 `中药方剂学基础#0001` 格式同族），必须带 `doc_name/chapter/page_no/topic` 四元数据。
- **BM25 索引刷新**：入库完成后必须重建关键词索引（新增 `rebuild_keyword_index()`），否则新文档无法被关键词路召回。
- 前端设计 token 一律取 `web/src/styles/theme.ts`；文案以《前端还原规格.md》为准，不得自造。
- 既有约束延续：`.env` 不入库；`data/uploads/` 与 `data/vectorstore/` 属运行数据，本轮将 `data/uploads/` 加入 `.gitignore`。
- MySQL 容器：`docker compose -f deploy/docker-compose.yml up -d mysql`（宿主端口 **3307**，库 `medirag`，`mysql+pymysql://medirag:medirag123@localhost:3307/medirag` 已配在 `config.py:mysql_dsn`）。

## 文件结构

| 文件 | 责任 |
|---|---|
| `backend/app/db.py`（新建） | SQLAlchemy 引擎/Session/Base/init_db（`DATABASE_URL` 可注入） |
| `backend/app/models/__init__.py`、`document.py`（新建） | `Document` ORM（文档元数据 + 状态机） |
| `backend/app/ingestion/parsers.py`（新建） | 按扩展名分发解析 → 纯文本 |
| `backend/app/ingestion/splitter.py`（新建） | 文本 → 带元数据切片 |
| `backend/app/ingestion/pipeline.py`（修改） | 既有 seed 入库保留；新增 `ingest_document(document_id)` 异步流水线 |
| `backend/app/retrieval/keyword.py`（修改） | 新增 `rebuild_keyword_index()` |
| `backend/app/api/documents.py`（新建） | 上传/列表/状态轮询/删除 |
| `backend/app/agent/prompts/entity_extract.txt`（新建） | 三元组抽取 Prompt |
| `backend/app/graph/extractor.py`（新建） | LLM 抽取三元组 + 写入候选 |
| `backend/app/api/graph_api.py`（新建） | 图谱搜索/邻居/详情 + 候选审核 |
| `backend/app/main.py`（修改） | 挂载新路由 + `init_db()` |
| `backend/requirements.txt`（修改） | +sqlalchemy +pymysql +python-multipart +pypdf +python-docx +openpyxl +python-pptx |
| `web/src/api/documents.ts`、`graph.ts`（新建） | 前端 API 封装 |
| `web/src/types/knowledge.ts`、`graph.ts`（新建） | 前端类型 |
| `web/src/views/knowledge/Library.vue`、`UploadDialog.vue`（新建） | 典籍知识库页（P0-6） |
| `web/src/views/graph/GraphExplore.vue`、`CandidateReview.vue`（新建） | 本草图谱页（P0-5） |
| `web/src/router/index.ts`（修改） | graph/library 路由指向真实页面 |

---

### Task 1: 依赖 + MySQL 接入 + Document 模型

**Files:**
- Modify: `backend/requirements.txt`
- Create: `backend/app/db.py`、`backend/app/models/__init__.py`、`backend/app/models/document.py`
- Modify: `backend/app/config.py`
- Modify: `.gitignore`
- Test: `backend/tests/test_db.py`

**Interfaces:**
- Produces: `db.get_engine()`、`db.session_scope()`（上下文管理器，提交/回滚）、`db.init_db()`、`db.Base`；`models.document.Document`（字段 `id/name/file_type/size/topic/status/chunk_count/error_message/stored_path/uploaded_at`）；`settings.sqlalchemy_url`（`DATABASE_URL` 优先，回落 `mysql_dsn`）。

- [ ] **Step 1: 追加依赖与配置**

`backend/requirements.txt` 在 `langchain-core` 行后追加：

```
# 阶段 4：知识库管理 + 图谱审核
sqlalchemy>=2.0,<3
pymysql>=1.1,<2
python-multipart>=0.0.9
pypdf>=4.0,<6
python-docx>=1.1,<2
openpyxl>=3.1,<4
python-pptx>=0.6.23,<2
```

安装：`cd backend && .venv/Scripts/python -m pip install sqlalchemy pymysql python-multipart pypdf python-docx openpyxl python-pptx`

`backend/app/config.py` 的 MySQL 区块后追加：

```python
    # ===== 业务库（阶段 4：文档元数据/状态机；测试用 sqlite 注入覆盖）=====
    database_url: str = ""
```

并在 `Settings` 类内定义属性方法（放在字段区之后、`@lru_cache` 之前）：

```python
    @property
    def sqlalchemy_url(self) -> str:
        """业务库 DSN：DATABASE_URL 优先，缺省回落 MySQL DSN（阶段 2 已配）。"""
        return self.database_url or self.mysql_dsn
```

`.gitignore` 追加：

```
# 上传的原始文档（运行数据）
data/uploads/
```

- [ ] **Step 2: 写失败测试** `backend/tests/test_db.py`

```python
"""业务库接入测试：SQLite 内存库建表 + Document CRUD，不连 MySQL。"""
from datetime import datetime

import app.db as dbmod
from app.models.document import Document


def _sqlite_engine(monkeypatch):
    monkeypatch.setattr(dbmod, "get_engine", lambda: dbmod._make_engine("sqlite:///:memory:"))
    engine = dbmod.get_engine()
    dbmod.Base.metadata.create_all(engine)
    return engine


def test_create_table_and_insert_document(monkeypatch):
    engine = _sqlite_engine(monkeypatch)

    with dbmod.session_scope(engine) as s:
        doc = Document(name="伤寒论.pdf", file_type="pdf", size=1024,
                       topic="内科", status="上传中", chunk_count=0)
        s.add(doc)
        s.flush()
        doc_id = doc.id

    with dbmod.session_scope(engine) as s:
        got = s.get(Document, doc_id)
        assert got.name == "伤寒论.pdf"
        assert got.status == "上传中"
        assert got.chunk_count == 0
        assert isinstance(got.uploaded_at, datetime)


def test_update_status_and_chunk_count(monkeypatch):
    engine = _sqlite_engine(monkeypatch)
    with dbmod.session_scope(engine) as s:
        doc = Document(name="a.md", file_type="md", size=10, topic="内科", status="上传中")
        s.add(doc)
        s.flush()
        doc_id = doc.id

    with dbmod.session_scope(engine) as s:
        doc = s.get(Document, doc_id)
        doc.status = "就绪"
        doc.chunk_count = 7

    with dbmod.session_scope(engine) as s:
        got = s.get(Document, doc_id)
        assert (got.status, got.chunk_count) == ("就绪", 7)


def test_sqlalchemy_url_falls_back_to_mysql_dsn(monkeypatch):
    from app.config import Settings

    s = Settings(database_url="", mysql_dsn="mysql+pymysql://u:p@h:3307/d")
    assert s.sqlalchemy_url == "mysql+pymysql://u:p@h:3307/d"
    s2 = Settings(database_url="sqlite:///:memory:")
    assert s2.sqlalchemy_url == "sqlite:///:memory:"
```

- [ ] **Step 3: 运行确认失败**

Run: `cd backend && .venv/Scripts/python -m pytest tests/test_db.py -v`
Expected: FAIL（`ModuleNotFoundError: app.db`）

- [ ] **Step 4: 实现**

`backend/app/db.py`：

```python
"""业务库接入：SQLAlchemy 2 引擎 / Session / Base。

生产用 MySQL（config.sqlalchemy_url）；测试注入 sqlite:///:memory:。
"""
from contextlib import contextmanager

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import get_settings


class Base(DeclarativeBase):
    pass


def _make_engine(url: str):
    kwargs = {"echo": False, "future": True}
    if url.startswith("sqlite"):
        kwargs["connect_args"] = {"check_same_thread": False}
    return create_engine(url, **kwargs)


def get_engine():
    """进程级引擎（按 sqlalchemy_url 创建一次）。"""
    global _engine
    if _engine is None:
        _engine = _make_engine(get_settings().sqlalchemy_url)
    return _engine


_engine = None


@contextmanager
def session_scope(engine=None):
    """事务作用域：正常提交，异常回滚。"""
    maker = sessionmaker(bind=engine or get_engine(), expire_on_commit=False)
    session: Session = maker()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def init_db(engine=None) -> None:
    """建表（幂等）。应用启动时调用。"""
    from app.models import document  # noqa: F401  确保模型注册到 Base

    Base.metadata.create_all(engine or get_engine())
```

`backend/app/models/__init__.py`：空文件。

`backend/app/models/document.py`：

```python
"""Document：知识库文档元数据与入库状态机（方案 6.6）。"""
from datetime import datetime

from sqlalchemy import DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class Document(Base):
    __tablename__ = "document"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255), index=True)
    file_type: Mapped[str] = mapped_column(String(16))
    size: Mapped[int] = mapped_column(Integer, default=0)
    topic: Mapped[str] = mapped_column(String(32), index=True)
    status: Mapped[str] = mapped_column(String(16), default="上传中", index=True)
    chunk_count: Mapped[int] = mapped_column(Integer, default=0)
    error_message: Mapped[str] = mapped_column(Text, default="")
    stored_path: Mapped[str] = mapped_column(String(512), default="")
    uploaded_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
```

- [ ] **Step 5: 运行确认通过**

Run: `cd backend && .venv/Scripts/python -m pytest tests/test_db.py -v`
Expected: PASS（3 passed）

- [ ] **Step 6: 建表并提交**

```bash
cd backend && .venv/Scripts/python -c "from app.db import init_db; init_db(); print('tables created')"
cd .. && git add backend/requirements.txt backend/app/config.py backend/app/db.py backend/app/models/__init__.py backend/app/models/document.py backend/tests/test_db.py .gitignore
git commit -m "feat(db): SQLAlchemy business store with Document status machine"
```

---

### Task 2: 多格式解析器

**Files:**
- Create: `backend/app/ingestion/parsers.py`
- Test: `backend/tests/test_parsers.py`

**Interfaces:**
- Produces: `SUPPORTED_EXTS: set[str]`；`parse_document(data: bytes, ext: str) -> str`（返回纯文本；不支持/解析失败抛 `ParseError`）。PDF 提取保留页边界 `\f`，供切片器识别页码。

- [ ] **Step 1: 写失败测试** `backend/tests/test_parsers.py`

```python
"""多格式解析测试：内存构造样本，不读真实磁盘文件。"""
import io
import json

import pytest

from app.ingestion.parsers import SUPPORTED_EXTS, ParseError, parse_document


def _docx_bytes() -> bytes:
    from docx import Document as Docx
    d = Docx()
    d.add_paragraph("四君子汤由人参、白术、茯苓、炙甘草组成。")
    buf = io.BytesIO()
    d.save(buf)
    return buf.getvalue()


def _xlsx_bytes() -> bytes:
    from openpyxl import Workbook
    wb = Workbook()
    ws = wb.active
    ws.append(["方剂", "组成"])
    ws.append(["四君子汤", "人参、白术"])
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _pptx_bytes() -> bytes:
    from pptx import Presentation
    prs = Presentation()
    slide = prs.slides.add_slide(prs.slide_layouts[5])
    slide.shapes.title.text = "脾气虚证候要点"
    buf = io.BytesIO()
    prs.save(buf)
    return buf.getvalue()


def _pdf_bytes() -> bytes:
    """最小可用 PDF（手写单页对象结构，含文本流）。"""
    content = b"BT /F1 12 Tf 72 720 Td (Sijunzi Tang) Tj ET"
    objs = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>",
        b"<< /Length " + str(len(content)).encode() + b" >>\nstream\n" + content + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for i, body in enumerate(objs, start=1):
        offsets.append(len(out))
        out += f"{i} 0 obj\n".encode() + body + b"\nendobj\n"
    xref_pos = len(out)
    out += f"xref\n0 {len(objs) + 1}\n".encode()
    out += b"0000000000 65535 f \n"
    for off in offsets:
        out += f"{off:010d} 00000 n \n".encode()
    out += b"trailer\n<< /Size " + str(len(objs) + 1).encode() + b" /Root 1 0 R >>\n"
    out += b"startxref\n" + str(xref_pos).encode() + b"\n%%EOF\n"
    return bytes(out)


@pytest.mark.parametrize("ext", ["txt", "md", "csv", "tsv", "json", "xml", "yaml", "yml", "log", "html"])
def test_plain_text_family(ext):
    text = parse_document("人参大补元气。".encode("utf-8"), ext)
    assert "人参" in text


def test_json_is_pretty_printed():
    raw = json.dumps({"方剂": "四君子汤"}, ensure_ascii=False).encode("utf-8")
    assert "四君子汤" in parse_document(raw, "json")


def test_docx_extraction():
    assert "四君子汤" in parse_document(_docx_bytes(), "docx")


def test_xlsx_extraction():
    text = parse_document(_xlsx_bytes(), "xlsx")
    assert "方剂" in text and "四君子汤" in text


def test_pptx_extraction():
    assert "脾气虚" in parse_document(_pptx_bytes(), "pptx")


def test_pdf_extraction():
    assert "Sijunzi" in parse_document(_pdf_bytes(), "pdf")


def test_unsupported_ext_raises():
    with pytest.raises(ParseError):
        parse_document(b"x", "exe")


def test_supported_exts_cover_spec_list():
    spec = {"pdf", "doc", "docx", "rtf", "ppt", "pptx", "xls", "xlsx", "csv", "tsv",
            "txt", "md", "html", "json", "xml", "yaml", "log"}
    assert spec <= SUPPORTED_EXTS
```

- [ ] **Step 2: 运行确认失败**

Run: `cd backend && .venv/Scripts/python -m pytest tests/test_parsers.py -v`
Expected: FAIL（`ModuleNotFoundError: app.ingestion.parsers`）

- [ ] **Step 3: 实现** `backend/app/ingestion/parsers.py`

```python
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
        if ext in ("doc", "rtf"):
            # 老格式二进制脆弱，尽力提取可见文本；失败由调用方落"失败"状态
            text = _decode(data)
            return text if text.isprintable() or "\n" in text else _decode(data)
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
```

- [ ] **Step 4: 运行确认通过**

Run: `cd backend && .venv/Scripts/python -m pytest tests/test_parsers.py -v`
Expected: PASS（17 passed：10 参数化 + 7 专项）

- [ ] **Step 5: Commit**

```bash
git add backend/app/ingestion/parsers.py backend/tests/test_parsers.py
git commit -m "feat(ingestion): multi-format document parser dispatch"
```

---

### Task 3: 切片器（带元数据）

**Files:**
- Create: `backend/app/ingestion/splitter.py`
- Test: `backend/tests/test_splitter.py`

**Interfaces:**
- Produces: `split_text(text, doc_name, topic, base_seq=0) -> list[dict]`，每片含 `chunk_id/title/doc_name/chapter/page_no/topic/text`（chunk_id = `f"{doc_name}#{seq:04d}"`，seq 自 base_seq 递增；PDF 的 `\f` 翻页推进 page_no；其余 page_no 为块序号）。

- [ ] **Step 1: 写失败测试** `backend/tests/test_splitter.py`

```python
"""切片器测试：元数据完整性、chunk_id 唯一、PDF 页码推进。"""
from app.ingestion.splitter import MAX_CHUNK_CHARS, split_text


def test_plain_text_split_with_metadata():
    chunks = split_text("四君子汤组成。\n\n归脾汤组成。" , doc_name="内科讲义.md", topic="内科")
    assert len(chunks) == 1                      # 两段合并未超长
    c = chunks[0]
    assert c["chunk_id"] == "内科讲义.md#0000"
    assert c["doc_name"] == "内科讲义.md"
    assert c["topic"] == "内科"
    assert c["page_no"] == 1
    assert "四君子汤" in c["text"]


def test_long_text_splits_into_multiple_chunks_with_unique_ids():
    para = "人参大补元气补脾益肺。"
    text = "\n\n".join([para] * 200)
    chunks = split_text(text, doc_name="中药学.md", topic="内科")
    assert len(chunks) > 1
    ids = [c["chunk_id"] for c in chunks]
    assert len(ids) == len(set(ids))             # 唯一
    assert all(len(c["text"]) <= MAX_CHUNK_CHARS + 50 for c in chunks)
    assert [c["page_no"] for c in chunks] == list(range(1, len(chunks) + 1))


def test_pdf_page_marker_advances_page_no():
    text = "第一页内容。\f第二页内容。"
    chunks = split_text(text, doc_name="伤寒论.pdf", topic="内科")
    pages = {c["page_no"] for c in chunks}
    assert pages == {1, 2}
    assert any("第二页" in c["text"] and c["page_no"] == 2 for c in chunks)


def test_base_seq_offsets_chunk_id():
    chunks = split_text("内容。", doc_name="x.md", topic="内科", base_seq=7)
    assert chunks[0]["chunk_id"] == "x.md#0007"


def test_blank_text_returns_empty():
    assert split_text("   \n  ", doc_name="x.md", topic="内科") == []
```

- [ ] **Step 2: 运行确认失败**

Run: `cd backend && .venv/Scripts/python -m pytest tests/test_splitter.py -v`
Expected: FAIL（ModuleNotFoundError）

- [ ] **Step 3: 实现** `backend/app/ingestion/splitter.py`

```python
"""切片器：纯文本 → 带元数据切片（方案 6.1 splitter.py）。

策略：按"页（\\f）"分割；页内按行累积到 ~MAX_CHUNK_CHARS 字符切一片（空行保留为
段落分隔，不作为强制切点）；每片带 doc_name/chapter/page_no/topic 元数据。
page_no 语义：有分页符时=PDF 页号；无分页符时=页内块序号（1 起，来源可追溯）。
"""
MAX_CHUNK_CHARS = 500


def split_text(text: str, doc_name: str, topic: str, base_seq: int = 0) -> list[dict]:
    """返回 [{'chunk_id','title','doc_name','chapter','page_no','topic','text'}, ...]。"""
    chunks: list[dict] = []
    seq = base_seq
    pages = text.split("\f")
    multi_page = len(pages) > 1

    for page_no, page in enumerate(pages, start=1):
        buf: list[str] = []
        size = 0

        def flush() -> None:
            nonlocal seq, buf, size
            body = "\n".join(buf).strip()
            if not body:
                buf, size = [], 0
                return
            chunks.append({
                "chunk_id": f"{doc_name}#{seq:04d}",
                "title": f"{doc_name} 切片 {seq + 1}",
                "doc_name": doc_name,
                "chapter": f"第 {page_no} 页",
                "page_no": page_no if multi_page else (seq - base_seq + 1),
                "topic": topic,
                "text": body,
            })
            seq += 1
            buf, size = [], 0

        for raw in page.split("\n"):
            line = raw.rstrip()
            if not line.strip():
                buf.append("")                      # 空行保留段落分隔，不触发切分
                continue
            if size + len(line) > MAX_CHUNK_CHARS and buf:
                flush()
            buf.append(line)
            size += len(line)
        flush()
    return chunks
```

- [ ] **Step 4: 运行确认通过**

Run: `cd backend && .venv/Scripts/python -m pytest tests/test_splitter.py -v`
Expected: PASS（5 passed）

- [ ] **Step 5: Commit**

```bash
git add backend/app/ingestion/splitter.py backend/tests/test_splitter.py
git commit -m "feat(ingestion): metadata-carrying text splitter"
```

---

### Task 4: 入库流水线 + BM25 索引刷新

**Files:**
- Modify: `backend/app/retrieval/keyword.py`（追加 `rebuild_keyword_index`）
- Modify: `backend/app/ingestion/pipeline.py`（追加 `ingest_document`）
- Test: `backend/tests/test_ingest_document.py`

**Interfaces:**
- Consumes: `parsers.parse_document`、`splitter.split_text`、`db.session_scope`、`models.Document`、`get_store()`、`embed_texts`、`get_keyword_index()`。
- Produces: `keyword.rebuild_keyword_index()`；`pipeline.ingest_document(document_id: int) -> dict`（读 DB → 解析 → 切片 → 向量化 → upsert+save → BM25 重建 → 状态流转；异常捕获后置 `失败` 并写 `error_message`）。

- [ ] **Step 1: 写失败测试** `backend/tests/test_ingest_document.py`

```python
"""异步入库流水线测试：SQLite + 内存向量库 + monkeypatch 向量化，无网络。"""
import app.db as dbmod
import app.ingestion.pipeline as pmod
import app.retrieval.keyword as kmod
from app.db import Base, _make_engine, session_scope
from app.models.document import Document
from app.retrieval.vector_store import LocalVectorStore


def _setup(monkeypatch, tmp_path):
    engine = _make_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    store = LocalVectorStore(str(tmp_path / "idx.json"))
    monkeypatch.setattr(dbmod, "_engine", engine)      # 所有 session_scope() 走测试库
    monkeypatch.setattr(pmod, "get_store", lambda: store)
    monkeypatch.setattr(pmod, "embed_texts", lambda texts: [[float(len(t)), 1.0] for t in texts])
    return engine, store


def test_ingest_marks_ready_and_writes_chunks(monkeypatch, tmp_path):
    engine, store = _setup(monkeypatch, tmp_path)
    src = tmp_path / "内科讲义.md"
    src.write_text("四君子汤由人参、白术、茯苓、炙甘草组成。", encoding="utf-8")

    with session_scope(engine) as s:
        doc = Document(name="内科讲义.md", file_type="md", size=src.stat().st_size,
                       topic="内科", status="上传中", stored_path=str(src))
        s.add(doc)
        s.flush()
        doc_id = doc.id

    stats = pmod.ingest_document(doc_id)

    assert stats["chunks"] >= 1
    with session_scope(engine) as s:
        got = s.get(Document, doc_id)
        assert got.status == "就绪"
        assert got.chunk_count == stats["chunks"]
    assert len(store) >= 1
    assert any("四君子汤" in c["text"] for c in store.chunks)


def test_ingest_marks_failed_on_parse_error(monkeypatch, tmp_path):
    engine, _ = _setup(monkeypatch, tmp_path)
    src = tmp_path / "坏文件.exe"
    src.write_bytes(b"\x00\x01")

    with session_scope(engine) as s:
        doc = Document(name="坏文件.exe", file_type="exe", size=2, topic="内科",
                       status="上传中", stored_path=str(src))
        s.add(doc)
        s.flush()
        doc_id = doc.id

    stats = pmod.ingest_document(doc_id)

    assert stats["chunks"] == 0
    with session_scope(engine) as s:
        got = s.get(Document, doc_id)
        assert got.status == "失败"
        assert "不支持" in got.error_message


def test_ingest_rebuilds_keyword_index(monkeypatch, tmp_path):
    engine, store = _setup(monkeypatch, tmp_path)
    called = {"n": 0}
    monkeypatch.setattr(pmod, "rebuild_keyword_index",
                        lambda: called.__setitem__("n", called["n"] + 1))
    src = tmp_path / "a.md"
    src.write_text("脾气虚常见便溏倦怠。", encoding="utf-8")
    with session_scope(engine) as s:
        doc = Document(name="a.md", file_type="md", size=10, topic="内科",
                       status="上传中", stored_path=str(src))
        s.add(doc)
        s.flush()
        doc_id = doc.id

    pmod.ingest_document(doc_id)
    assert called["n"] == 1


def test_rebuild_keyword_index_rebuilds_from_store(monkeypatch, tmp_path):
    store = LocalVectorStore(str(tmp_path / "idx.json"))
    store.upsert([{"chunk_id": "a#0000", "title": "四君子汤", "text": "人参白术茯苓炙甘草",
                   "doc_name": "a.md", "chapter": "第 1 页", "page_no": 1, "topic": "内科",
                   "embedding": [1.0, 0.0]}])
    monkeypatch.setattr(kmod, "get_store", lambda: store)
    kmod.rebuild_keyword_index()
    hits = kmod.get_keyword_index().search("四君子汤", top_k=5)
    assert hits and hits[0]["chunk_id"] == "a#0000"
```

- [ ] **Step 2: 运行确认失败**

Run: `cd backend && .venv/Scripts/python -m pytest tests/test_ingest_document.py -v`
Expected: FAIL（`ImportError: cannot import name 'rebuild_keyword_index'` 或 AttributeError）

- [ ] **Step 3: 实现**

`backend/app/retrieval/keyword.py` 末尾追加：

```python
def rebuild_keyword_index() -> int:
    """按当前向量库语料重建关键词索引（入库/删除文档后调用）。返回切片数。"""
    global _index
    _index = KeywordIndex()
    return _index.build(get_store().chunks)
```

`backend/app/ingestion/pipeline.py` 末尾追加（顶部补 import）：

```python
from app.db import session_scope
from app.models.document import Document

from app.ingestion.parsers import ParseError, parse_document
from app.ingestion.splitter import split_text
from app.retrieval.keyword import rebuild_keyword_index


def ingest_document(document_id: int) -> dict:
    """单文档入库流水线：解析 → 切片 → 向量化 → 入库 → BM25 重建 → 状态流转。

    由上传接口以 BackgroundTasks 异步调用；任何异常都会把文档置为"失败"。
    """
    with session_scope() as s:
        doc = s.get(Document, document_id)
        if doc is None:
            return {"chunks": 0, "error": "document not found"}
        doc.status = "处理中"
        stored_path, name, file_type, topic = doc.stored_path, doc.name, doc.file_type, doc.topic

    try:
        data = Path(stored_path).read_bytes()
        text = parse_document(data, file_type)
        chunks = split_text(text, doc_name=name, topic=topic)
        if not chunks:
            raise ParseError("解析结果为空（无可入库文本）")
        embeddings = embed_texts([f"{c['title']}：{c['text']}" for c in chunks])
        items = [{**c, "embedding": e} for c, e in zip(chunks, embeddings)]
        store = get_store()
        store.upsert(items)
        store.save()
        rebuild_keyword_index()
        with session_scope() as s:
            doc = s.get(Document, document_id)
            doc.status = "就绪"
            doc.chunk_count = len(chunks)
            doc.error_message = ""
        return {"chunks": len(chunks)}
    except Exception as e:
        with session_scope() as s:
            doc = s.get(Document, document_id)
            doc.status = "失败"
            doc.error_message = str(e)[:500]
        return {"chunks": 0, "error": str(e)}
```

- [ ] **Step 4: 运行确认通过**

Run: `cd backend && .venv/Scripts/python -m pytest tests/test_ingest_document.py -v`
Expected: PASS（4 passed）

- [ ] **Step 5: Commit**

```bash
git add backend/app/retrieval/keyword.py backend/app/ingestion/pipeline.py backend/tests/test_ingest_document.py
git commit -m "feat(ingestion): async document pipeline with status machine and BM25 refresh"
```

---

### Task 5: 文档 API（上传 / 列表 / 状态轮询）

**Files:**
- Create: `backend/app/api/documents.py`
- Modify: `backend/app/main.py`（挂路由 + `init_db()`）
- Modify: `backend/app/retrieval/vector_store.py`（新增 `remove_by_doc`）
- Test: `backend/tests/test_documents_api.py`

**Interfaces:**
- Consumes: `db.session_scope`、`Document`、`ingest_document`、解析器 `SUPPORTED_EXTS`。
- Produces: `POST /api/documents`（multipart：`file` + `topic`；≤100MB；写入 `data/uploads/{uuid}_{name}`；建记录 `上传中`；BackgroundTasks 触发入库）→ `{id, name, status}`；`GET /api/documents` → 列表（含统计 `total/total_chunks`）；`GET /api/documents/{id}/parse-status` → `{id, status, chunk_count, error_message}`；`DELETE /api/documents/{id}`（删记录 + 从向量库移除该 doc 的切片 + 重建 BM25）。

- [ ] **Step 1: 写失败测试** `backend/tests/test_documents_api.py`

```python
"""文档 API 测试：TestClient + SQLite + 内存向量库；后台任务同步执行（monkeypatch）。"""
import app.db as dbmod
import app.ingestion.pipeline as pmod
from app.api import documents as dmod
from app.db import Base, _make_engine
from app.retrieval.vector_store import LocalVectorStore


def _prepare(monkeypatch, tmp_path):
    engine = _make_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    store = LocalVectorStore(str(tmp_path / "idx.json"))
    monkeypatch.setattr(dbmod, "_engine", engine)      # 所有 session_scope() 走测试库
    monkeypatch.setattr(pmod, "get_store", lambda: store)
    monkeypatch.setattr(pmod, "embed_texts", lambda texts: [[1.0, float(i)] for i, _ in enumerate(texts)])
    monkeypatch.setattr(dmod, "UPLOAD_DIR", tmp_path / "uploads")
    return engine, store


def test_upload_requires_topic(client, monkeypatch, tmp_path):
    _prepare(monkeypatch, tmp_path)
    resp = client.post("/api/documents", files={"file": ("a.md", b"content", "text/markdown")})
    assert resp.status_code == 422          # 主题必选


def test_upload_rejects_unsupported_ext(client, monkeypatch, tmp_path):
    _prepare(monkeypatch, tmp_path)
    resp = client.post("/api/documents",
                       files={"file": ("a.exe", b"MZ", "application/octet-stream")},
                       data={"topic": "内科"})
    assert resp.status_code == 400
    assert "不支持" in resp.json()["detail"]


def test_upload_ingest_and_status_polling(client, monkeypatch, tmp_path):
    _prepare(monkeypatch, tmp_path)
    resp = client.post("/api/documents",
                       files={"file": ("内科讲义.md", "四君子汤由人参白术组成。".encode(), "text/markdown")},
                       data={"topic": "内科"})
    assert resp.status_code == 200
    doc_id = resp.json()["id"]

    st = client.get(f"/api/documents/{doc_id}/parse-status").json()
    assert st["status"] == "就绪"           # TestClient 同步跑完 BackgroundTasks
    assert st["chunk_count"] >= 1

    listed = client.get("/api/documents").json()
    assert listed["total"] == 1
    assert listed["items"][0]["name"] == "内科讲义.md"


def test_list_computes_total_chunks(client, monkeypatch, tmp_path):
    _prepare(monkeypatch, tmp_path)
    client.post("/api/documents", files={"file": ("a.md", b"x", "text/markdown")}, data={"topic": "内科"})
    listed = client.get("/api/documents").json()
    assert listed["total_chunks"] >= 0
```

- [ ] **Step 2: 运行确认失败**

Run: `cd backend && .venv/Scripts/python -m pytest tests/test_documents_api.py -v`
Expected: FAIL（404 / ModuleNotFoundError）

- [ ] **Step 3: 实现** `backend/app/api/documents.py`

```python
"""文档管理 API：上传（multipart）/列表/状态轮询/删除（方案第八节 + 规格 P0-6）。"""
import shutil
import uuid
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, File, Form, HTTPException, UploadFile
from pydantic import BaseModel

from app.config import get_settings
from app.db import session_scope
from app.ingestion.parsers import SUPPORTED_EXTS
from app.ingestion.pipeline import ingest_document
from app.models.document import Document

router = APIRouter()

MAX_UPLOAD_BYTES = 100 * 1024 * 1024          # 规格：单文件 ≤100MB
TOPICS = ["内科", "外科", "儿科", "妇科", "情志脑病", "筋骨伤科", "皮肤病证", "五官病证"]
UPLOAD_DIR = Path(__file__).resolve().parents[3] / "data" / "uploads"


class DocumentOut(BaseModel):
    id: int
    name: str
    file_type: str
    size: int
    topic: str
    status: str
    chunk_count: int
    error_message: str = ""
    uploaded_at: str

    @classmethod
    def of(cls, d: Document) -> "DocumentOut":
        return cls(id=d.id, name=d.name, file_type=d.file_type, size=d.size, topic=d.topic,
                   status=d.status, chunk_count=d.chunk_count, error_message=d.error_message,
                   uploaded_at=d.uploaded_at.strftime("%Y-%m-%d %H:%M"))


@router.post("/documents")
async def upload_document(background: BackgroundTasks,
                          file: UploadFile = File(...),
                          topic: str = Form("")) -> dict:
    """上传文档：校验主题/格式/大小 → 落盘 → 建记录 → 后台入库。"""
    if topic not in TOPICS:
        raise HTTPException(status_code=422, detail=f"知识主题必选，取值：{'/'.join(TOPICS)}")
    name = file.filename or "unnamed"
    ext = name.rsplit(".", 1)[-1].lower() if "." in name else ""
    if ext not in SUPPORTED_EXTS:
        raise HTTPException(status_code=400, detail=f"不支持的文件格式：.{ext}")

    data = await file.read()
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="文件超过 100MB 上限")

    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    stored = UPLOAD_DIR / f"{uuid.uuid4().hex}_{name}"
    stored.write_bytes(data)

    with session_scope() as s:
        doc = Document(name=name, file_type=ext, size=len(data), topic=topic,
                       status="上传中", stored_path=str(stored))
        s.add(doc)
        s.flush()
        doc_id = doc.id

    background.add_task(ingest_document, doc_id)
    return {"id": doc_id, "name": name, "status": "上传中"}


@router.get("/documents")
def list_documents() -> dict:
    with session_scope() as s:
        docs = s.query(Document).order_by(Document.uploaded_at.desc()).all()
        items = [DocumentOut.of(d).model_dump() for d in docs]
        return {"total": len(items), "total_chunks": sum(d["chunk_count"] for d in items), "items": items}


@router.get("/documents/{doc_id}/parse-status")
def parse_status(doc_id: int) -> dict:
    with session_scope() as s:
        doc = s.get(Document, doc_id)
        if doc is None:
            raise HTTPException(status_code=404, detail="文档不存在")
        return {"id": doc.id, "status": doc.status, "chunk_count": doc.chunk_count,
                "error_message": doc.error_message}


@router.delete("/documents/{doc_id}")
def delete_document(doc_id: int) -> dict:
    """删除文档：移除记录 + 从向量库剔除该文档切片 + 重建 BM25。"""
    from app.retrieval.keyword import rebuild_keyword_index
    from app.retrieval.vector_store import get_store

    with session_scope() as s:
        doc = s.get(Document, doc_id)
        if doc is None:
            raise HTTPException(status_code=404, detail="文档不存在")
        name = doc.name
        s.delete(doc)

    store = get_store()
    removed = store.remove_by_doc(name)
    store.save()
    rebuild_keyword_index()
    return {"deleted": doc_id, "removed_chunks": removed}
```

`backend/app/retrieval/vector_store.py` 的 `LocalVectorStore` 类内追加方法（放在 `search` 之后）：

```python
    def remove_by_doc(self, doc_name: str) -> int:
        """移除某文档的全部切片（删除文档时调用）。返回移除数。"""
        keep = [c for c in self.chunks if c["doc_name"] != doc_name]
        removed = len(self.chunks) - len(keep)
        if removed == 0:
            return 0
        self.chunks = keep
        valid = {c["chunk_id"] for c in keep}
        self._vectors = {k: v for k, v in self._vectors.items() if k in valid}
        self._rebuild_matrix()
        return removed
```

`backend/app/main.py` 修改（挂载路由 + 启动建表）：

```python
from app.api.chat import router as chat_router
from app.api.documents import router as documents_router
from app.db import init_db
from app.config import get_settings

settings = get_settings()

app = FastAPI(title="本草智问 MediRAG API", version="0.1.0")
app.include_router(chat_router, prefix="/api")
app.include_router(documents_router, prefix="/api")


@app.on_event("startup")
def _startup() -> None:
    init_db()
```

- [ ] **Step 4: 运行确认通过**

Run: `cd backend && .venv/Scripts/python -m pytest tests/test_documents_api.py -v`
Expected: PASS（4 passed）

- [ ] **Step 5: Commit**

```bash
git add backend/app/api/documents.py backend/app/main.py backend/tests/test_documents_api.py
git commit -m "feat(api): document upload/list/status/delete with async ingestion"
```

---

### Task 6: 实体关系抽取器（LLM → 候选）

**Files:**
- Create: `backend/app/agent/prompts/entity_extract.txt`
- Create: `backend/app/graph/extractor.py`
- Test: `backend/tests/test_extractor.py`

**Interfaces:**
- Produces: `extract_triples(text: str) -> list[dict]`（每项 `{"source","relation","target","source_type","target_type"}`，LLM 失败/解析失败返回 `[]`）；`save_candidates(triples: list[dict], source_doc: str) -> int`（写 Neo4j：节点 MERGE + `status='候选'`，边 MERGE + `status='候选'` + `source_doc`，返回写入边数）。

- [ ] **Step 1: 写失败测试** `backend/tests/test_extractor.py`

```python
"""抽取器测试：LLM 与图客户端全部 monkeypatch，无网络。"""
import app.graph.extractor as emod


def test_extract_triples_parses_llm_json(monkeypatch):
    from app.graph.extractor import extract_triples

    monkeypatch.setattr(emod, "chat_completion", lambda system, user, temperature=0.3: """
```json
[{"source":"四君子汤","relation":"组成","target":"人参","source_type":"方剂","target_type":"中药"}]
```
""")
    triples = extract_triples("四君子汤由人参组成。")
    assert triples == [{"source": "四君子汤", "relation": "组成", "target": "人参",
                        "source_type": "方剂", "target_type": "中药"}]


def test_extract_triples_returns_empty_on_bad_llm_output(monkeypatch):
    from app.graph.extractor import extract_triples

    monkeypatch.setattr(emod, "chat_completion", lambda system, user, temperature=0.3: "抱歉，我无法处理。")
    assert extract_triples("随便什么") == []


def test_extract_triples_returns_empty_on_llm_error(monkeypatch):
    from app.graph.extractor import extract_triples

    def boom(system, user, temperature=0.3):
        raise RuntimeError("LLM 不可用")

    monkeypatch.setattr(emod, "chat_completion", boom)
    assert extract_triples("内容") == []


def test_save_candidates_writes_candidate_status(monkeypatch):
    from app.graph.extractor import save_candidates

    calls = []

    class FakeGraph:
        def execute_write(self, cypher, **params):
            calls.append((cypher, params))

    triples = [{"source": "四君子汤", "relation": "组成", "target": "人参",
                "source_type": "方剂", "target_type": "中药"}]
    n = save_candidates(triples, source_doc="内科讲义.md", graph=FakeGraph())

    assert n == 1
    node_cyphers = [c for c, _ in calls if "MERGE (n:" in c]
    edge_cyphers = [c for c, _ in calls if "-[r:" in c or "MATCH (a" in c]
    assert any("status='候选'" in c or "status = '候选'" in c for c, _ in calls)
    assert len(node_cyphers) >= 2 and len(edge_cyphers) == 1
    assert all(p.get("source_doc") in (None, "内科讲义.md") for _, p in calls if p)
```

- [ ] **Step 2: 运行确认失败**

Run: `cd backend && .venv/Scripts/python -m pytest tests/test_extractor.py -v`
Expected: FAIL（ModuleNotFoundError）

- [ ] **Step 3: 实现**

`backend/app/agent/prompts/entity_extract.txt`：

```text
你是中医药知识图谱抽取器。从下面的文献切片中抽取 (实体, 关系, 实体) 三元组。

要求：
1. 只抽取文本中明确出现的事实，不得推断或补充。
2. 实体类型限：方剂 / 中药 / 证候 / 症状 / 功效 / 禁忌。
3. 关系限：组成 / 主治 / 功效 / 禁忌 / 表现。
4. 只输出 JSON 数组，不要任何解释文字。无可用三元组时输出 []。

输出格式：
[
  {{"source": "四君子汤", "relation": "组成", "target": "人参", "source_type": "方剂", "target_type": "中药"}}
]

【文献切片】
{text}
```

`backend/app/graph/extractor.py`：

```python
"""LLM 实体关系抽取 → Neo4j 候选（方案 6.5 审核闭环）。

抽取的三元组一律 status='候选'；问答链路只查 '已发布'，故候选不会污染回答。
"""
import json
import re
from pathlib import Path

from app.llm.chat import chat_completion

PROMPT_PATH = Path(__file__).resolve().parents[1] / "agent" / "prompts" / "entity_extract.txt"

VALID_RELATIONS = {"组成", "主治", "功效", "禁忌", "表现"}
VALID_TYPES = {"方剂", "中药", "证候", "症状", "功效", "禁忌"}


def extract_triples(text: str) -> list[dict]:
    """调用 LLM 抽取三元组；任何失败（网络/格式/非法值）返回 []。"""
    try:
        prompt = PROMPT_PATH.read_text(encoding="utf-8").format(text=text[:2000])
        raw = chat_completion(system="你是中医药知识图谱抽取器。", user=prompt, temperature=0.0)
    except Exception:
        return []

    match = re.search(r"\[.*\]", raw, re.DOTALL)
    if not match:
        return []
    try:
        data = json.loads(match.group(0))
    except json.JSONDecodeError:
        return []
    if not isinstance(data, list):
        return []

    triples: list[dict] = []
    for item in data:
        if not isinstance(item, dict):
            continue
        if not all(k in item for k in ("source", "relation", "target", "source_type", "target_type")):
            continue
        if item["relation"] not in VALID_RELATIONS:
            continue
        if item["source_type"] not in VALID_TYPES or item["target_type"] not in VALID_TYPES:
            continue
        triples.append({k: str(item[k]).strip() for k in
                        ("source", "relation", "target", "source_type", "target_type")})
    return triples


def save_candidates(triples: list[dict], source_doc: str, graph=None) -> int:
    """写入候选节点/边（MERGE 幂等）。返回写入边数。"""
    if not triples:
        return 0
    if graph is None:
        from app.graph.neo4j_client import get_graph

        graph = get_graph()

    edges = 0
    for t in triples:
        for name, label in ((t["source"], t["source_type"]), (t["target"], t["target_type"])):
            graph.execute_write(
                f"MERGE (n:`{label.replace('`', '``')}` {{name: $name}}) "
                "ON CREATE SET n.status = '候选', n.source = $source_doc "
                "ON MATCH SET n.status = CASE WHEN n.status = '已发布' THEN '已发布' ELSE '候选' END",
                name=name, source_doc=source_doc,
            )
        graph.execute_write(
            f"MATCH (a {{name: $s}}), (b {{name: $t}}) "
            f"MERGE (a)-[r:`{t['relation'].replace('`', '``')}`]->(b) "
            "ON CREATE SET r.status = '候选', r.source_doc = $source_doc "
            "ON MATCH SET r.status = CASE WHEN r.status = '已发布' THEN '已发布' ELSE '候选' END",
            s=t["source"], t=t["target"], source_doc=source_doc,
        )
        edges += 1
    return edges
```

- [ ] **Step 4: 运行确认通过**

Run: `cd backend && .venv/Scripts/python -m pytest tests/test_extractor.py -v`
Expected: PASS（4 passed）

- [ ] **Step 5: Commit**

```bash
git add backend/app/agent/prompts/entity_extract.txt backend/app/graph/extractor.py backend/tests/test_extractor.py
git commit -m "feat(graph): LLM triple extraction into candidate status"
```

---

### Task 7: 图谱查询与候选审核 API

**Files:**
- Create: `backend/app/api/graph_api.py`
- Modify: `backend/app/graph/neo4j_client.py`（新增 `run_read`）
- Modify: `backend/app/main.py`（挂路由）
- Test: `backend/tests/test_graph_api.py`

**Interfaces:**
- Consumes: `get_graph()`（Neo4j client，含 `execute_write`；测试注入 fake）。
- Produces:
  - `GET /api/graph/search?entity=&type=` → `{items: [{name, type, alias, status}]}`
  - `GET /api/graph/neighbors?name=&hop=2` → `{nodes: [{id,name,category,status}], links: [{source,target,relation,status}]}`
  - `GET /api/graph/entities/{name}` → `{name, type, alias, desc, source, status}`
  - `GET /api/graph/candidates` → `{nodes: [...候选节点...], edges: [...候选边...]}`
  - `POST /api/graph/candidates/approve`（body：`{"kind":"node"|"edge","name"|"source"/"target"/"relation"}`）→ 置 `已发布`
  - `POST /api/graph/candidates/reject` → 删除候选（节点仅当无已发布边引用）

- [ ] **Step 1: 写失败测试** `backend/tests/test_graph_api.py`

```python
"""图谱 API 测试：fake graph client（记录 cypher），无真实 Neo4j。"""
import app.api.graph_api as gmod


class FakeGraph:
    def __init__(self, rows=None):
        self.rows = rows or []
        self.calls = []

    def execute_write(self, cypher, **params):
        self.calls.append((cypher, params))

    def run_read(self, cypher, **params):
        self.calls.append((cypher, params))
        return self.rows


def _use(monkeypatch, fake):
    monkeypatch.setattr(gmod, "get_graph", lambda: fake)


def test_search_returns_items(client, monkeypatch):
    _use(monkeypatch, FakeGraph(rows=[{"name": "四君子汤", "type": "方剂", "alias": "", "status": "已发布"}]))
    resp = client.get("/api/graph/search", params={"entity": "四君子"})
    assert resp.status_code == 200
    assert resp.json()["items"][0]["name"] == "四君子汤"


def test_neighbors_returns_nodes_and_links(client, monkeypatch):
    rows = [{"source": "四君子汤", "relation": "组成", "target": "人参",
             "source_type": "方剂", "target_type": "中药", "status": "已发布"}]
    _use(monkeypatch, FakeGraph(rows=rows))
    body = client.get("/api/graph/neighbors", params={"name": "四君子汤", "hop": 2}).json()
    ids = {n["name"] for n in body["nodes"]}
    assert ids == {"四君子汤", "人参"}
    assert body["links"][0]["relation"] == "组成"


def test_candidates_lists_pending_only(client, monkeypatch):
    rows = [{"source": "归脾汤", "relation": "组成", "target": "远志",
             "source_type": "方剂", "target_type": "中药", "status": "候选",
             "source_doc": "内科讲义.md"}]
    _use(monkeypatch, FakeGraph(rows=rows))
    resp = client.get("/api/graph/candidates").json()
    assert resp["edges"][0]["target"] == "远志"
    assert resp["edges"][0]["source_doc"] == "内科讲义.md"


def test_approve_sets_published(client, monkeypatch):
    fake = FakeGraph()
    _use(monkeypatch, fake)
    resp = client.post("/api/graph/candidates/approve",
                       json={"kind": "edge", "source": "归脾汤", "relation": "组成", "target": "远志"})
    assert resp.status_code == 200
    cypher, params = fake.calls[-1]
    assert "已发布" in cypher and params["s"] == "归脾汤"


def test_approve_node(client, monkeypatch):
    fake = FakeGraph()
    _use(monkeypatch, fake)
    resp = client.post("/api/graph/candidates/approve", json={"kind": "node", "name": "远志"})
    assert resp.status_code == 200
    cypher, params = fake.calls[-1]
    assert params["name"] == "远志" and "已发布" in cypher


def test_entity_detail_404(client, monkeypatch):
    _use(monkeypatch, FakeGraph(rows=[]))
    assert client.get("/api/graph/entities/不存在").status_code == 404
```

- [ ] **Step 2: 运行确认失败**

Run: `cd backend && .venv/Scripts/python -m pytest tests/test_graph_api.py -v`
Expected: FAIL（ModuleNotFoundError / 404）

- [ ] **Step 3: 实现** `backend/app/api/graph_api.py`

```python
"""图谱 API：搜索/邻居/详情 + 候选审核（规格 P0-5，方案 6.5/第八节）。"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.graph.neo4j_client import get_graph

router = APIRouter()


def _read(cypher: str, **params) -> list[dict]:
    """只读查询（GraphClient.run_read；测试注入 fake 客户端）。"""
    return get_graph().run_read(cypher, **params)


@router.get("/graph/search")
def search_entities(entity: str = "", type: str = "") -> dict:
    where, params = ["n.status IN ['已发布','候选']"], {}
    if entity:
        where.append("n.name CONTAINS $entity")
        params["entity"] = entity
    if type:
        where.append("n.type = $type")
        params["type"] = type
    rows = _read(
        f"MATCH (n) WHERE {' AND '.join(where)} "
        "RETURN n.name AS name, n.type AS type, n.alias AS alias, n.status AS status "
        "ORDER BY n.name LIMIT 200",
        **params,
    )
    return {"items": rows}


@router.get("/graph/neighbors")
def neighbors(name: str, hop: int = 2) -> dict:
    hop = min(max(int(hop), 1), 2)
    rows = _read(
        f"MATCH p = (a)-[*1..{hop}]-(b) WHERE a.name = $name "
        "UNWIND relationships(p) AS r "
        "RETURN DISTINCT startNode(r).name AS source, type(r) AS relation, endNode(r).name AS target, "
        "startNode(r).type AS source_type, endNode(r).type AS target_type, startNode(r).status AS status",
        name=name,
    )
    nodes: dict[str, dict] = {}
    links: list[dict] = []
    for r in rows:
        for n, t in ((r["source"], r["source_type"]), (r["target"], r["target_type"])):
            nodes.setdefault(n, {"id": n, "name": n, "category": t, "status": r["status"]})
        links.append({"source": r["source"], "target": r["target"],
                      "relation": r["relation"], "status": r["status"]})
    return {"nodes": list(nodes.values()), "links": links}


@router.get("/graph/entities/{name}")
def entity_detail(name: str) -> dict:
    rows = _read(
        "MATCH (n {name: $name}) RETURN n.name AS name, n.type AS type, n.alias AS alias, "
        "n.desc AS desc, n.source AS source, n.status AS status LIMIT 1",
        name=name,
    )
    if not rows:
        raise HTTPException(status_code=404, detail="实体不存在")
    return rows[0]


@router.get("/graph/candidates")
def list_candidates() -> dict:
    edges = _read(
        "MATCH (a)-[r]->(b) WHERE r.status = '候选' "
        "RETURN a.name AS source, type(r) AS relation, b.name AS target, "
        "a.type AS source_type, b.type AS target_type, r.source_doc AS source_doc LIMIT 500"
    )
    node_rows = _read(
        "MATCH (n) WHERE n.status = '候选' "
        "RETURN n.name AS name, n.type AS type, n.source AS source_doc LIMIT 500"
    )
    return {"nodes": node_rows, "edges": edges}


class ApproveBody(BaseModel):
    kind: str                     # "node" | "edge"
    name: str = ""
    source: str = ""
    relation: str = ""
    target: str = ""


@router.post("/graph/candidates/approve")
def approve(body: ApproveBody) -> dict:
    graph = get_graph()
    if body.kind == "node":
        if not body.name:
            raise HTTPException(status_code=422, detail="node 需提供 name")
        graph.execute_write("MATCH (n {name: $name}) SET n.status = '已发布'", name=body.name)
        return {"approved": "node", "name": body.name}
    if body.kind == "edge":
        if not (body.source and body.relation and body.target):
            raise HTTPException(status_code=422, detail="edge 需提供 source/relation/target")
        graph.execute_write(
            "MATCH (a {name: $s})-[r]->(b {name: $t}) WHERE type(r) = $rel "
            "SET r.status = '已发布'",
            s=body.source, t=body.target, rel=body.relation,
        )
        return {"approved": "edge", "source": body.source, "relation": body.relation, "target": body.target}
    raise HTTPException(status_code=422, detail="kind 取值为 node|edge")


@router.post("/graph/candidates/reject")
def reject(body: ApproveBody) -> dict:
    graph = get_graph()
    if body.kind == "node":
        graph.execute_write("MATCH (n {name: $name}) WHERE n.status = '候选' DETACH DELETE n", name=body.name)
        return {"rejected": "node", "name": body.name}
    if body.kind == "edge":
        graph.execute_write(
            "MATCH (a {name: $s})-[r]->(b {name: $t}) WHERE type(r) = $rel AND r.status = '候选' DELETE r",
            s=body.source, t=body.target, rel=body.relation,
        )
        return {"rejected": "edge", "source": body.source, "relation": body.relation, "target": body.target}
    raise HTTPException(status_code=422, detail="kind 取值为 node|edge")
```

`backend/app/graph/neo4j_client.py` 的 `GraphClient` 类内追加只读查询方法（放在 `execute_write` 之后）：

```python
    def run_read(self, cypher: str, **params) -> list[dict]:
        """只读查询，返回行列表（业务 API 用，避免外部访问私有驱动）。"""
        with self._driver.session() as session:
            return session.run(cypher, **params).data()
```

`backend/app/main.py` 追加挂载：

```python
from app.api.graph_api import router as graph_router

app.include_router(graph_router, prefix="/api")
```

- [ ] **Step 4: 运行确认通过**

Run: `cd backend && .venv/Scripts/python -m pytest tests/test_graph_api.py -v`
Expected: PASS（6 passed）

- [ ] **Step 5: Commit**

```bash
git add backend/app/api/graph_api.py backend/app/main.py backend/tests/test_graph_api.py
git commit -m "feat(api): graph search/neighbors/detail and candidate review endpoints"
```

---

### Task 8: 前端典籍知识库页（Library + UploadDialog）

**Files:**
- Create: `web/src/types/knowledge.ts`、`web/src/api/documents.ts`
- Create: `web/src/views/knowledge/Library.vue`、`web/src/views/knowledge/UploadDialog.vue`
- Modify: `web/src/router/index.ts`

**Interfaces:**
- Consumes: `POST/GET /api/documents`、`GET /api/documents/{id}/parse-status`。
- Produces: 路由 `/library` → Library.vue（统计卡 + 主题筛选 + 文档表格 + 上传按钮/弹窗 + 状态轮询）；`UploadDialog` 支持 `v-model:visible` + `@uploaded` 事件。

- [ ] **Step 1: 实现 types 与 api**

`web/src/types/knowledge.ts`：

```ts
export const TOPICS = ['内科', '外科', '儿科', '妇科', '情志脑病', '筋骨伤科', '皮肤病证', '五官病证'] as const
export type Topic = typeof TOPICS[number]

export interface DocItem {
  id: number
  name: string
  file_type: string
  size: number
  topic: string
  status: '上传中' | '处理中' | '就绪' | '失败'
  chunk_count: number
  error_message: string
  uploaded_at: string
}

export interface DocList {
  total: number
  total_chunks: number
  items: DocItem[]
}
```

`web/src/api/documents.ts`：

```ts
import type { DocList, DocItem } from '../types/knowledge'

export async function listDocuments(): Promise<DocList> {
  const resp = await fetch('/api/documents')
  if (!resp.ok) throw new Error(`列表加载失败（${resp.status}）`)
  return resp.json()
}

export async function uploadDocument(file: File, topic: string) {
  const form = new FormData()
  form.append('file', file)
  form.append('topic', topic)
  const resp = await fetch('/api/documents', { method: 'POST', body: form })
  if (!resp.ok) {
    const detail = await resp.json().catch(() => ({ detail: `HTTP ${resp.status}` }))
    throw new Error(detail.detail ?? '上传失败')
  }
  return resp.json()
}

export async function parseStatus(id: number): Promise<Pick<DocItem, 'id' | 'status' | 'chunk_count' | 'error_message'>> {
  const resp = await fetch(`/api/documents/${id}/parse-status`)
  if (!resp.ok) throw new Error(`状态查询失败（${resp.status}）`)
  return resp.json()
}

export function humanSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`
}
```

- [ ] **Step 2: 实现 UploadDialog.vue**

```vue
<script setup lang="ts">
// 上传弹窗：拖拽区 + 支持格式清单 + 知识主题必选（规格 P0-6 逐字）
import { computed, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { TOPICS } from '../../types/knowledge'
import { uploadDocument } from '../../api/documents'

const props = defineProps<{ visible: boolean }>()
const emit = defineEmits<{ (e: 'update:visible', v: boolean): void; (e: 'uploaded'): void }>()

const FORMATS = 'PDF/DOC/DOCX/RTF/PPT/PPTX、XLS/XLSX/CSV/TSV、TXT/MD/HTML/JSON/XML/YAML/LOG'
const MAX_MB = 100

const file = ref<File | null>(null)
const topic = ref('')
const dragging = ref(false)
const uploading = ref(false)
const topicError = ref(false)

const canSubmit = computed(() => !!file.value && !!topic.value && !uploading.value)

watch(() => props.visible, (v) => {
  if (v) { file.value = null; topic.value = ''; topicError.value = false }
})

function pick(f: File | undefined) {
  if (!f) return
  if (f.size > MAX_MB * 1024 * 1024) { ElMessage.error(`单文件不超过 ${MAX_MB}MB`); return }
  file.value = f
}

function onDrop(e: DragEvent) {
  dragging.value = false
  pick(e.dataTransfer?.files?.[0])
}

async function submit() {
  if (!file.value) { ElMessage.warning('请选择文件'); return }
  if (!topic.value) { topicError.value = true; ElMessage.warning('请选择知识主题'); return }
  uploading.value = true
  try {
    await uploadDocument(file.value, topic.value)
    ElMessage.success('已提交入库，处理中…')
    emit('uploaded')
    emit('update:visible', false)
  } catch (e) {
    ElMessage.error((e as Error).message)
  } finally {
    uploading.value = false
  }
}
</script>

<template>
  <el-dialog :model-value="visible" title="上传典籍文献" width="560px"
             @update:model-value="emit('update:visible', $event)">
    <div class="drop-zone" :class="{ dragging }"
         @dragover.prevent="dragging = true"
         @dragleave.prevent="dragging = false"
         @drop.prevent="onDrop"
         @click="($refs.fileInput as HTMLInputElement).click()">
      <el-icon :size="28" color="#2d6a4f"><UploadFilled /></el-icon>
      <p>将文件拖到此处，或 <em>点击选择</em></p>
      <p class="hint">支持格式：{{ FORMATS }}；单文件 ≤ {{ MAX_MB }}MB</p>
      <p v-if="file" class="picked">{{ file.name }}（{{ (file.size / 1024).toFixed(1) }} KB）</p>
    </div>
    <input ref="fileInput" type="file" class="hidden-input" @change="pick(($event.target as HTMLInputElement).files?.[0])" />

    <div class="topic-block">
      <div class="topic-label">知识主题 <span class="required">*</span></div>
      <el-radio-group v-model="topic" class="topic-group">
        <el-radio-button v-for="t in TOPICS" :key="t" :value="t">{{ t }}</el-radio-button>
      </el-radio-group>
      <p v-if="topicError" class="topic-error">知识主题为必选项</p>
    </div>

    <template #footer>
      <el-button @click="emit('update:visible', false)">取消</el-button>
      <el-button type="primary" :disabled="!canSubmit" :loading="uploading" @click="submit">开始上传</el-button>
    </template>
  </el-dialog>
</template>

<style scoped>
.drop-zone {
  border: 1.5px dashed #b3d5c4; border-radius: 10px; padding: 28px 16px;
  text-align: center; cursor: pointer; background: #fafbfa;
}
.drop-zone.dragging { border-color: #2d6a4f; background: #e6f1ea; }
.drop-zone p { margin: 6px 0; font-size: 13px; color: #6b7280; }
.drop-zone em { color: #2d6a4f; font-style: normal; }
.drop-zone .hint { font-size: 12px; color: #9ca3af; }
.picked { color: #1f2937 !important; font-weight: 600; }
.hidden-input { display: none; }
.topic-block { margin-top: 18px; }
.topic-label { font-size: 13px; font-weight: 600; margin-bottom: 8px; }
.required { color: #c62828; }
.topic-error { color: #c62828; font-size: 12px; margin-top: 6px; }
</style>
```

- [ ] **Step 3: 实现 Library.vue**

```vue
<script setup lang="ts">
// 典籍知识库：统计卡 + 主题筛选 + 文档表格 + 上传（规格 P0-6）
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import type { DocItem } from '../../types/knowledge'
import { TOPICS } from '../../types/knowledge'
import { humanSize, listDocuments, parseStatus } from '../../api/documents'
import UploadDialog from './UploadDialog.vue'

const docs = ref<DocItem[]>([])
const total = ref(0)
const totalChunks = ref(0)
const filterTopic = ref('')
const showUpload = ref(false)
let timer: number | undefined

const filtered = computed(() =>
  filterTopic.value ? docs.value.filter(d => d.topic === filterTopic.value) : docs.value)

const STATUS_TAG: Record<string, string> = { 上传中: 'info', 处理中: 'warning', 就绪: 'success', 失败: 'danger' }

async function refresh() {
  try {
    const res = await listDocuments()
    docs.value = res.items
    total.value = res.total
    totalChunks.value = res.total_chunks
  } catch (e) {
    ElMessage.error((e as Error).message)
  }
}

async function pollPending() {
  const pending = docs.value.filter(d => d.status === '上传中' || d.status === '处理中')
  for (const d of pending) {
    try {
      const st = await parseStatus(d.id)
      const hit = docs.value.find(x => x.id === d.id)
      if (hit) { hit.status = st.status; hit.chunk_count = st.chunk_count }
      if (st.status === '失败') ElMessage.error(`${d.name} 入库失败：${st.error_message}`)
      if (st.status === '就绪') totalChunks.value += st.chunk_count
    } catch { /* 轮询失败静默，下轮重试 */ }
  }
}

async function removeDoc(d: DocItem) {
  await ElMessageBox.confirm(`确认删除《${d.name}》？其切片将从检索库移除。`, '删除确认', { type: 'warning' })
  await fetch(`/api/documents/${d.id}`, { method: 'DELETE' })
  ElMessage.success('已删除')
  refresh()
}

onMounted(() => { refresh(); timer = window.setInterval(pollPending, 2000) })
onUnmounted(() => window.clearInterval(timer))
</script>

<template>
  <div class="library-page">
    <div class="stat-row">
      <el-card shadow="never" class="stat-card">
        <div class="stat-num">{{ total }}</div>
        <div class="stat-label">典籍文献数</div>
      </el-card>
      <el-card shadow="never" class="stat-card">
        <div class="stat-num">{{ totalChunks }}</div>
        <div class="stat-label">知识切片数</div>
      </el-card>
      <div class="stat-actions">
        <el-button type="primary" @click="showUpload = true">
          <el-icon><Upload /></el-icon>&nbsp;上传文献
        </el-button>
      </div>
    </div>

    <el-card shadow="never">
      <div class="filter-row">
        <span class="filter-label">知识主题</span>
        <el-select v-model="filterTopic" placeholder="全部主题" clearable style="width: 160px">
          <el-option v-for="t in TOPICS" :key="t" :label="t" :value="t" />
        </el-select>
      </div>

      <el-table :data="filtered" style="width: 100%">
        <el-table-column prop="name" label="名称" min-width="200" show-overflow-tooltip />
        <el-table-column label="大小" width="100">
          <template #default="{ row }">{{ humanSize(row.size) }}</template>
        </el-table-column>
        <el-table-column prop="file_type" label="格式" width="80" />
        <el-table-column label="状态" width="100">
          <template #default="{ row }">
            <el-tag :type="STATUS_TAG[row.status] as any" size="small">{{ row.status }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="topic" label="知识主题" width="110" />
        <el-table-column prop="chunk_count" label="切片数" width="90" />
        <el-table-column prop="uploaded_at" label="上传时间" width="150" />
        <el-table-column label="操作" width="100" fixed="right">
          <template #default="{ row }">
            <el-button link type="danger" size="small" @click="removeDoc(row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <UploadDialog v-model:visible="showUpload" @uploaded="refresh" />
  </div>
</template>

<style scoped>
.library-page { display: flex; flex-direction: column; gap: 16px; }
.stat-row { display: flex; gap: 16px; align-items: center; }
.stat-card { width: 180px; text-align: center; }
.stat-num { font-size: 26px; font-weight: 600; color: #2d6a4f; }
.stat-label { font-size: 13px; color: #6b7280; }
.stat-actions { margin-left: auto; }
.filter-row { display: flex; align-items: center; gap: 10px; margin-bottom: 14px; }
.filter-label { font-size: 13px; color: #6b7280; }
</style>
```

- [ ] **Step 4: 路由接线**

`web/src/router/index.ts` 的 library 路由改为：

```ts
{
  path: 'library',
  name: 'library',
  component: () => import('../views/knowledge/Library.vue'),
  meta: { title: '典籍知识库', breadcrumb: '典籍知识库' },
},
```

- [ ] **Step 5: 构建门禁 + Commit**

Run: `cd web && npm run type-check && npm run build`
Expected: 零错误

```bash
git add web/src/types/knowledge.ts web/src/api/documents.ts web/src/views/knowledge/Library.vue web/src/views/knowledge/UploadDialog.vue web/src/router/index.ts
git commit -m "feat(web): knowledge library page with upload dialog and status polling"
```

---

### Task 9: 前端本草图谱页（GraphExplore + CandidateReview）

**Files:**
- Create: `web/src/types/graph.ts`、`web/src/api/graph.ts`
- Create: `web/src/views/graph/GraphExplore.vue`、`web/src/views/graph/CandidateReview.vue`
- Modify: `web/src/router/index.ts`

**Interfaces:**
- Consumes: `/api/graph/search|neighbors|entities/{name}`、`/api/graph/candidates|approve|reject`。
- Produces: 路由 `/graph` → GraphExplore.vue（图谱浏览/候选审核 双 Tab；左实体列表 + 中 ECharts 力导向图 + 右详情面板）。

- [ ] **Step 1: 实现 types 与 api**

`web/src/types/graph.ts`：

```ts
export interface GraphEntity {
  name: string
  type: string
  alias: string
  status: string
}

export interface GraphNode { id: string; name: string; category: string; status: string }
export interface GraphLink { source: string; target: string; relation: string; status: string }

export interface CandidateNode { name: string; type: string; source_doc: string }
export interface CandidateEdge {
  source: string; relation: string; target: string
  source_type: string; target_type: string; source_doc: string
}

/* 节点类型 → theme token 名（颜色在组件内从 theme.ts 取） */
export const NODE_TYPES = ['方剂', '中药', '证候', '症状', '功效', '禁忌'] as const
```

`web/src/api/graph.ts`：

```ts
import type { CandidateEdge, CandidateNode, GraphEntity, GraphLink, GraphNode } from '../types/graph'

async function getJson<T>(url: string): Promise<T> {
  const resp = await fetch(url)
  if (!resp.ok) throw new Error(`${url} 失败（${resp.status}）`)
  return resp.json()
}

export const searchEntities = (entity: string, type = '') =>
  getJson<{ items: GraphEntity[] }>(`/api/graph/search?entity=${encodeURIComponent(entity)}&type=${encodeURIComponent(type)}`)

export const getNeighbors = (name: string, hop = 2) =>
  getJson<{ nodes: GraphNode[]; links: GraphLink[] }>(`/api/graph/neighbors?name=${encodeURIComponent(name)}&hop=${hop}`)

export const getEntityDetail = (name: string) =>
  getJson<GraphEntity & { desc: string; source: string }>(`/api/graph/entities/${encodeURIComponent(name)}`)

export const listCandidates = () =>
  getJson<{ nodes: CandidateNode[]; edges: CandidateEdge[] }>('/api/graph/candidates')

async function post(url: string, body: unknown) {
  const resp = await fetch(url, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) })
  if (!resp.ok) {
    const detail = await resp.json().catch(() => ({ detail: `HTTP ${resp.status}` }))
    throw new Error(detail.detail ?? '操作失败')
  }
  return resp.json()
}

export const approveCandidate = (body: Record<string, string>) => post('/api/graph/candidates/approve', body)
export const rejectCandidate = (body: Record<string, string>) => post('/api/graph/candidates/reject', body)
```

- [ ] **Step 2: 实现 CandidateReview.vue**

```vue
<script setup lang="ts">
// 候选审核 Tab：LLM 抽取 → 人工确认 → 发布（方案 6.5 闭环）
import { onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import type { CandidateEdge, CandidateNode } from '../../types/graph'
import { approveCandidate, listCandidates, rejectCandidate } from '../../api/graph'

const nodes = ref<CandidateNode[]>([])
const edges = ref<CandidateEdge[]>([])
const loading = ref(false)

async function refresh() {
  loading.value = true
  try {
    const res = await listCandidates()
    nodes.value = res.nodes
    edges.value = res.edges
  } catch (e) {
    ElMessage.error((e as Error).message)
  } finally {
    loading.value = false
  }
}

async function approveEdge(e: CandidateEdge) {
  await approveCandidate({ kind: 'edge', source: e.source, relation: e.relation, target: e.target })
  ElMessage.success(`已发布：${e.source} --${e.relation}--> ${e.target}`)
  refresh()
}

async function rejectEdge(e: CandidateEdge) {
  await rejectCandidate({ kind: 'edge', source: e.source, relation: e.relation, target: e.target })
  ElMessage.success('已驳回该关系')
  refresh()
}

async function approveNode(n: CandidateNode) {
  await approveCandidate({ kind: 'node', name: n.name })
  ElMessage.success(`已发布实体：${n.name}`)
  refresh()
}

onMounted(refresh)
</script>

<template>
  <div v-loading="loading" class="review-panel">
    <div class="review-head">
      <span>待审核关系 {{ edges.length }} 条 · 待审核实体 {{ nodes.length }} 个</span>
      <el-button size="small" @click="refresh">刷新</el-button>
    </div>

    <el-table :data="edges" size="small" class="review-table">
      <el-table-column label="关系" min-width="320">
        <template #default="{ row }">{{ row.source }} --{{ row.relation }}--> {{ row.target }}</template>
      </el-table-column>
      <el-table-column prop="source_doc" label="来源" width="160" show-overflow-tooltip />
      <el-table-column label="操作" width="140">
        <template #default="{ row }">
          <el-button link type="primary" size="small" @click="approveEdge(row)">发布</el-button>
          <el-button link type="danger" size="small" @click="rejectEdge(row)">驳回</el-button>
        </template>
      </el-table-column>
    </el-table>

    <el-table :data="nodes" size="small" class="review-table">
      <el-table-column prop="name" label="实体" min-width="160" />
      <el-table-column prop="type" label="类型" width="90" />
      <el-table-column prop="source_doc" label="来源" width="160" show-overflow-tooltip />
      <el-table-column label="操作" width="100">
        <template #default="{ row }">
          <el-button link type="primary" size="small" @click="approveNode(row)">发布</el-button>
        </template>
      </el-table-column>
    </el-table>

    <el-empty v-if="!loading && !edges.length && !nodes.length" description="暂无待审核候选知识" />
    <p class="review-note">候选知识经人工审核后发布，回答结论保留原文证据</p>
  </div>
</template>

<style scoped>
.review-panel { display: flex; flex-direction: column; gap: 12px; }
.review-head { display: flex; justify-content: space-between; align-items: center; font-size: 13px; color: #6b7280; }
.review-note { font-size: 12px; color: #9ca3af; text-align: right; }
</style>
```

- [ ] **Step 3: 实现 GraphExplore.vue**

```vue
<script setup lang="ts">
// 本草图谱：左实体列表 + 中 ECharts 力导向图 + 右详情；候选审核 Tab（规格 P0-5）
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import * as echarts from 'echarts'
import { ElMessage } from 'element-plus'
import { theme } from '../../styles/theme'
import type { GraphEntity, GraphLink, GraphNode } from '../../types/graph'
import { getEntityDetail, getNeighbors, searchEntities } from '../../api/graph'
import CandidateReview from './CandidateReview.vue'

const TYPE_COLOR: Record<string, string> = {
  方剂: theme.nodeFormula, 中药: theme.nodeHerb, 证候: theme.nodeSyndrome,
  症状: theme.nodeSymptom, 功效: theme.nodeEffect, 禁忌: theme.nodeContra,
}

const activeTab = ref('browse')
const keyword = ref('')
const typeFilter = ref('')
const entities = ref<GraphEntity[]>([])
const selected = ref<GraphEntity | null>(null)
const detail = ref<(GraphEntity & { desc: string; source: string }) | null>(null)
const chartRef = ref<HTMLElement>()
let chart: echarts.ECharts | undefined

const TYPES = ['方剂', '中药', '证候', '症状', '功效', '禁忌']

async function doSearch() {
  try {
    const res = await searchEntities(keyword.value, typeFilter.value)
    entities.value = res.items
  } catch (e) { ElMessage.error((e as Error).message) }
}

async function focusEntity(name: string) {
  try {
    const res = await getNeighbors(name, 2)
    renderGraph(res.nodes, res.links)
    detail.value = await getEntityDetail(name)
    selected.value = { name, type: detail.value.type, alias: detail.value.alias, status: detail.value.status }
  } catch (e) { ElMessage.error((e as Error).message) }
}

function renderGraph(nodes: GraphNode[], links: GraphLink[]) {
  if (!chartRef.value) return
  chart = chart ?? echarts.init(chartRef.value)
  chart.setOption({
    tooltip: {},
    legend: [{ data: TYPES, bottom: 0, textStyle: { fontSize: 11 } }],
    series: [{
      type: 'graph', layout: 'force', roam: true, draggable: true,
      categories: TYPES.map(t => ({ name: t, itemStyle: { color: TYPE_COLOR[t] } })),
      label: { show: true, fontSize: 11 },
      force: { repulsion: 300, edgeLength: 90 },
      edgeLabel: { show: true, fontSize: 10, formatter: (p: any) => p.data.relation },
      data: nodes.map(n => ({
        id: n.name, name: n.name,
        category: TYPES.indexOf(n.category), symbolSize: n.status === '候选' ? 22 : 30,
        itemStyle: n.status === '候选' ? { borderType: 'dashed', borderWidth: 2, borderColor: '#9ca3af' } : {},
      })),
      links: links.map(l => ({ source: l.source, target: l.target, relation: l.relation })),
      lineStyle: { color: '#cde3d7', width: 1.5, curveness: 0.08 },
    }],
  })
}

watch(activeTab, (v) => { if (v === 'browse') setTimeout(() => chart?.resize(), 50) })
onMounted(() => { doSearch(); window.addEventListener('resize', () => chart?.resize()) })
onUnmounted(() => { chart?.dispose() })
</script>

<template>
  <div class="graph-page">
    <div class="toolbar">
      <el-input v-model="keyword" placeholder="搜索中药、方剂、证候或症状" style="width: 260px"
                @keyup.enter="doSearch" />
      <el-select v-model="typeFilter" placeholder="全部实体类型" clearable style="width: 140px">
        <el-option v-for="t in TYPES" :key="t" :label="t" :value="t" />
      </el-select>
      <el-button type="primary" @click="doSearch">查询</el-button>
      <el-button link type="primary">重新导入基础数据</el-button>
    </div>

    <el-tabs v-model="activeTab" class="graph-tabs">
      <el-tab-pane label="图谱浏览" name="browse">
        <div class="browse-body">
          <aside class="entity-list">
            <div class="list-head">实体结果 <el-tag size="small" type="info">{{ entities.length }}</el-tag></div>
            <div v-for="e in entities" :key="e.name" class="entity-item"
                 :class="{ active: selected?.name === e.name }" @click="focusEntity(e.name)">
              <span class="dot" :style="{ background: TYPE_COLOR[e.type] ?? '#9ca3af' }" />
              <span class="entity-name">{{ e.name }}</span>
              <el-tag size="small" class="entity-type">{{ e.type }}</el-tag>
            </div>
          </aside>

          <div class="canvas-wrap">
            <div ref="chartRef" class="chart" />
            <el-empty v-if="!chart" description="点击左侧实体查看关系图" />
          </div>

          <aside class="detail-panel">
            <template v-if="detail">
              <div class="detail-head">
                <span class="dot" :style="{ background: TYPE_COLOR[detail.type] }" />
                <strong>{{ detail.name }}</strong>
                <el-tag size="small">{{ detail.type }}</el-tag>
              </div>
              <div class="detail-field"><label>别名</label><span>{{ detail.alias || '—' }}</span></div>
              <div class="detail-field"><label>说明</label><span>{{ detail.desc || '—' }}</span></div>
              <div class="detail-field"><label>来源</label><span>{{ detail.source || '—' }}</span></div>
              <div class="legend">
                <span v-for="t in TYPES" :key="t">
                  <i :style="{ background: TYPE_COLOR[t] }" />{{ t }}
                </span>
              </div>
            </template>
            <el-empty v-else description="选择实体查看详情" :image-size="60" />
          </aside>
        </div>
      </el-tab-pane>

      <el-tab-pane label="候选审核" name="review">
        <CandidateReview />
      </el-tab-pane>
    </el-tabs>
  </div>
</template>

<style scoped>
.graph-page { display: flex; flex-direction: column; gap: 12px; }
.toolbar { display: flex; gap: 10px; align-items: center; }
.browse-body { display: grid; grid-template-columns: 240px 1fr 260px; gap: 12px; min-height: 520px; }
.entity-list, .detail-panel { background: #fff; border: 1px solid #e5e7eb; border-radius: 10px; padding: 10px; overflow-y: auto; max-height: 620px; }
.list-head { font-size: 13px; font-weight: 600; margin-bottom: 8px; display: flex; justify-content: space-between; }
.entity-item { display: flex; align-items: center; gap: 6px; padding: 7px 8px; border-radius: 8px; cursor: pointer; font-size: 13px; }
.entity-item:hover, .entity-item.active { background: #e6f1ea; }
.dot { width: 8px; height: 8px; border-radius: 50%; flex: none; }
.entity-name { flex: 1; }
.entity-type { transform: scale(0.9); }
.canvas-wrap { background: #fff; border: 1px solid #e5e7eb; border-radius: 10px; position: relative; }
.chart { width: 100%; height: 600px; }
.detail-head { display: flex; align-items: center; gap: 6px; margin-bottom: 12px; }
.detail-field { margin-bottom: 10px; font-size: 13px; }
.detail-field label { display: block; color: #6b7280; font-size: 12px; margin-bottom: 2px; }
.legend { display: flex; flex-wrap: wrap; gap: 8px; font-size: 12px; color: #6b7280; margin-top: 16px; }
.legend i { display: inline-block; width: 8px; height: 8px; border-radius: 50%; margin-right: 3px; }
</style>
```

- [ ] **Step 4: 路由接线 + 构建门禁 + Commit**

`web/src/router/index.ts` 的 graph 路由改为：

```ts
{
  path: 'graph',
  name: 'graph',
  component: () => import('../views/graph/GraphExplore.vue'),
  meta: { title: '本草图谱', breadcrumb: '本草图谱' },
},
```

Run: `cd web && npm run type-check && npm run build`
Expected: 零错误

```bash
git add web/src/types/graph.ts web/src/api/graph.ts web/src/views/graph/GraphExplore.vue web/src/views/graph/CandidateReview.vue web/src/router/index.ts
git commit -m "feat(web): graph explore page with force layout and candidate review tab"
```

---

### Task 10: 端到端实测验收

**Files:**
- Create: `docs/superpowers/plans/stage4-verification.md`
- 不改业务代码。

- [ ] **Step 1: 启动中间件与后端**

```bash
docker compose -f deploy/docker-compose.yml up -d mysql neo4j
cd backend && .venv/Scripts/python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

- [ ] **Step 2: 上传实测（真实 multipart）**

用 httpx 上传一个真实中文 md 文件（含四君子汤/归脾汤内容），轮询状态至 `就绪`：

```python
import httpx, time
content = "四君子汤由人参、白术、茯苓、炙甘草组成，功用益气健脾。\n归脾汤主治心脾两虚。"
r = httpx.post("http://localhost:8000/api/documents",
               files={"file": ("验收语料.md", content.encode(), "text/markdown")},
               data={"topic": "内科"}, timeout=60)
doc_id = r.json()["id"]
for _ in range(30):
    st = httpx.get(f"http://localhost:8000/api/documents/{doc_id}/parse-status").json()
    if st["status"] in ("就绪", "失败"): break
    time.sleep(1)
print(st)
```

Expected: `status=就绪, chunk_count>=1`

- [ ] **Step 3: 新文档可被问答检索（闭环验证）**

```python
with httpx.stream("POST", "http://localhost:8000/api/chat/stream",
                  json={"question": "归脾汤主治什么？"}, timeout=90) as r:
    raw = "".join(r.iter_text())
assert "归脾汤" in raw and "心脾两虚" in raw
```

Expected: 回答命中新上传文档内容（证明入库→检索闭环）。

- [ ] **Step 4: 抽取 → 候选 → 审核 → 发布闭环**

```python
from app.graph.extractor import extract_triples, save_candidates
triples = extract_triples("四君子汤由人参、白术、茯苓、炙甘草组成。")
n = save_candidates(triples, source_doc="验收语料.md")
# 候选列表可见且 status=候选
cands = httpx.get("http://localhost:8000/api/graph/candidates").json()
# 审核发布其中一条
httpx.post("http://localhost:8000/api/graph/candidates/approve",
           json={"kind": "edge", "source": "四君子汤", "relation": "组成", "target": "人参"})
# 发布后候选列表不再包含该条；图谱邻居查询可见
```

Expected: 候选 → 审核 → 发布状态流转正确（问答只查已发布，候选不污染）。

- [ ] **Step 5: 前端与浏览器验收**

`cd web && npm run dev`；浏览器：典籍知识库页（统计卡数字、上传弹窗 8 主题必选拦截、状态轮询到就绪、表格）→ 本草图谱页（左列表点击出图、6 类节点色、右详情、候选审核 Tab 发布/驳回）。

- [ ] **Step 6: 全量回归 + 归档 + 提交**

Run: `cd backend && .venv/Scripts/python -m pytest -v`（全绿）→ `cd web && npm run type-check && npm run build`（零错误）

写 `docs/superpowers/plans/stage4-verification.md`（上传/检索/审核/浏览器四组证据 + 数字），然后：

```bash
git add docs/superpowers/plans/stage4-verification.md
git commit -m "docs: stage 4 verification record"
```