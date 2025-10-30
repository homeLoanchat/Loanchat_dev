"""/chat 라우터."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from src.api.schemas import ChatRequest, ChatResponse
from src.core.responses import ErrorResponse
from src.services import ChatService, get_chat_service

router = APIRouter(prefix="/api/chat", tags=["chat"])


@router.post(
    "",
    response_model=ChatResponse,
    response_model_exclude_none=True,
    summary="통합 챗봇 엔드포인트",
    description="정보형/계산형 intent에 따라 Mock 응답을 반환합니다.",
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
