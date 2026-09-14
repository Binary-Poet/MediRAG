"""API 路由层：三路混合检索 + RRF + Rerank 问答（阶段 3 换 SSE /api/chat/stream）。"""
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.config import get_settings
from app.graph.entity_recognizer import recognize_entities
from app.graph.neo4j_client import get_graph
from app.llm.chat import chat_completion
from app.llm.embedding import embed_texts
from app.llm.rerank import rerank
from app.retrieval.keyword import get_keyword_index
from app.retrieval.rrf import rrf_fuse
from app.retrieval.vector_store import get_store

router = APIRouter()

PROMPT_PATH = Path(__file__).resolve().parents[1] / "agent" / "prompts" / "answer_cn_tcm.txt"


class AskBody(BaseModel):
    question: str = Field(min_length=1, max_length=500)


class Reference(BaseModel):
    chunk_id: str
    title: str
    doc_name: str
    chapter: str
    page_no: int
    score: float


class GraphFact(BaseModel):
    source: str
    relation: str
    target: str
    source_type: str
    target_type: str


class TraceUnderstand(BaseModel):
    raw: str
    rewritten: str
    entities: list[str]


class TraceRetrieve(BaseModel):
    vector_n: int
    keyword_n: int
    graph_n: int
    entity_n: int


class TraceFuse(BaseModel):
    candidate_n: int
    method: str = "RRF"


class TraceRerank(BaseModel):
    evidence_n: int
    confidence: float
    status: str


class Trace(BaseModel):
    understand: TraceUnderstand
    retrieve: TraceRetrieve
    fuse: TraceFuse
    rerank: TraceRerank


class AskResponse(BaseModel):
    answer: str
    references: list[Reference]
    graph_facts: list[GraphFact]
    trace: Trace


def _fallback_response(question: str) -> AskResponse:
    return AskResponse(
        answer="知识库中未检索到可靠依据。请换个问题或稍后再试。",
        references=[],
        graph_facts=[],
        trace=Trace(
            understand=TraceUnderstand(raw=question, rewritten=question, entities=[]),
            retrieve=TraceRetrieve(vector_n=0, keyword_n=0, graph_n=0, entity_n=0),
            fuse=TraceFuse(candidate_n=0),
            rerank=TraceRerank(evidence_n=0, confidence=0.0, status="知识库未匹配"),
        ),
    )


@router.post("/chat/ask", response_model=AskResponse)
def ask(body: AskBody) -> AskResponse:
    """三路混合检索问答：实体识别 → 向量+关键词+图谱 → RRF → Rerank → 生成。"""
    s = get_settings()
    question = body.question.strip()

    # 1. 问句理解：实体识别（词表来自图谱已发布节点；LLM 改写随阶段 3）
    vocab = get_graph().all_entities()
    entities = recognize_entities(question, vocab)
    entity_names = [e["name"] for e in entities]

    # 2. 三路并行召回（图谱证据独立，不参与 RRF）
    try:
        q_emb = embed_texts([question])[0]
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e)) from e
    vector_hits = get_store().search(q_emb, top_k=s.semantic_k)
    keyword_hits = get_keyword_index().search(question, top_k=s.keyword_k)
    graph_facts = get_graph().neighbors(entity_names, hop=1)

    # 3. RRF 融合（向量 + 关键词）
    fused = rrf_fuse([vector_hits, keyword_hits], k=s.rrf_k)[: s.fuse_candidate]

    # 4. 精排取最终证据
    ranked = rerank(
        question,
        [f"{c['title']}：{c['text']}" for c in fused],
        top_n=s.rerank_top_n,
    )
    evidence = [
        {**fused[r["index"]], "score": r["score"]} for r in ranked
    ]

    # 5. 置信度兜底（双重条件：文献证据与图谱事实都没有才拒答）
    if not evidence and not graph_facts:
        return _fallback_response(question)

    # 6. 组装 Prompt：图谱事实 + 文献证据
    graph_block = "\n".join(
        f"{f['source']} --{f['relation']}--> {f['target']}" for f in graph_facts
    ) or "（无）"
    evidence_block = "\n\n".join(
        f"[{i + 1}] 《{h['doc_name']}》{h['chapter']}（序号 {h['page_no']}）\n{h['title']}：{h['text']}"
        for i, h in enumerate(evidence)
    )
    template = PROMPT_PATH.read_text(encoding="utf-8")
    prompt = template.format(graph_facts=graph_block, evidence=evidence_block, question=question)

    # 7. 生成
    try:
        answer = chat_completion(system="你是中医药知识助手「本草智问」。", user=prompt)
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e)) from e

    confidence = evidence[0]["score"] if evidence else 0.0
    return AskResponse(
        answer=answer,
        references=[
            Reference(
                chunk_id=h["chunk_id"], title=h["title"], doc_name=h["doc_name"],
                chapter=h["chapter"], page_no=h["page_no"], score=h["score"],
            )
            for h in evidence
        ],
        graph_facts=[GraphFact(**f) for f in graph_facts],
        trace=Trace(
            understand=TraceUnderstand(raw=question, rewritten=question, entities=entity_names),
            retrieve=TraceRetrieve(
                vector_n=len(vector_hits), keyword_n=len(keyword_hits),
                graph_n=len(graph_facts), entity_n=len(entity_names),
            ),
            fuse=TraceFuse(candidate_n=len(fused)),
            rerank=TraceRerank(
                evidence_n=len(evidence), confidence=confidence,
                status="证据充分，正常生成",
            ),
        ),
    )