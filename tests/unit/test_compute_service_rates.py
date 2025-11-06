"""ComputeService interest rate normalisation tests."""

from pathlib import Path
import sys

import math


PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


from src.api.schemas import CalcType
from src.services.compute_service import ComputeService


def test_amortization_uses_percentage_rate() -> None:
    service = ComputeService()

    result = service.calculate(
        calc_type=CalcType.AMORTIZATION,
        params={
            "principal": 400_000_000,
            "interest_rate": 4.2,
            "interest_rate_unit": "percent",
            "months": 360,
        },
    )

    assert math.isclose(result["monthly_payment"], 1_956_068.69, rel_tol=1e-6)
    assert result["interest_rate"] == 4.2
    assert result["interest_rate_unit"] == "annual_pct"
    assert result["interest_rate_display"] == "4.20%"


def test_prepayment_fee_calculation() -> None:
    service = ComputeService()

    result = service.calculate(
        calc_type=CalcType.PREPAYMENT_FEE,
        params={
            "principal": 150_000_000,
            "fee_rate": 1.2,
        },
    )

    assert math.isclose(result["fee_amount"], 1_800_000.0, rel_tol=1e-9)
    assert result["principal"] == 150_000_000.0
    assert result["fee_rate"] == 1.2
