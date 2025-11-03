"""Pydantic models for the /chat endpoint."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field

from src.core.responses import ok


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


class ChatMetadata(BaseModel):
    """챗봇 응답 메타데이터."""

    mock: bool = Field(True, description="Mock 응답 여부")
    generated_at: datetime = Field(..., description="응답 생성 시각(UTC)")
    trace_id: UUID = Field(default_factory=uuid4, description="트레이싱 식별자")
    messages: list[ChatMessage] = Field(
        default_factory=list, description="사용자에게 노출할 메시지 목록"
    )


class ChatResponse(BaseModel):
    """챗봇 응답 스키마."""

    success: Literal[True] = Field(True, description="요청 성공 여부")
    type: ChatIntent = Field(..., description="생성된 응답 intent")
    category: str | None = Field(
        default=None, description="도메인 카테고리"
    )
    data: dict[str, Any] = Field(..., description="intent에 따른 상세 데이터")
    metadata: ChatMetadata | None = Field(
        default=None, description="추가 메타 정보"
    )

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "success": True,
                    "type": "informational",
                    "category": "loan_limit",
                    "data": {
                        "answer": "대출 한도는 소득과 신용등급에 따라 달라집니다.",
                        "sources": [
                            "https://example.com/loan-guidelines",
                            "https://example.com/credit-score",
                        ],
                    },
                    "metadata": {
                        "mock": True,
                        "generated_at": "2025-10-30T06:52:46.910280Z",
                        "trace_id": "ad7d1c28-6a2c-4a7b-86b7-5d7e65a9f6c3",
                        "messages": [
                            {
                                "role": "assistant",
                                "content": "정보형 답변을 생성했습니다.",
                            }
                        ],
                    },
                },
                {
                    "success": True,
                    "type": "calculational",
                    "category": "monthly_payment",
                    "data": {
                        "result": 32500000,
                        "currency": "KRW",
                        "explanation": "월 상환 가능액과 금리를 기준으로 산출한 예상 대출 한도입니다.",
                        "params": {
                            "loan_amount": 30000000,
                            "rate": 5.5,
                            "term_months": 36,
                        },
                    },
                    "metadata": {
                        "mock": True,
                        "generated_at": "2025-10-30T06:53:10.123456Z",
                        "trace_id": "f2e5f9ab-e268-474c-8a65-3a621ecf3a4d",
                        "messages": [
                            {
                                "role": "assistant",
                                "content": "계산형 답변을 생성했습니다.",
                            }
                        ],
                    },
                },
            ]
        }
    )


def build_chat_response(
    *,
    intent: ChatIntent,
    category: str | None,
    data: dict[str, Any],
    message: str,
    generated_at: datetime,
    mock: bool,
) -> ChatResponse:
    """표준 챗봇 응답을 생성한다."""

    metadata = ChatMetadata(
        mock=mock,
        generated_at=generated_at,
        messages=[ChatMessage(role="assistant", content=message)],
    )
    payload = ok(
        data=data,
        intent=intent,
        category=category,
        metadata=metadata.model_dump(),
    )
    return ChatResponse(**payload)


def build_mock_response(
    *,
    intent: ChatIntent,
    category: str | None,
    data: dict[str, Any],
    message: str,
    generated_at: datetime,
) -> ChatResponse:
    """기존 Mock 응답 빌더 (호환용)."""

    return build_chat_response(
        intent=intent,
        category=category,
        data=data,
        message=message,
        generated_at=generated_at,
        mock=True,
    )


__all__ = [
    "ChatIntent",
    "ChatMetadata",
    "ChatMessage",
    "ChatRequest",
    "ChatResponse",
    "build_chat_response",
    "build_mock_response",
]
