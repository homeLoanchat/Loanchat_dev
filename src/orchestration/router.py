# orchestration/router.py
# 질문을 calc/info로 분류하는 최소 휴리스틱

from .state import OrchestrationState

_CALC_KEYS = ("얼마", "한도", "가능", "LTV", "DTI", "DSR", "상환", "금리", "만기")

def route(state: OrchestrationState) -> OrchestrationState:
    q = state.user_query
    state.mode = "calc" if any(k in q for k in _CALC_KEYS) else "info"
    return state
