# orchestration/graph.py
# 상대 import로 통일. 실행은 'cd src' 후 'python -m orchestration.graph'

from .state import OrchestrationState
from .router import route
from .composer import render_answer

def run(query: str, inputs: dict | None = None) -> str:
    state = OrchestrationState(user_query=query, inputs=inputs or {})
    state = route(state)

    if state.mode == "calc":
        # 더미 계산 결과(계산 엔진 붙기 전 테스트용)
        state.calc = {
            "limit_kr": "2.85억",
            "rate": 3.9,
            "term_years": 35,
            "repay_type": "원리금균등",
        }
        state.sources = [{"name": "금감원 금융상품비교공시", "date": "2024.03.30"}]

    return render_answer(state)

if __name__ == "__main__":
    # 단독 실행 테스트
    print(run("6억짜리 집이면 한도 얼마야?", {"house_price": 600_000_000}))
