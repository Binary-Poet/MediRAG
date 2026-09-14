"""LLM 基础设施：Embedding / Chat 客户端。

阶段 1 用 httpx 直调 OpenAI 兼容接口（SiliconFlow / DeepSeek / DashScope），
避免引入 openai SDK 依赖；阶段 3 Agentic 化时切换到 LangChain 的统一接口。
"""
