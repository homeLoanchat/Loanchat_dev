from __future__ import annotations

import sys
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

pytestmark = pytest.mark.skip(reason="calc API contract only; implementation pending")

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.api.main import app


@pytest.fixture(scope="module")
async def client() -> AsyncClient:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as http_client:
        yield http_client


# 계약상 정상 시나리오: 허용된 파라미터로 LTV를 계산해야 한다.
@pytest.mark.anyio
async def test_calc_ltv_success(client: AsyncClient) -> None:
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
    assert body["data"]["ratio"] == pytest.approx(0.6, rel=1e-6)


# 정책 위반 시나리오: DTI가 한도를 초과하면 범위 에러를 반환해야 한다.
@pytest.mark.anyio
async def test_calc_dti_policy_violation(client: AsyncClient) -> None:
    response = await client.post(
        "/api/calc",
        json={
            "calc_type": "dti",
            "params": {"annual_income": 80_000_000, "total_debt_payment": 50_000_000},
        },
    )

    assert response.status_code == 400
    body = response.json()
    assert body["success"] is False
    assert body["error"]["code"] == "INVALID_RANGE"
    assert body["error"]["field"] == "total_debt_payment"
