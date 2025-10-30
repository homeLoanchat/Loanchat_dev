"""Chat 서비스 계층.

Iteration 2에서는 라우터에서 비즈니스 로직을 분리하고, 향후 실제
Retrieval/Compute 모듈을 주입할 수 있는 구조를 마련한다.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Protocol

from src.api.schemas import (
    ChatIntent,
    ChatRequest,
    ChatResponse,
    build_mock_response,
)


class RetrievalRunner(Protocol):
    """정보형 intent에 사용되는 검색 모듈 인터페이스."""

    def run(
        self,
        *,
        category: str | None,
        query: str,
        user_id: str | None = None,
    ) -> dict[str, Any]:
        ...


class ComputeRunner(Protocol):
    """계산형 intent에 사용되는 연산 모듈 인터페이스."""

    def run(
        self,
        *,
        category: str | None,
        params: dict[str, Any] | None,
        user_id: str | None = None,
    ) -> dict[str, Any]:
        ...


class MockRetriever:
    """Iteration 2에서 사용되는 기본 Mock Retrieval."""

    def run(
        self,
        *,
        category: str | None,
        query: str,
        user_id: str | None = None,
    ) -> dict[str, Any]:
        return {
            "type": ChatIntent.INFORMATIONAL.value,
            "category": category or "general",
            "data": {
                "answer": "대출 한도는 소득과 신용등급에 따라 달라집니다.",
                "sources": [
                    "https://example.com/loan-guidelines",
                    "https://example.com/credit-score",
                ],
            },
        }


class MockCompute:
    """Iteration 2에서 사용되는 기본 Mock Compute."""

    def run(
        self,
        *,
        category: str | None,
        params: dict[str, Any] | None,
        user_id: str | None = None,
    ) -> dict[str, Any]:
        return {
            "type": ChatIntent.CALCULATIONAL.value,
            "category": category or "general",
            "data": {
                "result": 32_500_000,
                "currency": "KRW",
                "explanation": "월 상환 가능액과 금리를 기준으로 산출한 예상 대출 한도입니다.",
                "params": params or {},
            },
        }


class ChatService:
    """챗봇 intent에 따라 적절한 모듈을 호출한다."""

    def __init__(
        self,
        *,
        retriever: RetrievalRunner,
        compute: ComputeRunner,
    ) -> None:
        self._retriever = retriever
        self._compute = compute

    def handle(self, request: ChatRequest) -> ChatResponse:
        """요청 intent에 맞춰 Mock 응답을 생성한다."""

        generated_at = datetime.now(timezone.utc)

        if request.intent == ChatIntent.INFORMATIONAL:
            retrieval_payload = self._retriever.run(
                category=request.category,
                query=request.message,
            )
            return build_mock_response(
                intent=request.intent,
                payload=retrieval_payload,
                message="정보형 답변을 생성했습니다.",
                generated_at=generated_at,
            )

        compute_payload = self._compute.run(
            category=request.category,
            params=request.params,
        )
        return build_mock_response(
            intent=request.intent,
            payload=compute_payload,
            message="계산형 답변을 생성했습니다.",
            generated_at=generated_at,
        )


def get_chat_service() -> ChatService:
    """FastAPI DI에 사용할 기본 ChatService 제공자."""

    return ChatService(retriever=MockRetriever(), compute=MockCompute())
