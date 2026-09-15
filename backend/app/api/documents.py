"""文档管理 API：上传（multipart）/列表/状态轮询/删除（方案第八节 + 规格 P0-6）。"""
import uuid
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, File, Form, HTTPException, UploadFile
from pydantic import BaseModel

from app.db import session_scope
from app.ingestion.parsers import SUPPORTED_EXTS
from app.ingestion.pipeline import ingest_document
from app.models.document import Document
from app.retrieval.keyword import rebuild_keyword_index
from app.retrieval.vector_store import get_store

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