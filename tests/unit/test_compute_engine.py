from __future__ import annotations

import math

import pytest

from src.compute.engine import (
    calculate_amortization_schedule,
    calculate_dsr,
    calculate_dti,
    calculate_ltv,
    calculate_payment_sensitivity,
)


def _monthly_payment(principal: float, annual_rate: float, months: int) -> float:
    monthly_rate = annual_rate / 12
    if monthly_rate == 0:
        return principal / months
    factor = (1 + monthly_rate) ** months
    return principal * monthly_rate * factor / (factor - 1)


def test_calculate_ltv_scalar() -> None:
    result = calculate_ltv(collateral_value=500_000, loan_amount=350_000)
    assert math.isclose(result, 0.7, rel_tol=1e-9)


def test_calculate_ltv_pandas_series() -> None:
    pd = pytest.importorskip("pandas")
    collateral = pd.Series([700_000, 800_000], name="collateral")
    loan = pd.Series([350_000, 400_000], name="loan")

    result = calculate_ltv(collateral_value=collateral, loan_amount=loan)

    assert list(result.index) == [0, 1]
    assert result.tolist() == pytest.approx([0.5, 0.5], rel=1e-9)


def test_calculate_ltv_sequence_without_pandas(monkeypatch: pytest.MonkeyPatch) -> None:
    from src.compute import engine

    monkeypatch.setattr(engine, "_pd", None)
    result = calculate_ltv(
        collateral_value=[700_000, 800_000],
        loan_amount=[350_000, 400_000],
    )
    assert result == pytest.approx([0.5, 0.5], rel=1e-9)


def test_calculate_dti_and_dsr_scalar() -> None:
    dti = calculate_dti(annual_income=80_000, total_debt_payment=24_000)
    dsr = calculate_dsr(annual_income=80_000, annual_debt_service=30_000)
    assert math.isclose(dti, 0.3, rel_tol=1e-9)
    assert math.isclose(dsr, 0.375, rel_tol=1e-9)


def test_calculate_dti_invalid_income() -> None:
    with pytest.raises(ValueError):
        calculate_dti(annual_income=0, total_debt_payment=10_000)


def test_amortization_schedule_structure() -> None:
    schedule = calculate_amortization_schedule(principal=100_000, interest_rate=0.04, months=360)
    assert len(schedule) == 360
    first = schedule[0]
    assert first["period"] == 1
    assert math.isclose(first["payment"], 477.42, rel_tol=1e-3)
    assert math.isclose(schedule[-1]["balance"], 0.0, abs_tol=0.05)


def test_amortization_schedule_zero_interest() -> None:
    schedule = calculate_amortization_schedule(principal=12_000, interest_rate=0.0, months=12)
    assert all(math.isclose(entry["interest"], 0.0, abs_tol=1e-9) for entry in schedule)
    assert all(math.isclose(entry["payment"], 1_000.0, abs_tol=1e-6) for entry in schedule)
    assert math.isclose(schedule[-1]["balance"], 0.0, abs_tol=1e-9)


def test_amortization_schedule_dataframe_output() -> None:
    pd = pytest.importorskip("pandas")
    df = calculate_amortization_schedule(
        principal=10_000,
        interest_rate=0.05,
        months=24,
        as_dataframe=True,
    )
    assert list(df.columns) == ["period", "payment", "principal", "interest", "balance"]
    assert len(df) == 24


def test_payment_sensitivity_monotonicity() -> None:
    rates = [0.02, 0.03, 0.04]
    sensitivity = calculate_payment_sensitivity(principal=300_000, interest_rates=rates, months=360)
    payments = [row["monthly_payment"] for row in sensitivity]
    assert payments == sorted(payments)


def test_payment_sensitivity_dataframe_output() -> None:
    pd = pytest.importorskip("pandas")
    df = calculate_payment_sensitivity(
        principal=300_000,
        interest_rates=[0.03, 0.035],
        months=360,
        as_dataframe=True,
    )
    assert list(df.columns) == ["interest_rate", "monthly_payment", "total_payment", "total_interest"]
    expected = round(_monthly_payment(300_000, 0.03, 360), 2)
    assert math.isclose(df.iloc[0]["monthly_payment"], expected, abs_tol=1e-9)


def test_payment_sensitivity_requires_rates() -> None:
    with pytest.raises(ValueError):
        calculate_payment_sensitivity(principal=100_000, interest_rates=[], months=120)
