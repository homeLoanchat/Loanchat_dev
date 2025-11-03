"""Chat 서비스 계층."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from functools import lru_cache
from typing import Any, Protocol

from src.api.schemas import (
    ChatIntent,
    ChatRequest,
    ChatResponse,
    build_chat_response,
)
from src.orchestration import graph
from src.retrieval.pipeline import RetrievalPipeline
from src.services.compute_service import LoanComputationService
from src.services.retriever_service import PipelineRetriever

logger = logging.getLogger(__name__)


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
        """Orchestration 그래프를 호출해 응답을 생성한다."""

        generated_at = datetime.now(timezone.utc)

        logger.info(
            "ChatService.handle intent=%s category=%s user_params=%s",
            request.intent,
            request.category,
            bool(request.params),
        )

        orchestration_intent = (
            "calc" if request.intent == ChatIntent.CALCULATIONAL else "info"
        )
        state = graph.run(
            query=request.message,
            intent=orchestration_intent,
            category=request.category,
            params=request.params,
            retriever=self._retriever,
            compute=self._compute,
        )

        provider = self._compute if state.mode == "calc" else self._retriever
        message = state.response_text or state.response_message or "응답을 생성했습니다."

        return build_chat_response(
            intent=request.intent,
            category=request.category,
            data=state.response_data,
            message=message,
            generated_at=generated_at,
            mock=getattr(provider, "is_mock", False),
            confidence=state.confidence,
        )


@lru_cache(maxsize=1)
def _get_retrieval_pipeline() -> RetrievalPipeline:
    return RetrievalPipeline()


@lru_cache(maxsize=1)
def _get_retriever() -> RetrievalRunner:
    return PipelineRetriever(pipeline=_get_retrieval_pipeline())


@lru_cache(maxsize=1)
def _get_compute() -> ComputeRunner:
    return LoanComputationService()


def get_retriever() -> RetrievalRunner:
    return _get_retriever()


def get_compute() -> ComputeRunner:
    return _get_compute()


def get_chat_service() -> ChatService:
    """FastAPI DI에 사용할 기본 ChatService 제공자."""

    return ChatService(retriever=get_retriever(), compute=get_compute())
