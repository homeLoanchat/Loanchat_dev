"""/admin 라우터."""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter

from src.api.schemas import HealthResponse

router = APIRouter(prefix="/api/admin", tags=["admin"])


@router.get(
    "/health",
    response_model=HealthResponse,
    summary="관리자용 헬스체크",
    description="모니터링·테스트에서 서버 상태를 확인하는 관리자용 헬스체크 엔드포인트.",
)
def health_check() -> HealthResponse:
    """서버가 정상 동작하는지 간단히 확인한다."""
    return HealthResponse(timestamp=datetime.now(timezone.utc))
