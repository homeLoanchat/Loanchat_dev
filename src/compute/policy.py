"""금융 상품 및 규제 정책 룰."""

from __future__ import annotations

from copy import deepcopy
from typing import Final

Policy = dict[str, object]
PolicyTable = dict[str, dict[str, Policy]]

_POLICY_TABLE: Final[PolicyTable] = {
    "kr": {
        "_default": {
            "currency": "KRW",
            "ltv_limit": 0.7,
            "dti_limit": 0.4,
            "dsr_limit": 0.4,
            "max_tenor_months": 360,
            "min_credit_score": 680,
            "documentation": {
                "income": True,
                "tax_report": True,
                "collateral_appraisal": True,
            },
        },
        "mortgage": {
            "ltv_limit": 0.7,
            "dti_limit": 0.4,
            "dsr_limit": 0.4,
            "max_tenor_months": 420,
            "min_credit_score": 700,
            "rate_spread": {"prime": 0.008, "standard": 0.015, "subprime": 0.028},
            "prepayment_penalty_months": 36,
        },
        "jeonse": {
            "ltv_limit": 0.8,
            "dti_limit": 0.45,
            "dsr_limit": 0.5,
            "max_tenor_months": 240,
            "min_credit_score": 660,
            "rate_spread": {"prime": 0.005, "standard": 0.012, "subprime": 0.02},
        },
        "personal": {
            "ltv_limit": None,
            "dti_limit": 0.35,
            "dsr_limit": 0.4,
            "max_tenor_months": 120,
            "min_credit_score": 720,
            "rate_spread": {"prime": 0.015, "standard": 0.028, "subprime": 0.045},
        },
    },
}


def get_policy(region: str, product_type: str) -> Policy:
    """지역/상품 유형별 한도, 금리, 심사 기준 등을 반환합니다."""

    region_key = region.strip().lower()
    product_key = product_type.strip().lower()

    if not region_key:
        raise ValueError("region must be a non-empty string.")
    if not product_key:
        raise ValueError("product_type must be a non-empty string.")

    try:
        region_table = _POLICY_TABLE[region_key]
    except KeyError as exc:
        raise ValueError(f"Unsupported region: {region}") from exc

    policy = region_table.get(product_key) or region_table.get("_default")
    if policy is None:
        raise ValueError(f"Unsupported product_type '{product_type}' for region '{region}'.")

    return deepcopy(policy)
