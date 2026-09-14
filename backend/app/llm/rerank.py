"""Rerank 客户端：SiliconFlow /rerank（BAAI/bge-reranker-v2-m3，OpenAI 兼容网关）。"""
import httpx

from app.config import get_settings


def rerank(query: str, documents: list[str], top_n: int = 5) -> list[dict]:
    """按相关度降序返回 [{'index': i, 'score': s}]，index 指向原 documents 下标。"""
    if not documents:
        return []
    s = get_settings()
    if not s.siliconflow_api_key:
        raise RuntimeError("SILICONFLOW_API_KEY 未配置，请在 backend/.env 填入")
    try:
        resp = httpx.post(
            f"{s.siliconflow_base_url}/rerank",
            headers={"Authorization": f"Bearer {s.siliconflow_api_key}"},
            json={"model": s.rerank_model, "query": query,
                  "documents": documents, "top_n": min(top_n, len(documents))},
            timeout=60,
        )
        resp.raise_for_status()
        results = resp.json()["results"]
    except httpx.HTTPError as e:
        raise RuntimeError(f"精排服务调用失败：{e}") from e
    except (ValueError, KeyError) as e:
        raise RuntimeError(f"精排服务调用失败：{e}") from e
    return [{"index": r["index"], "score": r["relevance_score"]} for r in results]