"""/admin 라우터.

TODO:
1. 지식베이스 리프레시, 메트릭 조회, 시스템 상태 확인 엔드포인트를 정의하세요.
2. 관리자 인증/권한 검증 로직을 추가하세요.
3. 백그라운드 작업 큐(예: Celery, RQ) 연동을 고려하세요.
"""

from __future__ import annotations

from datetime import datetime, timezone
import logging

from fastapi import APIRouter, BackgroundTasks, Depends, Header, HTTPException, status

from config.settings import Settings
from src.api.schemas import HealthResponse, MetricsResponse, MetricsData
from src.core.dependencies import get_settings
from src.core.metrics import collect_metrics, mark_reindex
from scripts.build_index import run_build_index

router = APIRouter(prefix="/api/admin", tags=["admin"])

logger = logging.getLogger(__name__)


def _require_admin_token(
    settings: Settings = Depends(get_settings),
    x_admin_token: str | None = Header(default=None, alias="X-Admin-Token"),
) -> None:
    if x_admin_token is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Admin token required")
    if x_admin_token != settings.admin_secret.get_secret_value():
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid admin token")


@router.get(
    "/health",
    response_model=HealthResponse,
    response_model_exclude_none=True,
    summary="관리자 헬스체크",
)
def read_health(_: None = Depends(_require_admin_token)) -> HealthResponse:
    """기본 헬스체크 응답."""

    # TODO(Iteration 4): core.responses.ok() 적용하여 공통 포맷으로 반환 고려
    return HealthResponse(
        timestamp=datetime.now(timezone.utc),
        version="0.1.0",
    )


@router.post(
    "/reindex",
    status_code=status.HTTP_202_ACCEPTED,
    summary="벡터 인덱스 재생성",
)
def trigger_reindex(
    background_tasks: BackgroundTasks,
    settings: Settings = Depends(get_settings),
    _: None = Depends(_require_admin_token),
) -> dict[str, str]:
    """지식베이스 인덱스를 비동기로 재생성한다."""

    def _task() -> None:
        try:
            run_build_index(settings=settings)
            mark_reindex()
        except Exception as exc:  # noqa: BLE001
            logger.exception("reindex 작업 실패: %s", exc)

    background_tasks.add_task(_task)
    return {"status": "accepted"}


@router.get(
    "/metrics",
    response_model=MetricsResponse,
    summary="서비스 메트릭 조회",
)
def read_metrics(_: None = Depends(_require_admin_token)) -> MetricsResponse:
    snapshot = collect_metrics()
    data = MetricsData(**snapshot)
    return MetricsResponse(data=data)
