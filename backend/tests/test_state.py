def test_agent_state_has_required_fields():
    from app.agent.state import AgentState
    assert AgentState.__annotations__["question"] is str
    assert AgentState.__annotations__["intent"] is str
    assert AgentState.__annotations__["plan"] is list
    assert AgentState.__annotations__["reflect_count"] is int
    assert AgentState.__annotations__["safety_flag"] == (str | None)  # 可先置 None 再写 "emergency"/"low_confidence"/"ok"
    from typing import get_args
    from operator import add
    # Python 3.12 下 get_origin(Annotated[...]) 返回 typing.Annotated，故用 get_args 校验底层类型与 reducer
    assert get_args(AgentState.__annotations__["trace"])[0] is list      # Annotated[list, add]
    assert get_args(AgentState.__annotations__["trace"])[1] is add       # langgraph 累加 reducer