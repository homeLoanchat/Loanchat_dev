from __future__ import annotations

import pytest

import sys
from pathlib import Path
import types

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

stub_pipeline = types.ModuleType("src.retrieval.pipeline")


class _StubRetrievalPipeline:
    def __init__(self, *args: object, **kwargs: object) -> None:
        raise RuntimeError("RetrievalPipeline should not be constructed in unit tests.")


stub_pipeline.RetrievalPipeline = _StubRetrievalPipeline
sys.modules["src.retrieval.pipeline"] = stub_pipeline

from src.api.schemas import CalcType, ChatIntent, ChatRequest
from src.services.chat_service import ChatService, MockRetriever, _get_compute


def _as_int(value: object) -> int:
    return int(str(value).replace(",", "").strip())


@pytest.fixture
def chat_service() -> ChatService:
    return ChatService(retriever=MockRetriever(), compute=_get_compute())


def test_chat_service_infers_monthly_payment_and_triggers_compute(chat_service: ChatService) -> None:
    request = ChatRequest(
        message="연이자 3.5%로 3억을 30년 상환하면?",
        intent=ChatIntent.CALCULATIONAL,
        params={"loan_amount": "300000000", "interest_rate": "3.5", "term_months": "360"},
    )

    response = chat_service.handle(request)

    assert response.type == ChatIntent.CALCULATIONAL
    assert response.category == "monthly_payment"
    assert response.metadata and response.metadata.mock is False

    data = response.data
    assert data["needs_input"] is False
    assert data["calc_type"] == CalcType.AMORTIZATION.value
    assert _as_int(data["params"]["principal"]) == 300000000
    assert data["params"]["interest_rate"] == pytest.approx(3.5)
    assert data["params"]["months"] == 360
    assert "schedule" in data["result"]
    assert len(data["result"]["schedule"]) == 360
    assert data["result"]["schedule"][0]["period"] == 1
    assert "summary" in data
    assert "월 예상 상환액" in data["summary"]
    assert data["primary_value_unit"] == "krw"
    expected_primary = int(round(data["result"]["schedule"][0]["payment"]))
    assert data["primary_value"] == expected_primary


def test_chat_service_normalizes_aliases_for_ltv(chat_service: ChatService) -> None:
    request = ChatRequest(
        message="담보인정비율 계산해줘",
        intent=ChatIntent.CALCULATIONAL,
        params={"property_value": 500_000_000, "loan_amount": 300_000_000},
    )

    response = chat_service.handle(request)

    assert response.type == ChatIntent.CALCULATIONAL
    assert response.category == "ltv"

    data = response.data
    assert data["needs_input"] is False
    assert data["calc_type"] == CalcType.LTV.value
    assert "collateral_value" in data["params"]
    assert _as_int(data["params"]["collateral_value"]) == 500_000_000
    assert data["result"]["ltv"] == pytest.approx(0.6, rel=1e-4)
    assert "summary" in data
    assert "LTV" in data["summary"]
    assert data.get("primary_value_unit") == "percent"
    assert data.get("primary_value") == pytest.approx(60.0, rel=1e-4)


def test_chat_service_derives_collateral_from_additional(chat_service: ChatService) -> None:
    request = ChatRequest(
        message="담보가치 5억에 3억 대출이면 LTV 얼마야?",
        intent=ChatIntent.CALCULATIONAL,
        params={"loan_amount": 300_000_000, "additional_amounts": [500_000_000]},
    )

    response = chat_service.handle(request)

    assert response.type == ChatIntent.CALCULATIONAL
    assert response.category == "ltv"

    data = response.data
    assert data["needs_input"] is False
    assert data["calc_type"] == CalcType.LTV.value
    assert _as_int(data["params"]["loan_amount"]) == 300_000_000
    assert _as_int(data["params"]["collateral_value"]) == 500_000_000
    assert "summary" in data
