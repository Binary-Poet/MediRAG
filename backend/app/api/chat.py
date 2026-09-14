"""API 路由层：阶段 1 普通问答接口（阶段 3 换 SSE /api/chat/stream）。"""
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.llm.chat import chat_completion
from app.llm.embedding import embed_texts
from app.retrieval.vector_store import get_store

router = APIRouter()

PROMPT_PATH = Path(__file__).resolve().parents[1] / "agent" / "prompts" / "answer_cn_tcm.txt"
TOP_K = 5


class AskBody(BaseModel):
    question: str = Field(min_length=1, max_length=500)


class Reference(BaseModel):
    chunk_id: str
    title: str
    doc_name: str
    chapter: str
    page_no: int
    score: float


class AskResponse(BaseModel):
    answer: str
    references: list[Reference]


@router.post("/chat/ask", response_model=AskResponse)
def ask(body: AskBody) -> AskResponse:
    """最小 RAG 闭环：向量化问题 → 检索 top5 → 组装 Prompt → 生成带引用回答。"""
    question = body.question.strip()

    # 1. 检索
    try:
        q_emb = embed_texts([question])[0]
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e)) from e
    hits = get_store().search(q_emb, top_k=TOP_K)

    if not hits:
        return AskResponse(
            answer="知识库中未检索到可靠依据。请先运行 python -m app.ingestion.pipeline 完成语料入库。",
            references=[],
        )

    # 2. 组装证据（编号与返回引用列表一一对应）
    evidence = "\n\n".join(
        f"[{i + 1}] 《{h['doc_name']}》{h['chapter']}（序号 {h['page_no']}）\n{h['title']}：{h['text']}"
        for i, h in enumerate(hits)
    )
    template = PROMPT_PATH.read_text(encoding="utf-8")
    prompt = template.format(evidence=evidence, question=question)

    # 3. 生成
    try:
        answer = chat_completion(system="你是中医药知识助手「本草智问」。", user=prompt)
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e)) from e

    return AskResponse(
        answer=answer,
        references=[
            Reference(
                chunk_id=h["chunk_id"],
                title=h["title"],
                doc_name=h["doc_name"],
                chapter=h["chapter"],
                page_no=h["page_no"],
                score=h["score"],
            )
            for h in hits
        ],
    )
