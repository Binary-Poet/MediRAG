"""急症词表拦截（方案 4.4-2）：问题命中急症症状时强制就医引导。"""

EMERGENCY_WORDS = [
    "胸痛", "胸口疼", "昏迷", "晕厥", "大出血", "休克", "孕妇出血",
    "孕妇腹痛", "呼吸困难", "咯血", "吐血", "便血", "黑便", "剧烈头痛",
    "突发瘫痪", "抽搐", "气道异物",
]


def detect_emergency(text: str) -> bool:
    """任意急症词命中即返回 True。"""
    return any(w in text for w in EMERGENCY_WORDS)