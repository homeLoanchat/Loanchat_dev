"""/chat 라우터."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter

from src.api.schemas import (
    ChatIntent,
    ChatRequest,
    ChatResponse,
    build_mock_response,
)

router = APIRouter(prefix="/api/chat", tags=["chat"])


@router.post(
    "",
    response_model=ChatResponse,
    response_model_exclude_none=True,
    summary="통합 챗봇 엔드포인트",
    description="정보형/계산형 intent에 따라 Mock 응답을 반환합니다.",
)
def chat_endpoint(payload: ChatRequest) -> ChatResponse:
    """정보형과 계산형 intent에 대해 샘플 응답을 반환한다."""

    generated_at = datetime.now(timezone.utc)

    payload_data: dict[str, Any]

    if payload.intent == ChatIntent.INFORMATIONAL:
        payload_data = {
            "type": payload.intent.value,
            "content": {
                "answer": "대출 한도는 소득과 신용등급에 따라 달라집니다.",
                "sources": [
                    "https://example.com/loan-guidelines",
                    "https://example.com/credit-score",
                ],
            },
        }
        message = "정보형 답변을 생성했습니다."
    else:
        payload_data = {
            "type": payload.intent.value,
            "content": {
                "result": 32500000,
                "currency": "KRW",
                "explanation": "월 상환 가능액과 금리를 기준으로 산출한 예상 대출 한도입니다.",
            },
        }
        message = "계산형 답변을 생성했습니다."

    # TODO(Iteration 2): MockRetriever/MockCompute를 DI로 주입해 intent별 실제 응답 생성
    return build_mock_response(
        intent=payload.intent,
        payload=payload_data,
        message=message,
        generated_at=generated_at,
    )
