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


@router.post("/refresh")
def trigger_refresh() -> dict[str, str]:
    """TODO: 지식베이스 리프레시 작업을 트리거하세요."""
    raise NotImplementedError("refresh 엔드포인트를 구현하세요.")


@router.get("/metrics")
def read_metrics() -> dict[str, str]:
    """TODO: 핵심 SLA/토큰 사용량 등을 반환하세요."""
    raise NotImplementedError("metrics 엔드포인트를 구현하세요.")
