"""SSE 流式问答接口（合并方案 4.3 事件协议）。"""
import json

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.agent.memory import get_history, new_session, upsert_message
from app.agent.nodes.safety import LOW_CONFIDENCE_MESSAGE
from app.agent.workflow import get_agent
from app.llm.chat import chat_completion_stream

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
    }


@router.post("/chat/stream")
def chat_stream(body: StreamBody) -> StreamingResponse:
    session_id = body.session_id or new_session()
    graph = get_agent()
    initial = _initial_state(body, session_id)

    def gen():
        final = dict(initial)
        try:
            for node_name, update in graph.stream(initial, stream_mode="updates"):
                for key, val in update.items():
                    if key == "trace":
                        final["trace"] = final.get("trace", []) + val
                    else:
                        final[key] = val
                if "trace" in update:
                    for ev in update["trace"]:
                        yield sse("step", ev)
        except RuntimeError as e:
            yield sse("error", {"detail": str(e)})
            return

        # 生成阶段（异常收口：LLM/网络错误 → 显式 error 事件，跳过 references/done）
        try:
            if final["safety_flag"] == "emergency":
                yield sse("safety", {"type": "emergency", "message": final["safety_message"]})
                collected = []
                for chunk in chat_completion_stream(system="你是中医药知识助手。", user=final["prompt"], temperature=0.3):
                    collected.append(chunk)
                    yield sse("token", {"text": chunk})
                final["answer"] = "".join(collected)
            elif final["safety_flag"] == "low_confidence":
                # 正常流：safety 节点已产出 safety_message/answer；兜底以防只置了 flag
                msg = final["safety_message"] or final["answer"] or LOW_CONFIDENCE_MESSAGE
                yield sse("safety", {"type": "low_confidence", "message": msg})
                yield sse("token", {"text": final["answer"] or msg})
            else:
                collected = []
                for chunk in chat_completion_stream(system="你是中医药知识助手「本草智问」。", user=final["prompt"], temperature=0.3):
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
