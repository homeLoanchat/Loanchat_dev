"""Pydantic models for the /calc endpoint."""

from __future__ import annotations

from enum import Enum
from typing import Any, Dict

from pydantic import BaseModel, ConfigDict, Field

from src.core.responses import SuccessResponse, ok


class CalcType(str, Enum):
    LTV = "ltv"
    DTI = "dti"
    DSR = "dsr"
    AMORTIZATION = "amortization"
    PAYMENT_SENSITIVITY = "payment_sensitivity"
    PREPAYMENT_FEE = "prepayment_fee"


class CalcRequest(BaseModel):
    """계산형 엔드포인트 요청 스키마."""

    calc_type: str = Field(..., description="수행할 계산 유형")
    params: Dict[str, Any] | None = Field(None, description="계산에 필요한 파라미터")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "calc_type": "ltv",
                "params": {"collateral_value": 500000000, "loan_amount": 300000000},
            }
        }
    )


def build_calc_response(*, calc_type: CalcType, data: dict[str, Any]) -> SuccessResponse:
    payload = ok(data=data, intent=calc_type.value)
    return SuccessResponse(**payload)


__all__ = ["CalcType", "CalcRequest", "build_calc_response"]
