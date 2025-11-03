# orchestration/graph.py
# 상대 import로 통일. 실행은 'cd src' 후 'python -m orchestration.graph'

from __future__ import annotations

from time import perf_counter
from typing import Any, Protocol, Literal, Optional

from src.core.metrics import track_latency

from src.core.exceptions import InvalidValueError

from .composer import render_answer
from .router import route
from .state import OrchestrationState

INFORMATIONAL_CATEGORIES = {"loan_limit", "interest_rate"}
CALCULATIONAL_CATEGORIES = {"monthly_payment"}


class RetrievalRunner(Protocol):
    def run(
        self,
        *,
        category: str | None,
        query: str,
        user_id: str | None = None,
    ) -> dict[str, Any]:
        ...


class ComputeRunner(Protocol):
    def run(
        self,
        *,
        category: str | None,
        params: dict[str, Any] | None,
        user_id: str | None = None,
    ) -> dict[str, Any]:
        ...


def run(
    *,
    query: str,
    intent: Literal["info", "calc"],
    category: Optional[str],
    params: Optional[dict[str, Any]],
    retriever: RetrievalRunner,
    compute: ComputeRunner,
) -> OrchestrationState:
    state = OrchestrationState(
        user_query=query,
        inputs=params or {},
        category=category,
    )
    if intent == "info":
        _validate_category(category, INFORMATIONAL_CATEGORIES)
    elif intent == "calc":
        _validate_category(category, CALCULATIONAL_CATEGORIES)

    route_started = perf_counter()
    state = route(
        state,
        retriever=retriever,
        compute=compute,
        intent_hint=intent,
    )
    route_elapsed = (perf_counter() - route_started) * 1000.0
    track_latency("orchestration_route", value=route_elapsed)
    state.metrics.setdefault("latency_ms", {})["route_ms"] = round(route_elapsed, 3)

    if state.mode not in {"info", "calc"} and not state.response_message:
        raise InvalidValueError("의도(intent)를 판별하지 못했습니다.", field="intent")

    compose_started = perf_counter()
    state.response_text = render_answer(state)
    compose_elapsed = (perf_counter() - compose_started) * 1000.0
    track_latency("composer", value=compose_elapsed)
    state.metrics.setdefault("latency_ms", {})["composer_ms"] = round(compose_elapsed, 3)

    return state


def run_preview(
    *,
    query: str,
    intent: Literal["info", "calc"],
    category: Optional[str],
    params: Optional[dict[str, Any]],
    retriever: RetrievalRunner,
    compute: ComputeRunner,
) -> OrchestrationState:
    return run(
        query=query,
        intent=intent,
        category=category,
        params=params,
        retriever=retriever,
        compute=compute,
    )


def _validate_category(category: Optional[str], allowed: set[str]) -> None:
    if category and category not in allowed:
        raise InvalidValueError(
            "지원하지 않는 category 입니다.",
            field="category",
            details={"category": category},
        )


if __name__ == "__main__":
    # 단독 실행 테스트
    dummy_retriever = lambda **kwargs: {
        "answer": "예시 답변입니다.",
        "sources": ["https://example.com"],
        "documents": [],
        "web_results": [],
        "confidence": {"passed": True, "reason": None, "thresholds": {}},
    }

    class _DummyCompute(ComputeRunner):
        def run(self, *, category: str | None, params: dict[str, Any] | None, user_id: str | None = None) -> dict[str, Any]:
            return {
                "summary": "예상 한도는 3억원입니다.",
                "policy": {},
                "repayment": {"monthly_payment": 950000, "term_months": 360},
                "confidence": {"derived_from": "policy_limits"},
            }

    dummy_compute = _DummyCompute()

    info_state = run(
        query="전세자금대출 한도가 궁금해",
        intent="info",
        category="loan_limit",
        params=None,
        retriever=dummy_retriever,  # type: ignore[arg-type]
        compute=dummy_compute,
    )
    print(info_state.response_text)

    calc_state = run(
        query="6억짜리 집이면 한도 얼마야?",
        intent="calc",
        category="monthly_payment",
        params={"loan_amount": 300000000, "rate": 3.8, "term_months": 360},
        retriever=dummy_retriever,  # type: ignore[arg-type]
        compute=dummy_compute,
    )
    print(calc_state.response_text)
