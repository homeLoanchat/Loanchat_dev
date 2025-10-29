"""금융 계산 엔진."""

from __future__ import annotations


def calculate_ltv(*, collateral_value: float, loan_amount: float) -> float:
    """TODO: 담보 대비 대출 비율(LTV)을 계산하세요."""
    raise NotImplementedError("LTV 계산을 구현하세요.")


def calculate_dti(*, annual_income: float, total_debt_payment: float) -> float:
    """TODO: 총부채상환비율(DTI)을 계산하세요."""
    raise NotImplementedError("DTI 계산을 구현하세요.")


def calculate_amortization_schedule(*, principal: float, interest_rate: float, months: int) -> list[dict[str, float]]:
    """TODO: 원리금 상환 스케줄을 생성하세요."""
    raise NotImplementedError("상환표 계산을 구현하세요.")
