"""Compute 서비스 계층."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from functools import lru_cache
from typing import Any, Callable, Dict

from src.api.schemas import CalcType
from src.compute.engine import (
    calculate_amortization_schedule,
    calculate_dsr,
    calculate_dti,
    calculate_ltv,
    calculate_payment_sensitivity,
)
from src.core.exceptions import InvalidValueError

Handler = Callable[[dict[str, Any]], dict[str, Any]]


class ComputeService:
    """calc_type에 따라 금융 계산을 수행한다."""

    def __init__(self) -> None:
        self._handlers: Dict[CalcType, Handler] = {
            CalcType.LTV: self._handle_ltv,
            CalcType.DTI: self._handle_dti,
            CalcType.DSR: self._handle_dsr,
            CalcType.AMORTIZATION: self._handle_amortization,
            CalcType.PAYMENT_SENSITIVITY: self._handle_payment_sensitivity,
        }

    def calculate(self, *, calc_type: CalcType, params: dict[str, Any]) -> dict[str, Any]:
        try:
            handler = self._handlers[calc_type]
        except KeyError as exc:  # pragma: no cover - 안전장치
            raise InvalidValueError(
                "지원하지 않는 calc_type 입니다.",
                field="calc_type",
                details={"calc_type": calc_type.value},
            ) from exc
        return handler(params)

    # Handlers -----------------------------------------------------------------

    def _handle_ltv(self, params: dict[str, Any]) -> dict[str, Any]:
        collateral = self._require_decimal(params, "collateral_value")
        loan = self._require_decimal(params, "loan_amount", allow_zero=True)
        try:
            ratio_value = calculate_ltv(collateral_value=float(collateral), loan_amount=float(loan))
        except ValueError as exc:
            raise InvalidValueError(str(exc), field="collateral_value") from exc
        ratio = Decimal(str(ratio_value)).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)
        return {
            "ltv": float(ratio),
            "ratio": str(ratio),
            "collateral_value": float(collateral),
            "loan_amount": float(loan),
        }

    def _handle_dti(self, params: dict[str, Any]) -> dict[str, Any]:
        income = self._require_decimal(params, "annual_income")
        debt_payment = self._require_decimal(params, "total_debt_payment", allow_zero=True)
        try:
            ratio_value = calculate_dti(annual_income=float(income), total_debt_payment=float(debt_payment))
        except ValueError as exc:
            raise InvalidValueError(str(exc), field="annual_income") from exc
        ratio = Decimal(str(ratio_value)).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)
        return {
            "dti": float(ratio),
            "ratio": str(ratio),
            "annual_income": float(income),
            "total_debt_payment": float(debt_payment),
        }

    def _handle_dsr(self, params: dict[str, Any]) -> dict[str, Any]:
        income = self._require_decimal(params, "annual_income")
        debt_service = self._require_decimal(params, "annual_debt_service", allow_zero=True)
        try:
            ratio_value = calculate_dsr(annual_income=float(income), annual_debt_service=float(debt_service))
        except ValueError as exc:
            raise InvalidValueError(str(exc), field="annual_income") from exc
        ratio = Decimal(str(ratio_value)).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)
        return {
            "dsr": float(ratio),
            "ratio": str(ratio),
            "annual_income": float(income),
            "annual_debt_service": float(debt_service),
        }

    def _handle_amortization(self, params: dict[str, Any]) -> dict[str, Any]:
        principal = self._require_decimal(params, "principal")
        interest_rate = self._require_decimal(params, "interest_rate", allow_zero=True)
        months = self._require_int(params, "months", min_value=1)
        schedule = calculate_amortization_schedule(
            principal=float(principal),
            interest_rate=float(interest_rate),
            months=months,
            as_dataframe=False,
        )
        monthly_payment = schedule[0]["payment"] if schedule else 0.0
        return {
            "principal": float(principal),
            "interest_rate": float(interest_rate),
            "months": months,
            "schedule": schedule,
            "monthly_payment": monthly_payment,
        }

    def _handle_payment_sensitivity(self, params: dict[str, Any]) -> dict[str, Any]:
        principal = self._require_decimal(params, "principal")
        rates = self._require_rate_list(params, "interest_rates")
        months = self._require_int(params, "months", min_value=1)
        sensitivity = calculate_payment_sensitivity(
            principal=float(principal),
            interest_rates=[float(rate) for rate in rates],
            months=months,
            as_dataframe=False,
        )
        return {
            "principal": float(principal),
            "interest_rates": [float(rate) for rate in rates],
            "months": months,
            "sensitivity": sensitivity,
        }

    # Helpers ------------------------------------------------------------------

    def _require_decimal(
        self,
        params: dict[str, Any],
        key: str,
        *,
        allow_zero: bool = False,
    ) -> Decimal:
        if key not in params:
            raise InvalidValueError(f"{key} 파라미터가 필요합니다.", field=key)
        value = params[key]
        try:
            decimal_value = Decimal(str(value))
        except (InvalidOperation, ValueError) as exc:
            raise InvalidValueError(f"{key}는 숫자여야 합니다.", field=key) from exc
        if not allow_zero and decimal_value == 0:
            raise InvalidValueError(f"{key}는 0이 될 수 없습니다.", field=key)
        return decimal_value

    def _require_int(
        self,
        params: dict[str, Any],
        key: str,
        *,
        min_value: int | None = None,
    ) -> int:
        if key not in params:
            raise InvalidValueError(f"{key} 파라미터가 필요합니다.", field=key)
        try:
            value = int(params[key])
        except (TypeError, ValueError) as exc:
            raise InvalidValueError(f"{key}는 정수여야 합니다.", field=key) from exc
        if min_value is not None and value < min_value:
            raise InvalidValueError(f"{key}는 {min_value} 이상이어야 합니다.", field=key)
        return value

    def _require_rate_list(self, params: dict[str, Any], key: str) -> list[Decimal]:
        if key not in params:
            raise InvalidValueError(f"{key} 파라미터가 필요합니다.", field=key)
        raw = params[key]
        if not isinstance(raw, (list, tuple)) or not raw:
            raise InvalidValueError(f"{key}는 숫자 리스트여야 합니다.", field=key)
        rates: list[Decimal] = []
        for idx, item in enumerate(raw):
            try:
                rates.append(Decimal(str(item)))
            except (InvalidOperation, ValueError) as exc:
                raise InvalidValueError(
                    f"{key}[{idx}]는 숫자여야 합니다.",
                    field=key,
                    details={"index": idx},
                ) from exc
        return rates


@lru_cache(maxsize=1)
def get_compute_service() -> ComputeService:
    return ComputeService()



__all__ = ["ComputeService", "get_compute_service"]
