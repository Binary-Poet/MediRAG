"""Embedding 客户端：SiliconFlow OpenAI 兼容 /embeddings（bge-m3, 1024 维）。"""
import httpx

from app.config import get_settings


def embed_texts(texts: list[str]) -> list[list[float]]:
    """批量向量化。返回顺序与输入一致。"""
    s = get_settings()
    if not s.siliconflow_api_key:
        raise RuntimeError("SILICONFLOW_API_KEY 未配置，请在 backend/.env 填入")
    resp = httpx.post(
        f"{s.siliconflow_base_url}/embeddings",
        headers={"Authorization": f"Bearer {s.siliconflow_api_key}"},
        json={"model": s.embed_model, "input": texts},
        timeout=60,
    )
    try:
        resp.raise_for_status()
    except httpx.HTTPError as e:
        raise RuntimeError(f"Embedding 服务调用失败：{e}") from e
    data = resp.json()["data"]
    # 按 index 排序，保证与输入顺序一致
    return [item["embedding"] for item in sorted(data, key=lambda d: d["index"])]
