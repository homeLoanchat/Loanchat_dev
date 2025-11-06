"""Tests for mortgage slot extraction heuristics."""

from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


from src.nlp.slot_intent import extract_intent_and_slots


def test_interest_rates_not_misclassified_as_amounts() -> None:
    message = "주택담보대출 금리 4.2%, 30년 원리금균등으로 4억 원 빌리면 월 납입액이 얼마일까?"
    slots = extract_intent_and_slots(message)["slots"]

    assert slots["interest_rate"] == 4.2
    assert slots["interest_rate_unit"] == "percent"
    assert slots["term_months"] == 360
    assert slots["loan_amount"] == 400_000_000


def test_rate_change_question_does_not_create_fake_principal() -> None:
    message = "변동금리 3.5%에서 5%로 오르면 월 상환액이 얼마나 늘어나?"
    slots = extract_intent_and_slots(message)["slots"]

    assert slots["interest_rate"] == 3.5
    assert slots["interest_rate_unit"] == "percent"
    assert "loan_amount" not in slots


def test_prepayment_fee_percentage_not_treated_as_amount() -> None:
    message = "중도상환수수료 1.2%가 남은 대출잔액 1억 5천만 원에 적용되면 수수료는 얼마야?"
    slots = extract_intent_and_slots(message)["slots"]

    assert slots["interest_rate"] == 1.2
    assert slots["interest_rate_unit"] == "percent"
    assert slots["loan_amount"] == 100_000_000


def test_dsr_question_extracts_income_debt_and_target() -> None:
    message = "연소득 6000만원, 기존 부채 월 80만, 금리 4.5%, 30년, DSR 40% 기준 대출 한도는?"
    slots = extract_intent_and_slots(message)["slots"]

    assert slots["annual_income"] == 60_000_000
    assert slots["monthly_debt_payment"] == 800_000
    assert slots["annual_debt_service"] == 9_600_000
    assert slots["target_dsr"] == 40.0
