"""공통 응답 포맷."""

from __future__ import annotations

from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class SuccessResponse(BaseModel):
    """표준 성공 응답."""

    success: Literal[True] = True
    type: str = Field(..., description="응답 intent 혹은 유형")
    category: str | None = Field(
        default=None, description="도메인 카테고리 (선택)"
    )
    data: dict[str, Any] = Field(..., description="응답 본문")
    metadata: dict[str, Any] | None = Field(
        default=None, description="추가 메타 데이터"
    )
    error: None = Field(default=None, description="성공 시 오류 정보는 없음")

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
                    },
                }
            ]
        }
    )


class ErrorPayload(BaseModel):
    """오류 상세 정보."""

    code: str = Field(..., description="오류 코드")
    message: str = Field(..., description="오류 메시지")
    field: str | None = Field(
        default=None, description="오류가 발생한 필드명 (선택)"
    )
    details: dict[str, Any] | None = Field(
        default=None, description="추가 디버깅 정보"
    )


class ErrorResponse(BaseModel):
    """표준 실패 응답."""

    success: Literal[False] = False
    error: ErrorPayload = Field(..., description="오류 정보")
    metadata: dict[str, Any] | None = Field(
        default=None, description="추가 메타 데이터"
    )
    data: None = Field(default=None, description="실패 시 데이터 없음")
    type: None = Field(default=None, description="실패 시 타입 없음")
    category: None = Field(default=None, description="실패 시 카테고리 없음")

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "success": False,
                    "error": {
                        "code": "INVALID_VALUE",
                        "message": "지원하지 않는 category 입니다.",
                        "field": "category",
                    },
                }
            ]
        }
    )


def _intent_to_str(intent: str | Enum) -> str:
    if isinstance(intent, Enum):
        return intent.value
    return str(intent)


def ok(
    *,
    data: dict[str, Any],
    intent: str | Enum,
    category: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """표준 성공 응답을 생성한다."""

    response = SuccessResponse(
        type=_intent_to_str(intent),
        category=category,
        data=data,
        metadata=metadata,
    )
    return response.model_dump(exclude_none=True)


def fail(
    *,
    code: str,
    message: str,
    field: str | None = None,
    details: dict[str, Any] | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """표준 실패 응답을 생성한다."""

    response = ErrorResponse(
        error=ErrorPayload(code=code, message=message, field=field, details=details),
        metadata=metadata,
    )
    return response.model_dump(exclude_none=True)


__all__ = [
    "ErrorPayload",
    "ErrorResponse",
    "SuccessResponse",
    "fail",
    "ok",
]
