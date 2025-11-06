"""Tests for calculation parameter normalization heuristics."""

from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


from src.api.schemas import ChatRequest
from src.services.chat_service import IntentResolution, _infer_calc_category, _normalize_calc_params


def test_does_not_infer_ltv_without_context() -> None:
    params = {
        "loan_amount": 60_000_000,
        "additional_amounts": [800_000],
    }

    normalized = _normalize_calc_params(params, message="연소득 6000만원, 기존 부채 월 80만, DSR 40% 기준")

    assert "collateral_value" not in normalized
    assert normalized["loan_amount"] == 60_000_000


def test_infers_ltv_when_message_mentions_ltv() -> None:
    params = {
        "loan_amount": 600_000_000,
        "additional_amounts": [300_000_000],
    }

    normalized = _normalize_calc_params(params, message="집값 6억, 대출 3억이면 LTV 얼마야?")

    assert normalized["collateral_value"] == 600_000_000
    assert normalized["loan_amount"] == 300_000_000
    resolution = IntentResolution(intent=None, source="test", slots=params, confidence={})
    category = _infer_calc_category(
        ChatRequest(message="집값 6억, 대출 3억이면 LTV 얼마야?"),
        resolution,
        normalized,
    )
    assert category == "ltv"


def test_monthly_debt_payment_converts_to_annual_and_prefers_dsr() -> None:
    message = "연소득 6000만원, 기존 부채 월 80만, 금리 4.5%, 30년, DSR 40% 기준 대출 한도는?"
    params = {
        "annual_income": 60_000_000,
        "monthly_debt_payment": 800_000,
        "interest_rate": 4.5,
        "interest_rate_unit": "percent",
        "term_months": 360,
        "target_dsr": 40.0,
        "target_dsr_unit": "percent",
    }

    normalized = _normalize_calc_params(dict(params), message=message)

    assert normalized["annual_debt_service"] == 9_600_000
    resolution = IntentResolution(intent=None, source="test", slots=params, confidence={})
    category = _infer_calc_category(ChatRequest(message=message), resolution, normalized)
    assert category == "dsr"


def test_ltv_inference_not_triggered_for_prepayment_question() -> None:
    message = "중도상환수수료 1.2%가 남은 대출잔액 1억 5천만 원에 적용되면 수수료는 얼마야?"
    slots = {
        "fee_rate": 1.2,
        "fee_rate_unit": "percent",
        "loan_amount": 150_000_000,
    }

    normalized = _normalize_calc_params(dict(slots), message=message)

    assert normalized["principal"] == 150_000_000
    resolution = IntentResolution(intent=None, source="test", slots=slots, confidence={})
    category = _infer_calc_category(ChatRequest(message=message), resolution, normalized)
    assert category == "prepayment_fee"
