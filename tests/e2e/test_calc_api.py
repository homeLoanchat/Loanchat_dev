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
async def test_calc_success(client: AsyncClient) -> None:
    response = await client.post(
        "/api/calc",
        json={
            "calc_type": "ltv",
            "params": {"collateral_value": 500_000_000, "loan_amount": 300_000_000},
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["type"] == "ltv"
    assert pytest.approx(body["data"]["ltv"], rel=1e-6) == 0.6


@pytest.mark.anyio
async def test_calc_invalid_type_returns_400(client: AsyncClient) -> None:
    response = await client.post(
        "/api/calc",
        json={"calc_type": "unknown", "params": {}},
    )

    assert response.status_code == 400
    body = response.json()
    assert body["success"] is False
    assert body["error"]["code"] == "INVALID_VALUE"
    assert body["error"]["field"] == "calc_type"


@pytest.mark.anyio
async def test_calc_missing_params_returns_400(client: AsyncClient) -> None:
    response = await client.post(
        "/api/calc",
        json={"calc_type": "ltv"},
    )

    assert response.status_code == 400
    body = response.json()
    assert body["success"] is False
    assert body["error"]["code"] == "INVALID_VALUE"
    assert body["error"]["field"] == "params"
