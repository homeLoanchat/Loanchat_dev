"""/chat 라우터."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from src.api.schemas import (
    CalcPreview,
    ChatIntent,
    ChatRequest,
    ChatResponse,
    InfoPreview,
    OrchestrationPreview,
    RetrievalConfidence,
)
from src.core.responses import ErrorResponse
from src.orchestration import graph
from src.services import ChatService, get_chat_service, get_compute, get_retriever
from src.services.chat_service import ComputeRunner, RetrievalRunner

router = APIRouter(prefix="/api/chat", tags=["chat"])


@router.post(
    "",
    response_model=ChatResponse,
    response_model_exclude_none=True,
    summary="통합 챗봇 엔드포인트",
    description="정보형/계산형 intent에 따라 Retrieval/Compute 파이프라인을 실행합니다.",
    responses={
        400: {"model": ErrorResponse},
        422: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
def chat_endpoint(
    payload: ChatRequest,
    service: ChatService = Depends(get_chat_service),
) -> ChatResponse:
    """정보형과 계산형 intent에 대해 ChatService를 호출한다."""

    return service.handle(payload)


@router.post(
    "/preview",
    response_model=OrchestrationPreview,
    response_model_exclude_none=True,
    summary="Orchestration 미리보기",
    description="정보형/계산형 흐름에서 생성되는 중간 데이터를 확인합니다.",
)
def preview_orchestration(
    payload: ChatRequest,
    retriever: RetrievalRunner = Depends(get_retriever),
    compute: ComputeRunner = Depends(get_compute),
) -> OrchestrationPreview:
    """Orchestration 파이프라인 수행 결과를 미리보기로 제공한다."""

    intent = "calc" if payload.intent == ChatIntent.CALCULATIONAL else "info"
    state = graph.run_preview(
        query=payload.message,
        intent=intent,
        category=payload.category,
        params=payload.params,
        retriever=retriever,
        compute=compute,
    )

    if state.mode == "calc":
        calc_preview = CalcPreview(
            summary=state.response_message or state.calc.get("summary"),
            policy=state.calc.get("policy"),
            repayment=state.calc.get("repayment"),
            inputs=state.inputs,
            confidence=state.calc.get("confidence") or state.confidence,
            data=state.response_data,
        )
        return OrchestrationPreview(mode="calc", calc=calc_preview)

    confidence = (
        RetrievalConfidence.model_validate(state.confidence)
        if state.confidence
        else None
    )
    info_preview = InfoPreview(
        answer=state.answer,
        sources=[str(src) for src in state.sources],
        confidence=confidence,
        documents=state.docs,
        web_results=state.web_results,
        data=state.response_data,
    )
    return OrchestrationPreview(mode="info", info=info_preview)
