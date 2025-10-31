"""금융 계산 엔진."""

from __future__ import annotations

import math
from collections.abc import Sequence
from typing import TYPE_CHECKING, Literal, overload, cast

try:  # pragma: no cover - typing backport
    from typing import TypeAlias, TypeGuard
except ImportError:  # pragma: no cover - fallback for older type checkers
    from typing_extensions import TypeAlias, TypeGuard
try:  # pragma: no cover - optional dependency
    import pandas as _pd
except Exception:  # pragma: no cover - optional dependency
    _pd = None  # type: ignore[assignment]

if TYPE_CHECKING:  # pragma: no cover - typing helper
    import pandas as pd

SeriesLike: TypeAlias = "pd.Series"
DataFrameLike: TypeAlias = "pd.DataFrame"


def _is_pandas_series(value: object) -> TypeGuard["pd.Series"]:
    # pandas Series 유형인지 확인한다.
    return _pd is not None and isinstance(value, _pd.Series)


def _is_sequence_like(value: object) -> bool:
    # 시퀀스 형태로 취급 가능한지 판별한다.
    return isinstance(value, Sequence) and not isinstance(value, (str, bytes))


def _as_float(value: object, *, name: str) -> float:
    # 입력을 float으로 변환하며 NaN/무한대를 차단한다.
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:  # pragma: no cover - defensive branch
        raise TypeError(f"{name} must be a numeric value.") from exc
    if not (result == result and result not in (float("inf"), float("-inf"))):
        raise ValueError(f"{name} cannot be NaN or infinite.")
    return result


def _as_numeric_sequence(value: object, *, name: str) -> list[float]:
    # 시퀀스 항목을 모두 float 리스트로 정규화한다.
    if not _is_sequence_like(value):
        raise TypeError(f"{name} must be a sequence of numeric values.")
    sequence = cast(Sequence[object], value)
    result: list[float] = []
    for index, item in enumerate(sequence):
        numeric = _as_float(item, name=f"{name}[{index}]")
        result.append(numeric)
    return result


def _as_series(value: object, *, name: str) -> "pd.Series":
    # pandas Series 기반 계산을 위해 입력을 Series로 변환한다.
    if _pd is None:  # pragma: no cover - optional dependency
        raise RuntimeError("pandas is required for series-based calculations.")
    if isinstance(value, _pd.Series):
        return value.astype(float)
    if _is_sequence_like(value):
        return _pd.Series(value, dtype=float, name=name)
    if isinstance(value, (int, float)):
        return _pd.Series([float(value)], name=name)
    raise TypeError(f"{name} must be convertible to pandas.Series.")


def _validate_positive(value: object, *, name: str, allow_zero: bool = False) -> None:
    # 값이 양수(또는 0 이상)인지 검증한다.
    if _is_pandas_series(value):
        series = value.astype(float)
        comparison = series < 0 if allow_zero else series <= 0
        if comparison.any():
            raise ValueError(f"{name} must be {'non-negative' if allow_zero else 'greater than 0'}.")
    elif _is_sequence_like(value):
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
    # 음수 값이 존재하는지 확인한다.
    _validate_positive(value, name=name, allow_zero=True)


def _ensure_no_missing(value: object, *, name: str) -> None:
    # None 혹은 NaN과 같은 결측값이 있는지 검사한다.
    if _is_pandas_series(value):
        if value.isna().any():
            raise ValueError(f"{name} cannot contain missing values.")
    elif _is_sequence_like(value):
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
    # 서로 다른 타입의 입력을 동일한 길이/정렬로 맞춘다.
    if _is_pandas_series(a) or _is_pandas_series(b):
        series_a = _as_series(a, name=name_a)
        series_b = _as_series(b, name=name_b)
        return series_a.align(series_b, join="outer", fill_value=float("nan"))
    if _pd is not None and (
        _is_sequence_like(a)
        or _is_sequence_like(b)
    ):
        series_a = _as_series(a, name=name_a)
        series_b = _as_series(b, name=name_b)
        return series_a.align(series_b, join="outer", fill_value=float("nan"))
    return a, b


def _calculate_ratio(
    *,
    numerator: object,
    denominator: object,
    numerator_name: str,
    denominator_name: str,
    series_label: str,
) -> object:
    # 비율 계산을 공통 로직으로 처리한다.
    if _is_pandas_series(numerator) or _is_pandas_series(denominator):
        series_numerator = _as_series(numerator, name=numerator_name)
        series_denominator = _as_series(denominator, name=denominator_name)
        result = series_numerator / series_denominator
        return result.rename(series_label)  # type: ignore[return-value]
    numerator_is_sequence = _is_sequence_like(numerator)
    denominator_is_sequence = _is_sequence_like(denominator)
    if numerator_is_sequence or denominator_is_sequence:
        if numerator_is_sequence != denominator_is_sequence:
            raise ValueError(
                f"{numerator_name} and {denominator_name} must both be sequences when one is provided as a sequence."
            )
        numeric_numerator = _as_numeric_sequence(numerator, name=numerator_name)
        numeric_denominator = _as_numeric_sequence(denominator, name=denominator_name)
        if len(numeric_numerator) != len(numeric_denominator):
            raise ValueError(f"{numerator_name} and {denominator_name} must have the same length.")
        return [num / den for num, den in zip(numeric_numerator, numeric_denominator)]
    numerator_float = _as_float(numerator, name=numerator_name)
    denominator_float = _as_float(denominator, name=denominator_name)
    return numerator_float / denominator_float


# 담보 대비 대출 비율(LTV)을 계산한다.
def calculate_ltv(*, collateral_value: object, loan_amount: object) -> object:
    """담보 대비 대출 비율(LTV)을 계산합니다.

    Args:
        collateral_value: 담보 자산 가치. 스칼라(float/int) 또는 pandas Series/Sequence 지원.
        loan_amount: 대출 금액. 스칼라(float/int) 또는 pandas Series/Sequence 지원.

    Returns:
        LTV 비율. 스칼라는 float으로, pandas Series는 Series로 반환하며
        pandas가 없는 환경에서는 시퀀스 입력에 대해 float 리스트를 반환합니다.
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

    return _calculate_ratio(
        numerator=loan_amount,
        denominator=collateral_value,
        numerator_name="loan_amount",
        denominator_name="collateral_value",
        series_label="ltv",
    )


# 총부채상환비율(DTI)을 계산한다.
def calculate_dti(*, annual_income: object, total_debt_payment: object) -> object:
    """총부채상환비율(DTI)을 계산합니다.

    Args:
        annual_income: 연소득. 스칼라 또는 pandas Series/Sequence.
        total_debt_payment: 연간 부채 상환액. 스칼라 또는 pandas Series/Sequence.

    Returns:
        DTI 비율. 스칼라는 float으로, pandas Series는 Series로 반환하며
        pandas가 없는 환경에서는 시퀀스 입력에 대해 float 리스트를 반환합니다.
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

    return _calculate_ratio(
        numerator=total_debt_payment,
        denominator=annual_income,
        numerator_name="total_debt_payment",
        denominator_name="annual_income",
        series_label="dti",
    )


# 총부채원리금상환비율(DSR)을 계산한다.
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

    return _calculate_ratio(
        numerator=annual_debt_service,
        denominator=annual_income,
        numerator_name="annual_debt_service",
        denominator_name="annual_income",
        series_label="dsr",
    )


def _monthly_payment(*, principal: float, monthly_interest_rate: float, months: int) -> float:
    # 원리금 균등 상환의 월 납입액을 계산한다.
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


# 균등분할 상환 스케줄을 생성한다.
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


# 금리 변화에 따른 상환 영향도를 산출한다.
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
