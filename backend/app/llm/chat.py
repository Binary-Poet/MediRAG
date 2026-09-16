"""Chat 客户端：OpenAI 兼容 /chat/completions。

按 LLM_VENDOR 切换 DeepSeek（主力）/ Qwen（DashScope 兼容模式），
对应合并方案"多模型路由"的阶段 1 简化版。
"""
import json

import httpx

from app.config import get_settings


def _endpoint(vendor: str | None = None, model: str | None = None) -> tuple[str, str, str]:
    """返回 (base_url, api_key, model)；vendor/model 显式覆盖 settings（推理配置页切模型）。
    model="qwen-plus" → vendor=qwen；model="deepseek-chat" → vendor=deepseek。"""
    s = get_settings()
    if model == "qwen-plus":
        vendor = "qwen"
    elif model == "deepseek-chat":
        vendor = "deepseek"
    vendor = vendor or s.llm_vendor
    if vendor == "qwen":
        if not s.dashscope_api_key:
            raise RuntimeError("DASHSCOPE_API_KEY 未配置（LLM_VENDOR=qwen）")
        return s.dashscope_base_url, s.dashscope_api_key, model or s.llm_model_alt
    if not s.deepseek_api_key:
        raise RuntimeError("DEEPSEEK_API_KEY 未配置，请在 backend/.env 填入")
    return s.deepseek_base_url, s.deepseek_api_key, model or s.llm_model_main


def chat_completion(system: str, user: str, temperature: float = 0.3,
                    vendor: str | None = None, model: str | None = None) -> str:
    """单轮对话补全，返回首个 choice 的文本。"""
    base_url, api_key, model = _endpoint(vendor=vendor, model=model)
    resp = httpx.post(
        f"{base_url}/chat/completions",
        headers={"Authorization": f"Bearer {api_key}"},
        json={
            "model": model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": temperature,
        },
        timeout=120,
    )
    try:
        resp.raise_for_status()
    except httpx.HTTPError as e:
        raise RuntimeError(f"Chat 服务调用失败：{e}") from e
    return resp.json()["choices"][0]["message"]["content"]


def chat_completion_stream(system: str, user: str, temperature: float = 0.3,
                           vendor: str | None = None, model: str | None = None):
    """流式对话补全：逐 token 产出文本。返回生成器。"""
    base_url, api_key, model = _endpoint(vendor=vendor, model=model)
    with httpx.stream(
        "POST", f"{base_url}/chat/completions",
        headers={"Authorization": f"Bearer {api_key}"},
        json={
            "model": model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": temperature,
            "stream": True,
        },
        timeout=120,
    ) as resp:
        try:
            resp.raise_for_status()
        except httpx.HTTPError as e:
            raise RuntimeError(f"Chat 服务调用失败：{e}") from e
        for line in resp.iter_lines():
            if not line or not line.startswith("data:"):
                continue
            payload = line[len("data:"):].strip()
            if payload == "[DONE]":
                break
            try:
                data = json.loads(payload)
            except (json.JSONDecodeError, ValueError):
                continue
            delta = data.get("choices", [{}])[0].get("delta", {}).get("content")
            if delta:
                yield delta
