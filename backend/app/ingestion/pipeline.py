"""文档入库流水线：解析 → 切片 → 向量化 → 入库。

阶段 1 支持项目内置的 tcm_corpus.md（带 【来源】…·…·[NNNN] 标记的种子语料）。
阶段 4 扩展为多格式解析分发（parsers.py）。
CLI 用法（backend/ 下）：
    python -m app.ingestion.pipeline
"""
import re
from pathlib import Path

from app.llm.embedding import embed_texts
from app.retrieval.vector_store import get_store

from app.db import session_scope
from app.models.document import Document

from app.ingestion.parsers import ParseError, parse_document
from app.ingestion.splitter import split_text
from app.retrieval.keyword import rebuild_keyword_index

# 默认语料路径：backend/../data/corpus/tcm_corpus.md
DEFAULT_CORPUS = Path(__file__).resolve().parents[3] / "data" / "corpus" / "tcm_corpus.md"

# 匹配【来源】中药方剂学基础 · 第1节 · [0001]
SOURCE_PATTERN = re.compile(r"^【来源】(.+?)\s*·\s*(.+?)\s*·\s*\[(\d+)\]\s*$")


def load_corpus(path: Path = DEFAULT_CORPUS) -> list[dict]:
    """解析种子语料：按 ### 词条切片，提取来源/章节/序号元数据。"""
    chunks: list[dict] = []
    current: dict | None = None
    body_lines: list[str] = []

    def _flush() -> None:
        if current is not None:
            current["text"] = "\n".join(body_lines).strip()

    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if line.startswith("### "):
            _flush()
            current = {
                "chunk_id": "",
                "title": line[4:].strip(),
                "doc_name": "",
                "chapter": "",
                "page_no": 0,
                "topic": "综合典籍",
                "text": "",
            }
            body_lines = []
            chunks.append(current)
        elif current is not None and (m := SOURCE_PATTERN.match(line)):
            current["doc_name"] = m.group(1).strip()
            current["chapter"] = m.group(2).strip()
            current["page_no"] = int(m.group(3))
            current["chunk_id"] = f"{m.group(1).strip()}#{m.group(3)}"
        elif current is not None:
            body_lines.append(raw)
    _flush()

    # 丢弃缺来源标记的非法切片
    return [c for c in chunks if c["chunk_id"] and c["text"]]


def run_ingestion(corpus_path: Path = DEFAULT_CORPUS) -> dict:
    """全量入库：切片 → 向量化 → upsert → 持久化。返回统计信息。"""
    chunks = load_corpus(corpus_path)
    if not chunks:
        raise RuntimeError(f"未解析到有效切片：{corpus_path}")

    embeddings = embed_texts([f"{c['title']}：{c['text']}" for c in chunks])
    items = [{**c, "embedding": e} for c, e in zip(chunks, embeddings)]

    store = get_store()
    total = store.upsert(items)
    store.save()
    return {"ingested": len(chunks), "total_in_store": total}


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
            if doc is not None:
                doc.status = "就绪"
                doc.chunk_count = len(chunks)
                doc.error_message = ""
        return {"chunks": len(chunks)}
    except Exception as e:
        with session_scope() as s:
            doc = s.get(Document, document_id)
            if doc is not None:
                doc.status = "失败"
                doc.error_message = str(e)[:500]
        return {"chunks": 0, "error": str(e)}


if __name__ == "__main__":
    stats = run_ingestion()
    print(f"[ingestion] 本次入库 {stats['ingested']} 条，库内共 {stats['total_in_store']} 条")
