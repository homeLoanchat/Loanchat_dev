from __future__ import annotations

import sys
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.api.main import app


@pytest.fixture(scope="module")
async def client() -> AsyncClient:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as http_client:
        yield http_client


@pytest.mark.anyio
async def test_informational_success(client: AsyncClient) -> None:
    response = await client.post(
        "/api/chat",
        json={
            "message": "전세자금대출 한도가 궁금해요",
            "intent": "informational",
            "category": "loan_limit",
        },
    )

    assert response.status_code == 200
    body = response.json()

    assert body["success"] is True
    assert body["type"] == "informational"
    assert isinstance(body["data"].get("answer"), str)
    assert body["data"].get("query") == "전세자금대출 한도가 궁금해요"
    assert isinstance(body["data"].get("sources"), list)
    assert body["metadata"]["mock"] is False


@pytest.mark.anyio
async def test_calculational_success(client: AsyncClient) -> None:
    response = await client.post(
        "/api/chat",
        json={
            "message": "예상 상환 금액을 계산해줘",
            "intent": "calculational",
            "category": "monthly_payment",
            "params": {"loan_amount": 30_000_000, "rate": 5.5, "term_months": 36},
        },
    )

    assert response.status_code == 200
    body = response.json()

    assert body["success"] is True
    assert body["type"] == "calculational"
    assert body["data"]["result"] == 32_500_000
    assert body["metadata"]["mock"] is True


@pytest.mark.anyio
async def test_invalid_category_returns_400(client: AsyncClient) -> None:
    response = await client.post(
        "/api/chat",
        json={
            "message": "지원하지 않는 카테고리",
            "intent": "informational",
            "category": "unknown",
        },
    )

    assert response.status_code == 400
    body = response.json()

    assert body["success"] is False
    assert body["error"]["code"] == "INVALID_VALUE"
    assert body["error"]["field"] == "category"


@pytest.mark.anyio
async def test_missing_required_field_returns_422(client: AsyncClient) -> None:
    response = await client.post(
        "/api/chat",
        json={"intent": "informational"},
    )

    assert response.status_code == 422
    body = response.json()

    assert body["success"] is False
    assert body["error"]["code"] == "INVALID_VALUE"
    assert "errors" in body["error"]["details"]
