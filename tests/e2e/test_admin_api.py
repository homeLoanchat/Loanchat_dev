from __future__ import annotations

import sys
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.api.main import app

ADMIN_TOKEN = "test-secret"


@pytest.fixture(scope="module")
async def client() -> AsyncClient:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as http_client:
        yield http_client


@pytest.mark.anyio
async def test_health_requires_token(client: AsyncClient) -> None:
    response = await client.get("/api/admin/health")
    assert response.status_code == 401


@pytest.mark.anyio
async def test_health_with_token(client: AsyncClient) -> None:
    response = await client.get("/api/admin/health", headers={"X-Admin-Token": ADMIN_TOKEN})
    assert response.status_code == 200


@pytest.mark.anyio
async def test_metrics_structure(client: AsyncClient) -> None:
    response = await client.get("/api/admin/metrics", headers={"X-Admin-Token": ADMIN_TOKEN})
    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    data = body["data"]
    assert "uptime_sec" in data
    assert "req_count" in data
    assert "token_usage" in data


@pytest.mark.anyio
async def test_invalid_token(client: AsyncClient) -> None:
    response = await client.get("/api/admin/metrics", headers={"X-Admin-Token": "invalid"})
    assert response.status_code == 403
