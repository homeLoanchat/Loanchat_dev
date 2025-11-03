"""/calc 라우터."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from src.api.schemas import CalcRequest, CalcType, build_calc_response
from src.core.exceptions import InvalidValueError
from src.core.responses import ErrorResponse, SuccessResponse
from src.services import ComputeService, get_compute_service

router = APIRouter(prefix="/api/calc", tags=["calc"])


@router.post(
    "",
    response_model=SuccessResponse,
    response_model_exclude_none=True,
    responses={
        400: {"model": ErrorResponse},
        422: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
    summary="계산 엔드포인트",
    description="calc_type에 따라 금융 계산을 수행합니다.",
)
def calc_endpoint(
    payload: CalcRequest,
    service: ComputeService = Depends(get_compute_service),
) -> CalcResponse:
    """계산형 요청을 처리한다."""

    try:
        calc_type = CalcType(payload.calc_type)
    except ValueError as exc:
        raise InvalidValueError(
            "지원하지 않는 calc_type 입니다.",
            field="calc_type",
            details={"calc_type": payload.calc_type},
        ) from exc

    if payload.params is None:
        raise InvalidValueError("params 필드가 필요합니다.", field="params")

    result = service.calculate(calc_type=calc_type, params=payload.params)
    return build_calc_response(calc_type=calc_type, data=result)


__all__ = ["router"]
