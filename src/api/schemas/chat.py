"""Pydantic models for the /chat endpoint."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, Field, ConfigDict


class ChatIntent(str, Enum):
    """지원하는 챗봇 응답 유형."""

    INFORMATIONAL = "informational"
    CALCULATIONAL = "calculational"


class ChatRequest(BaseModel):
    """챗봇 통합 엔드포인트 요청 스키마."""

    message: str = Field(..., description="사용자 입력 질문")
    intent: ChatIntent = Field(..., description="정보형/계산형 중 하나")
    category: str | None = Field(
        default=None,
        description="업무/도메인 분류 (예: 'loan_limit', 'interest_rate')",
        examples=["loan_limit"],
    )
    params: dict[str, Any] | None = Field(
        default=None,
        description="계산형 요청에 사용될 파라미터 집합",
        examples=[{"loan_amount": 30000000, "term_months": 36}],
    )

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "message": "대출 한도가 궁금해",
                    "intent": "informational",
                    "category": "loan_limit",
                },
                {
                    "message": "매달 상환 금액을 계산해줘",
                    "intent": "calculational",
                    "category": "monthly_payment",
                    "params": {"loan_amount": 30000000, "rate": 5.5, "term_months": 36},
                },
            ]
        }
    )


class ChatMessage(BaseModel):
    """대화 로그 항목."""

    role: Literal["assistant", "system", "user"] = Field(
        ..., description="메시지 역할"
    )
    content: str = Field(..., description="메시지 본문")


class ChatResult(BaseModel):
    """챗봇 응답 결과."""

    intent: ChatIntent = Field(..., description="생성된 응답 intent")
    payload: dict[str, Any] = Field(..., description="intent에 따른 상세 데이터")


class ChatMeta(BaseModel):
    """챗봇 응답 메타데이터."""

    mock: bool = Field(True, description="Mock 응답 여부")
    generated_at: datetime = Field(..., description="응답 생성 시각(UTC)")


class ChatResponse(BaseModel):
    """챗봇 응답 스키마."""

    result: ChatResult = Field(..., description="실제 응답 페이로드")
    messages: list[ChatMessage] = Field(
        default_factory=list, description="사용자에게 노출할 메시지 목록"
    )
    trace_id: UUID = Field(default_factory=uuid4, description="트레이싱 식별자")
    meta: ChatMeta = Field(..., description="추가 메타 정보")


def build_mock_response(
    *,
    intent: ChatIntent,
    payload: dict[str, Any],
    message: str,
    generated_at: datetime,
) -> ChatResponse:
    """Mock 데이터를 이용해 표준 응답 스키마를 생성한다."""

    return ChatResponse(
        result=ChatResult(intent=intent, payload=payload),
        messages=[ChatMessage(role="assistant", content=message)],
        meta=ChatMeta(mock=True, generated_at=generated_at),
    )
