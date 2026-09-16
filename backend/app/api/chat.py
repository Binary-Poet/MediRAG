"""SSE 流式问答接口（合并方案 4.3 事件协议）。"""
import json

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.agent.memory import get_history, new_session, upsert_message
from app.agent.nodes.safety import LOW_CONFIDENCE_MESSAGE
from app.agent.workflow import get_agent
from app.db import session_scope
from app.llm.chat import chat_completion_stream
from app.models.retrieval_log import RetrievalLog
from app.services.inference_config import load_inference_config

router = APIRouter()


class StreamBody(BaseModel):
    question: str = Field(min_length=1, max_length=500)
    session_id: str | None = Field(default=None, max_length=64)


def sse(event: str, data: dict | str) -> str:
    payload = data if isinstance(data, str) else json.dumps(data, ensure_ascii=False)
    return f"event: {event}\ndata: {payload}\n\n"


def _initial_state(body: StreamBody, session_id: str) -> dict:
    return {
        "question": body.question, "session_id": session_id,
        "chat_history": get_history(session_id), "rewritten_query": body.question,
        "entities": [], "entity_names": [], "intent": "", "plan": [],
        "vector_hits": [], "keyword_hits": [], "graph_facts": [], "fused": [],
        "evidence": [], "confidence": 0.0, "low_confidence": False, "reflect_count": 0,
        "safety_flag": None, "safety_message": "", "prompt": "", "answer": "",
        "trace": [],
        "inference": load_inference_config(),
    }


@router.post("/chat/stream")
def chat_stream(body: StreamBody) -> StreamingResponse:
    session_id = body.session_id or new_session()
    graph = get_agent()
    initial = _initial_state(body, session_id)

    def gen():
        final = dict(initial)
        try:
            # langgraph 1.x stream_mode="updates" 逐 chunk 产出 {node_name: update} 单键 dict；
            # 元组 (node_name, update) 为 0.x 形状，兼容兜底。
            for chunk in graph.stream(initial, stream_mode="updates"):
                items = chunk.items() if isinstance(chunk, dict) else [chunk]
                for node_name, update in items:
                    for key, val in update.items():
                        if key == "trace":
                            final["trace"] = final.get("trace", []) + val
                        else:
                            final[key] = val
                    if "trace" in update:
                        for ev in update["trace"]:
                            yield sse("step", ev)
        except Exception as e:
            yield sse("error", {"detail": str(e)})
            return

        # 生成阶段（异常收口：LLM/网络错误 → 显式 error 事件，跳过 references/done）
        try:
            if final["safety_flag"] == "emergency":
                yield sse("safety", {"type": "emergency", "message": final["safety_message"]})
                emg_system = "你是中医药知识助手。用户描述了可能的急症情况，请务必在回答开头用加粗文字明确提示立即就医或拨打 120，再提供知识性说明。"
                collected = []
                cfg = final.get("inference") or {}
                for chunk in chat_completion_stream(system=emg_system, user=final["prompt"],
                                                    temperature=cfg.get("answer_temp", 0.3),
                                                    model=cfg.get("model")):
                    collected.append(chunk)
                    yield sse("token", {"text": chunk})
                final["answer"] = "".join(collected)
            elif final["safety_flag"] == "low_confidence":
                # 低置信分支无 LLM 生成：只发 safety 事件，前端以框渲染兜底话术
                msg = final["safety_message"] or final["answer"] or LOW_CONFIDENCE_MESSAGE
                yield sse("safety", {"type": "low_confidence", "message": msg})
            else:
                collected = []
                cfg = final.get("inference") or {}
                for chunk in chat_completion_stream(system="你是中医药知识助手「本草智问」。", user=final["prompt"],
                                                    temperature=cfg.get("answer_temp", 0.3),
                                                    model=cfg.get("model")):
                    collected.append(chunk)
                    yield sse("token", {"text": chunk})
                final["answer"] = "".join(collected)
        except Exception as e:  # 生成阶段异常收口：LLM/网络错误 → 显式 error 事件
            yield sse("error", {"detail": f"生成阶段失败：{e}"})
            return

        refs = [
            {"chunk_id": c["chunk_id"], "title": c["title"], "doc_name": c["doc_name"],
             "chapter": c["chapter"], "page_no": c["page_no"], "score": c["score"]}
            for c in final["evidence"]
        ]
        yield sse("references", {"docs": refs, "graph_facts": final["graph_facts"]})

        try:
            with session_scope() as s:
                s.add(RetrievalLog(
                    session_id=session_id,
                    intent=final.get("intent", ""),
                    vector_n=len(final.get("vector_hits", [])),
                    keyword_n=len(final.get("keyword_hits", [])),
                    graph_n=len(final.get("graph_facts", [])),
                    evidence_n=len(final.get("evidence", [])),
                    confidence=float(final.get("confidence", 0.0)),
                    is_fallback=final.get("safety_flag") in ("low_confidence", "emergency"),
                ))
        except Exception:
            pass  # 日志失败不影响问答结果

        yield sse("done", {"message_id": session_id, "metrics": {
            "vector_n": len(final.get("vector_hits", [])),
            "graph_n": len(final.get("graph_facts", [])),
            "evidence_n": len(final["evidence"]),
            "reflect_count": final.get("reflect_count", 0),
        }})

        upsert_message(session_id, "user", body.question)
        if final["answer"]:
            upsert_message(session_id, "assistant", final["answer"])

    return StreamingResponse(gen(), media_type="text/event-stream")
