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


class RetrievalConfidence(BaseModel):
    """검색 결과의 신뢰도 정보."""

    passed: bool = Field(..., description="임계치 충족 여부")
    reason: str | None = Field(default=None, description="임계치를 통과하지 못한 경우 원인")
    top_score: float | None = Field(default=None, description="최상위 문서 점수")
    top_score_normalized: float | None = Field(default=None, description="정규화된 최상위 점수")
    top_document_id: str | None = Field(default=None, description="최상위 문서 식별자")
    hits: int = Field(..., description="검색된 문서 수")
    thresholds: dict[str, float | int] = Field(
        default_factory=dict, description="임계치 기준값(min_score 등)"
    )

    model_config = ConfigDict(extra="allow")


class ChatMetadata(BaseModel):
    """챗봇 응답 메타데이터."""

    mock: bool = Field(True, description="Mock 응답 여부")
    generated_at: datetime = Field(..., description="응답 생성 시각(UTC)")
    trace_id: UUID = Field(default_factory=uuid4, description="트레이싱 식별자")
    messages: list[ChatMessage] = Field(
        default_factory=list, description="사용자에게 노출할 메시지 목록"
    )
    confidence: RetrievalConfidence | None = Field(
        default=None, description="검색 결과 신뢰도 평가 정보"
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
    confidence: dict[str, Any] | RetrievalConfidence | None = None,
) -> ChatResponse:
    """표준 챗봇 응답을 생성한다."""

    metadata = ChatMetadata(
        mock=mock,
        generated_at=generated_at,
        messages=[ChatMessage(role="assistant", content=message)],
        confidence=confidence,
    )
    payload = ok(
        data=data,
        intent=intent,
        category=category,
        metadata=metadata.model_dump(),
    )
    return ChatResponse(**payload)


class InfoPreview(BaseModel):
    """정보형 orchestration 미리보기."""

    answer: str | None = Field(default=None, description="Retrieval 요약/답변")
    sources: list[str] = Field(default_factory=list, description="출처 목록")
    confidence: RetrievalConfidence | None = Field(
        default=None, description="검색 신뢰도 정보"
    )
    documents: list[dict[str, Any]] = Field(
        default_factory=list, description="Retrieval 내부 문서 후보"
    )
    web_results: list[dict[str, Any]] = Field(
        default_factory=list, description="외부 검색 결과"
    )
    data: dict[str, Any] = Field(
        default_factory=dict, description="원본 Retrieval 결과"
    )


class CalcPreview(BaseModel):
    """계산형 orchestration 미리보기."""

    summary: str | None = Field(default=None, description="계산 결과 요약")
    policy: dict[str, Any] | None = Field(default=None, description="적용된 정책 정보")
    repayment: dict[str, Any] | None = Field(
        default=None, description="상환 스케줄 등 계산 결과"
    )
    inputs: dict[str, Any] = Field(default_factory=dict, description="사용자 입력 파라미터")
    confidence: dict[str, Any] | None = Field(
        default=None, description="계산 결과에 대한 부가 신뢰도 정보"
    )
    data: dict[str, Any] = Field(
        default_factory=dict, description="원본 계산 결과 데이터"
    )


class OrchestrationPreview(BaseModel):
    """Orchestration 흐름 미리보기 응답."""

    mode: Literal["info", "calc"] = Field(..., description="선택된 실행 모드")
    info: InfoPreview | None = Field(default=None, description="정보형 미리보기")
    calc: CalcPreview | None = Field(default=None, description="계산형 미리보기")


def build_mock_response(
    *,
    intent: ChatIntent,
    category: str | None,
    data: dict[str, Any],
    message: str,
    generated_at: datetime,
    confidence: dict[str, Any] | RetrievalConfidence | None = None,
) -> ChatResponse:
    """기존 Mock 응답 빌더 (호환용)."""

    return build_chat_response(
        intent=intent,
        category=category,
        data=data,
        message=message,
        generated_at=generated_at,
        mock=True,
        confidence=confidence,
    )


__all__ = [
    "ChatIntent",
    "ChatMetadata",
    "ChatMessage",
    "ChatRequest",
    "ChatResponse",
    "InfoPreview",
    "CalcPreview",
    "OrchestrationPreview",
    "build_chat_response",
    "build_mock_response",
    "RetrievalConfidence",
]
