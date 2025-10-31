"""Chat 서비스 계층."""

from __future__ import annotations

from datetime import datetime, timezone
from functools import lru_cache
from typing import Any, Protocol

from src.api.schemas import (
    ChatIntent,
    ChatRequest,
    ChatResponse,
    build_chat_response,
)
from src.core.exceptions import InvalidValueError
from src.retrieval.pipeline import RetrievalPipeline
from src.services.retriever_service import PipelineRetriever


INFORMATIONAL_CATEGORIES = {"loan_limit", "interest_rate"}
CALCULATIONAL_CATEGORIES = {"monthly_payment"}


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

    is_mock = True

    def run(
        self,
        *,
        category: str | None,
        query: str,
        user_id: str | None = None,
    ) -> dict[str, Any]:
        return {
            "answer": "대출 한도는 소득과 신용등급에 따라 달라집니다.",
            "sources": [
                "https://example.com/loan-guidelines",
                "https://example.com/credit-score",
            ],
            "query": query,
        }


class MockCompute:
    """Iteration 2에서 사용되는 기본 Mock Compute."""

    is_mock = True

    def run(
        self,
        *,
        category: str | None,
        params: dict[str, Any] | None,
        user_id: str | None = None,
    ) -> dict[str, Any]:
        return {
            "result": 32_500_000,
            "currency": "KRW",
            "explanation": "월 상환 가능액과 금리를 기준으로 산출한 예상 대출 한도입니다.",
            "params": params or {},
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
            if request.category and request.category not in INFORMATIONAL_CATEGORIES:
                raise InvalidValueError(
                    "지원하지 않는 category 입니다.",
                    field="category",
                    details={"category": request.category},
                )

            retrieval_payload = self._retriever.run(
                category=request.category,
                query=request.message,
            )
            return build_chat_response(
                intent=request.intent,
                category=request.category,
                data=retrieval_payload,
                message="정보형 답변을 생성했습니다.",
                generated_at=generated_at,
                mock=getattr(self._retriever, "is_mock", False),
            )

        if request.category and request.category not in CALCULATIONAL_CATEGORIES:
            raise InvalidValueError(
                "지원하지 않는 category 입니다.",
                field="category",
                details={"category": request.category},
            )

        if not request.params:
            raise InvalidValueError(
                "계산형 intent에는 params가 필요합니다.",
                field="params",
            )

        compute_payload = self._compute.run(
            category=request.category,
            params=request.params,
        )
        return build_chat_response(
            intent=request.intent,
            category=request.category,
            data=compute_payload,
            message="계산형 답변을 생성했습니다.",
            generated_at=generated_at,
            mock=getattr(self._compute, "is_mock", False),
        )


@lru_cache(maxsize=1)
def _get_retrieval_pipeline() -> RetrievalPipeline:
    return RetrievalPipeline()


@lru_cache(maxsize=1)
def _get_retriever() -> RetrievalRunner:
    return PipelineRetriever(pipeline=_get_retrieval_pipeline())


@lru_cache(maxsize=1)
def _get_compute() -> ComputeRunner:
    return MockCompute()


@lru_cache(maxsize=1)
def get_chat_service() -> ChatService:
    """FastAPI DI에 사용할 기본 ChatService 제공자."""

    return ChatService(retriever=_get_retriever(), compute=_get_compute())
