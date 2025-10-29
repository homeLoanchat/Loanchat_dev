"""금융 계산 엔진."""

from __future__ import annotations

import math
from collections.abc import Sequence
from typing import TYPE_CHECKING, Literal, Union, overload

try:  # pragma: no cover - optional dependency
    import pandas as _pd
except Exception:  # pragma: no cover - optional dependency
    _pd = None  # type: ignore[assignment]

if TYPE_CHECKING:  # pragma: no cover - typing helper
    import pandas as pd

Number = Union[float, int]
SeriesLike = "pd.Series"
DataFrameLike = "pd.DataFrame"


def _is_pandas_series(value: object) -> bool:
    return _pd is not None and isinstance(value, _pd.Series)


def _as_float(value: Number, *, name: str) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:  # pragma: no cover - defensive branch
        raise TypeError(f"{name} must be a numeric value.") from exc
    if not (result == result and result not in (float("inf"), float("-inf"))):
        raise ValueError(f"{name} cannot be NaN or infinite.")
    return result


def _as_series(value: object, *, name: str) -> "pd.Series":
    if _pd is None:  # pragma: no cover - optional dependency
        raise RuntimeError("pandas is required for series-based calculations.")
    if isinstance(value, _pd.Series):
        return value.astype(float)
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        return _pd.Series(value, dtype=float, name=name)
    if isinstance(value, (int, float)):
        return _pd.Series([float(value)], name=name)
    raise TypeError(f"{name} must be convertible to pandas.Series.")


def _validate_positive(value: object, *, name: str, allow_zero: bool = False) -> None:
    if _is_pandas_series(value):
        series = value.astype(float)
        comparison = series < 0 if allow_zero else series <= 0
        if comparison.any():
            raise ValueError(f"{name} must be {'non-negative' if allow_zero else 'greater than 0'}.")
    elif isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        for item in value:
            _validate_positive(item, name=name, allow_zero=allow_zero)
    else:
        numeric = _as_float(value, name=name)
        if allow_zero:
            if numeric < 0:
                raise ValueError(f"{name} must be non-negative.")
        else:
            if numeric <= 0:
                raise ValueError(f"{name} must be greater than 0.")


def _validate_non_negative(value: object, *, name: str) -> None:
    _validate_positive(value, name=name, allow_zero=True)


def _ensure_no_missing(value: object, *, name: str) -> None:
    if _is_pandas_series(value):
        if value.isna().any():
            raise ValueError(f"{name} cannot contain missing values.")
    elif isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        for index, item in enumerate(value):
            if item is None:
                raise ValueError(f"{name} contains a None value at position {index}.")
            if isinstance(item, float) and math.isnan(item):
                raise ValueError(f"{name} contains NaN at position {index}.")
    elif isinstance(value, float) and math.isnan(value):
        raise ValueError(f"{name} cannot be NaN.")


def _coerce_like(
    a: object,
    b: object,
    *,
    name_a: str,
    name_b: str,
) -> tuple[object, object]:
    if _is_pandas_series(a) or _is_pandas_series(b):
        series_a = _as_series(a, name=name_a)
        series_b = _as_series(b, name=name_b)
        return series_a.align(series_b, join="outer", fill_value=float("nan"))
    if _pd is not None and (
        (isinstance(a, Sequence) and not isinstance(a, (str, bytes)))
        or (isinstance(b, Sequence) and not isinstance(b, (str, bytes)))
    ):
        series_a = _as_series(a, name=name_a)
        series_b = _as_series(b, name=name_b)
        return series_a.align(series_b, join="outer", fill_value=float("nan"))
    return a, b


def calculate_ltv(*, collateral_value: object, loan_amount: object) -> object:
    """담보 대비 대출 비율(LTV)을 계산합니다.

    Args:
        collateral_value: 담보 자산 가치. 스칼라(float/int) 또는 pandas Series/Sequence 지원.
        loan_amount: 대출 금액. 스칼라(float/int) 또는 pandas Series/Sequence 지원.

    Returns:
        LTV 비율. 입력 타입을 보존하여 float 또는 pandas Series로 반환합니다.
    """

    collateral_value, loan_amount = _coerce_like(
        collateral_value,
        loan_amount,
        name_a="collateral_value",
        name_b="loan_amount",
    )

    _validate_positive(collateral_value, name="collateral_value")
    _validate_non_negative(loan_amount, name="loan_amount")
    _ensure_no_missing(collateral_value, name="collateral_value")
    _ensure_no_missing(loan_amount, name="loan_amount")

    if _is_pandas_series(collateral_value):
        result = loan_amount / collateral_value
        return result.rename("ltv")  # type: ignore[return-value]

    collateral = _as_float(collateral_value, name="collateral_value")
    loan = _as_float(loan_amount, name="loan_amount")
    return loan / collateral


def calculate_dti(*, annual_income: object, total_debt_payment: object) -> object:
    """총부채상환비율(DTI)을 계산합니다.

    Args:
        annual_income: 연소득. 스칼라 또는 pandas Series/Sequence.
        total_debt_payment: 연간 부채 상환액. 스칼라 또는 pandas Series/Sequence.

    Returns:
        DTI 비율. 입력 타입을 보존합니다.
    """

    annual_income, total_debt_payment = _coerce_like(
        annual_income,
        total_debt_payment,
        name_a="annual_income",
        name_b="total_debt_payment",
    )

    _validate_positive(annual_income, name="annual_income")
    _validate_non_negative(total_debt_payment, name="total_debt_payment")
    _ensure_no_missing(annual_income, name="annual_income")
    _ensure_no_missing(total_debt_payment, name="total_debt_payment")

    if _is_pandas_series(annual_income):
        result = total_debt_payment / annual_income
        return result.rename("dti")  # type: ignore[return-value]

    income = _as_float(annual_income, name="annual_income")
    debt = _as_float(total_debt_payment, name="total_debt_payment")
    return debt / income


def calculate_dsr(*, annual_income: object, annual_debt_service: object) -> object:
    """총부채원리금상환비율(DSR)을 계산합니다."""

    annual_income, annual_debt_service = _coerce_like(
        annual_income,
        annual_debt_service,
        name_a="annual_income",
        name_b="annual_debt_service",
    )

    _validate_positive(annual_income, name="annual_income")
    _validate_non_negative(annual_debt_service, name="annual_debt_service")
    _ensure_no_missing(annual_income, name="annual_income")
    _ensure_no_missing(annual_debt_service, name="annual_debt_service")

    if _is_pandas_series(annual_income):
        result = annual_debt_service / annual_income
        return result.rename("dsr")  # type: ignore[return-value]

    income = _as_float(annual_income, name="annual_income")
    service = _as_float(annual_debt_service, name="annual_debt_service")
    return service / income


def _monthly_payment(*, principal: float, monthly_interest_rate: float, months: int) -> float:
    _validate_positive(principal, name="principal")
    _validate_non_negative(monthly_interest_rate, name="monthly_interest_rate")
    if months <= 0:
        raise ValueError("months must be greater than 0.")

    if monthly_interest_rate == 0:
        return principal / months

    factor = (1 + monthly_interest_rate) ** months
    return principal * monthly_interest_rate * factor / (factor - 1)


@overload
def calculate_amortization_schedule(
    *,
    principal: float,
    interest_rate: float,
    months: int,
    as_dataframe: Literal[True],
) -> DataFrameLike:
    ...


@overload
def calculate_amortization_schedule(
    *,
    principal: float,
    interest_rate: float,
    months: int,
    as_dataframe: Literal[False] = False,
) -> list[dict[str, float]]:
    ...


def calculate_amortization_schedule(
    *,
    principal: float,
    interest_rate: float,
    months: int,
    as_dataframe: bool = False,
) -> object:
    """균등분할 원리금 상환 스케줄을 생성합니다."""

    _validate_positive(principal, name="principal")
    _validate_non_negative(interest_rate, name="interest_rate")
    if months <= 0:
        raise ValueError("months must be greater than 0.")

    monthly_rate = interest_rate / 12
    payment = _monthly_payment(principal=principal, monthly_interest_rate=monthly_rate, months=months)

    schedule: list[dict[str, float]] = []
    balance = float(principal)

    for period in range(1, months + 1):
        interest_payment = balance * monthly_rate
        principal_payment = payment - interest_payment

        if period == months:
            principal_payment = balance
            payment_for_period = principal_payment + interest_payment
            balance = 0.0
        else:
            balance = max(balance - principal_payment, 0.0)
            payment_for_period = payment

        schedule.append(
            {
                "period": period,
                "payment": round(payment_for_period, 2),
                "principal": round(principal_payment, 2),
                "interest": round(interest_payment, 2),
                "balance": round(balance, 2),
            }
        )

    if as_dataframe:
        if _pd is None:  # pragma: no cover - optional dependency
            raise RuntimeError("pandas is required for DataFrame output.")
        return _pd.DataFrame(schedule)

    return schedule


@overload
def calculate_payment_sensitivity(
    *,
    principal: float,
    interest_rates: Sequence[float],
    months: int,
    as_dataframe: Literal[True],
) -> DataFrameLike:
    ...


@overload
def calculate_payment_sensitivity(
    *,
    principal: float,
    interest_rates: Sequence[float],
    months: int,
    as_dataframe: Literal[False] = False,
) -> list[dict[str, float]]:
    ...


def calculate_payment_sensitivity(
    *,
    principal: float,
    interest_rates: Sequence[float],
    months: int,
    as_dataframe: bool = False,
) -> object:
    """금리 민감도 분석 결과를 반환합니다."""

    if not interest_rates:
        raise ValueError("interest_rates must contain at least one value.")

    _validate_positive(principal, name="principal")
    if months <= 0:
        raise ValueError("months must be greater than 0.")

    results: list[dict[str, float]] = []
    for rate in interest_rates:
        _validate_non_negative(rate, name="interest_rate")
        monthly_rate = rate / 12
        payment = _monthly_payment(
            principal=principal,
            monthly_interest_rate=monthly_rate,
            months=months,
        )
        total_payment = payment * months
        results.append(
            {
                "interest_rate": rate,
                "monthly_payment": round(payment, 2),
                "total_payment": round(total_payment, 2),
                "total_interest": round(total_payment - principal, 2),
            }
        )

    if as_dataframe:
        if _pd is None:  # pragma: no cover - optional dependency
            raise RuntimeError("pandas is required for DataFrame output.")
        return _pd.DataFrame(results)

    return results


__all__ = [
    "calculate_ltv",
    "calculate_dti",
    "calculate_dsr",
    "calculate_amortization_schedule",
    "calculate_payment_sensitivity",
]
