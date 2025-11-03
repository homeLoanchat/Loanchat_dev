# orchestration/router.py
# 질문을 calc/info로 분류하는 최소 휴리스틱

from typing import Literal, Optional

from .state import OrchestrationState

_CALC_KEYS = ("얼마", "한도", "가능", "LTV", "DTI", "DSR", "상환", "금리", "만기")


def route(
    state: OrchestrationState,
    *,
    intent: Optional[Literal["calc", "info"]] = None,
) -> OrchestrationState:
    if intent is not None:
        state.mode = intent
        return state

    q = state.user_query
    state.mode = "calc" if any(k in q for k in _CALC_KEYS) else "info"
    return state
