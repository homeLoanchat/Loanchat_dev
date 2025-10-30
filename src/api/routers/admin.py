"""/admin 라우터.

TODO:
1. 지식베이스 리프레시, 메트릭 조회, 시스템 상태 확인 엔드포인트를 정의하세요.
2. 관리자 인증/권한 검증 로직을 추가하세요.
3. 백그라운드 작업 큐(예: Celery, RQ) 연동을 고려하세요.
"""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter

from src.api.schemas import HealthResponse

router = APIRouter(prefix="/api/admin", tags=["admin"])


@router.get(
    "/health",
    response_model=HealthResponse,
    response_model_exclude_none=True,
    summary="관리자 헬스체크",
)
def read_health() -> HealthResponse:
    """기본 헬스체크 응답."""

    # TODO(Iteration 4): core.responses.ok() 적용하여 공통 포맷으로 반환 고려
    return HealthResponse(
        timestamp=datetime.now(timezone.utc),
        version="0.1.0",
    )
