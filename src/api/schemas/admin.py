"""Pydantic models for admin endpoints."""

from __future__ import annotations

from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field

from src.core.metrics import TokenUsage


class HealthResponse(BaseModel):
    """헬스체크 응답."""

    status: Literal["ok"] = Field("ok", description="서비스 상태")
    timestamp: datetime = Field(..., description="ISO 포맷의 서버 시각(UTC)")
    version: str | None = Field(
        default=None,
        description="선택적 서비스 버전 정보",
        examples=["0.1.0"],
    )


class MetricsData(BaseModel):
    """관리자 메트릭 데이터."""

    uptime_sec: float = Field(..., description="서비스 업타임(초)")
    req_count: int = Field(..., description="누적 요청 수")
    p50_ms: float = Field(..., description="요청 지연 p50 (ms)")
    p95_ms: float = Field(..., description="요청 지연 p95 (ms)")
    token_usage: TokenUsage = Field(..., description="토큰 사용량")
    last_reindex_at: Optional[datetime] = Field(
        default=None,
        description="마지막 인덱스 재생성 시각",
    )


class MetricsResponse(BaseModel):
    """관리자 메트릭 응답."""

    success: Literal[True] = Field(True, description="응답 성공 여부")
    type: Literal["metrics"] = Field("metrics", description="응답 유형")
    data: MetricsData = Field(..., description="메트릭 데이터")
    category: None = None
    metadata: dict[str, str] | None = None
    error: None = None
