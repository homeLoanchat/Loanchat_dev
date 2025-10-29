"""Pydantic models for admin endpoints."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    """헬스체크 응답."""

    status: Literal["ok"] = Field("ok", description="서비스 상태")
    timestamp: datetime = Field(..., description="ISO 포맷의 서버 시각(UTC)")
    version: str | None = Field(
        default=None,
        description="선택적 서비스 버전 정보",
        examples=["0.1.0"],
    )
