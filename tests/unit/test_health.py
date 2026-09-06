"""Liveness must never depend on external infrastructure - see
app/api/health.py and docs/architecture/02-non-functional-requirements.md
2.3 (observation must survive a dependency outage). These tests run with
no database or Redis available and must still pass.
"""

from httpx import AsyncClient


async def test_liveness_returns_ok(client: AsyncClient) -> None:
    response = await client.get("/healthz")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


async def test_liveness_does_not_require_request_body(client: AsyncClient) -> None:
    response = await client.get("/healthz", params={"unexpected": "ignored"})

    assert response.status_code == 200


async def test_status_endpoint_reports_real_metadata(client: AsyncClient) -> None:
    response = await client.get("/api/v1/status")

    assert response.status_code == 200
    body = response.json()
    assert body["name"] == "AURA API"
    assert body["environment"] == "ci"  # set in tests/conftest.py
    assert "version" in body


async def test_request_id_header_is_always_present(client: AsyncClient) -> None:
    response = await client.get("/healthz")

    assert "x-request-id" in response.headers


async def test_request_id_is_propagated_when_supplied(client: AsyncClient) -> None:
    response = await client.get("/healthz", headers={"X-Request-ID": "test-fixed-id"})

    assert response.headers["x-request-id"] == "test-fixed-id"
