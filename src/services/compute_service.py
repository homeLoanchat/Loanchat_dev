"""계산형 챗봇 응답을 위한 Compute 서비스."""

from __future__ import annotations

import logging
from typing import Any

from src.compute import engine
from src.compute.policy import get_policy
from src.core.exceptions import InvalidValueError

logger = logging.getLogger(__name__)


class LoanComputationService:
    """도메인 정책과 계산 엔진을 결합해 응답 페이로드를 생성한다."""

    is_mock = False

    def __init__(self, *, default_region: str = "kr", default_product: str = "mortgage") -> None:
        self._default_region = default_region
        self._default_product = default_product

    def run(
        self,
        *,
        category: str | None,
        params: dict[str, Any] | None,
        user_id: str | None = None,
    ) -> dict[str, Any]:
        if not params:
            raise InvalidValueError(
                "계산형 응답을 생성하려면 params가 필요합니다.",
                field="params",
            )

        region = str(params.get("region") or self._default_region)
        product = str(category or params.get("product_type") or self._default_product)
        policy = get_policy(region, product)

        loan_amount = _safe_float(params.get("loan_amount"))
        collateral_value = _safe_float(params.get("collateral_value") or params.get("house_price"))
        annual_income = _safe_float(params.get("annual_income") or params.get("income"))
        annual_debt_payment = _safe_float(params.get("total_debt_payment") or params.get("debt_payment"))
        annual_debt_service = _safe_float(params.get("annual_debt_service"))
        interest_rate_pct = _safe_float(params.get("rate") or params.get("interest_rate"))
        term_months = _safe_int(params.get("term_months") or params.get("tenor_months")) or policy.get("max_tenor_months") or 360

        logger.debug(
            "LoanComputationService.run region=%s product=%s loan=%s collateral=%s",
            region,
            product,
            loan_amount,
            collateral_value,
        )

        ltv_ratio = _calculate_ratio(
            engine.calculate_ltv,
            collateral_value=collateral_value,
            loan_amount=loan_amount,
        )
        dti_ratio = _calculate_ratio(
            engine.calculate_dti,
            annual_income=annual_income,
            total_debt_payment=annual_debt_payment,
        )
        dsr_ratio = _calculate_ratio(
            engine.calculate_dsr,
            annual_income=annual_income,
            annual_debt_service=annual_debt_service or annual_debt_payment,
        )

        monthly_payment = None
        repayment_schedule = None
        if loan_amount and interest_rate_pct is not None and term_months:
            try:
                schedule = engine.calculate_amortization_schedule(
                    principal=loan_amount,
                    interest_rate=(interest_rate_pct / 100.0),
                    months=term_months,
                )
                if schedule:
                    monthly_payment = schedule[0]["payment"]
                    repayment_schedule = schedule[:12]
            except Exception as exc:  # noqa: BLE001
                logger.warning("상환 스케줄 계산 실패: %s", exc)

        max_by_ltv = None
        if collateral_value is not None:
            ltv_limit = policy.get("ltv_limit")
            if isinstance(ltv_limit, (int, float)):
                max_by_ltv = round(collateral_value * ltv_limit, 2)

        summary_parts: list[str] = []
        if max_by_ltv is not None:
            summary_parts.append(f"담보 기준 예상 한도는 약 {int(max_by_ltv):,} {policy.get('currency', 'KRW')}입니다.")
        if monthly_payment is not None:
            summary_parts.append(f"월 예상 상환액은 약 {round(monthly_payment):,} {policy.get('currency', 'KRW')}입니다.")
        if not summary_parts:
            summary_parts.append("입력값이 제한적이라 일반 정책 정보만 제공합니다.")

        confidence = {
            "passed": True,
            "reason": "policy_limits",
            "top_score": 1.0,
            "top_score_normalized": 1.0,
            "top_document_id": None,
            "hits": 1,
            "thresholds": {
                "min_score": 0.0,
                "min_score_normalized": 0.0,
                "min_hits": 0,
            },
            "region": region,
            "product_type": product,
        }

        return {
            "summary": " ".join(summary_parts),
            "currency": policy.get("currency", "KRW"),
            "policy": policy,
            "ltv": {
                "value": ltv_ratio,
                "limit": policy.get("ltv_limit"),
                "passed": _is_within_limit(ltv_ratio, policy.get("ltv_limit")),
            },
            "dti": {
                "value": dti_ratio,
                "limit": policy.get("dti_limit"),
                "passed": _is_within_limit(dti_ratio, policy.get("dti_limit")),
            },
            "dsr": {
                "value": dsr_ratio,
                "limit": policy.get("dsr_limit"),
                "passed": _is_within_limit(dsr_ratio, policy.get("dsr_limit")),
            },
            "repayment": {
                "monthly_payment": monthly_payment,
                "term_months": term_months,
                "schedule_preview": repayment_schedule,
            },
            "inputs": params,
            "confidence": confidence,
        }


def _safe_float(value: Any) -> float | None:
    try:
        if value is None or value == "":
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _safe_int(value: Any) -> int | None:
    try:
        if value is None or value == "":
            return None
        return int(value)
    except (TypeError, ValueError):
        return None


def _calculate_ratio(func, **kwargs) -> float | None:
    if any(v is None for v in kwargs.values()):
        return None
    try:
        result = func(**kwargs)
        if isinstance(result, (int, float)):
            return float(result)
    except Exception as exc:  # noqa: BLE001
        logger.debug("ratio 계산 실패 func=%s kwargs=%s error=%s", func.__name__, kwargs, exc)
    return None


def _is_within_limit(value: float | None, limit: Any) -> bool | None:
    if value is None or limit in (None, ""):
        return None
    try:
        return float(value) <= float(limit)
    except (TypeError, ValueError):
        return None


__all__ = ["LoanComputationService"]
