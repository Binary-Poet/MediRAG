"""安全兜底节点：急症词拦截 + 低置信度拒答 + 图谱豁免（方案 4.4）。"""
from app.agent.state import AgentState
from app.safety.emergency import detect_emergency

EMERGENCY_MESSAGE = (
    "您提到的情况可能属于急症，请立即就医或拨打 120，本系统不提供急诊建议，也不替代专业诊断。"
)
LOW_CONFIDENCE_MESSAGE = "知识库中未检索到可靠依据。请换个问题，或提供更具体的证候、方剂或中药名称。"


def safety(state: AgentState) -> dict:
    text = f"{state['question']} {' '.join(state.get('entity_names', []))}"
    if detect_emergency(text):
        return {"safety_flag": "emergency", "safety_message": EMERGENCY_MESSAGE}
    if state["intent"] == "chitchat":
        return {"safety_flag": "low_confidence", "safety_message": LOW_CONFIDENCE_MESSAGE,
                "answer": LOW_CONFIDENCE_MESSAGE}
    if (not state["evidence"] or state["low_confidence"]) and not state["graph_facts"]:
        return {"safety_flag": "low_confidence", "safety_message": LOW_CONFIDENCE_MESSAGE,
                "answer": LOW_CONFIDENCE_MESSAGE}
    return {"safety_flag": "ok", "safety_message": ""}
