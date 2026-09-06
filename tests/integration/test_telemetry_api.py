"""API-level tests for POST /api/v1/telemetry and GET /api/v1/fleet - the
doc 05 error envelope, request validation, and response contract.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from tests.fixtures.transportation import flush, make_vehicle


def _body(vehicle_id: uuid.UUID, **overrides: object) -> dict:
    """The API endpoint validates clock skew against real wall-clock
    `now` (it has no way to accept an injected clock, unlike the
    pipeline-level tests) - so, unlike test_telemetry_pipeline.py's fixed
    T0, this defaults to the actual current time."""
    body = {
        "vehicle_id": str(vehicle_id),
        "timestamp": datetime.now(UTC).isoformat(),
        "latitude": 10.0,
        "longitude": 10.0,
        "speed_mps": 5.0,
        "source": "synthetic",
    }
    body.update(overrides)
    return body


async def test_valid_telemetry_is_accepted(
    api_client: AsyncClient, db_session: AsyncSession
) -> None:
    vehicle = make_vehicle()
    await flush(db_session, vehicle)

    response = await api_client.post("/api/v1/telemetry", json=_body(vehicle.id))

    assert response.status_code == 202
    payload = response.json()
    assert payload["status"] == "accepted"
    assert payload["state_updated"] is True
    assert payload["telemetry_id"] is not None


async def test_duplicate_request_is_idempotent(
    api_client: AsyncClient, db_session: AsyncSession
) -> None:
    vehicle = make_vehicle()
    await flush(db_session, vehicle)
    body = _body(vehicle.id)

    first = await api_client.post("/api/v1/telemetry", json=body)
    second = await api_client.post("/api/v1/telemetry", json=body)

    assert first.status_code == 202
    assert second.status_code == 202
    assert second.json()["status"] == "duplicate"


async def test_unknown_vehicle_returns_422_structured_error(api_client: AsyncClient) -> None:
    response = await api_client.post("/api/v1/telemetry", json=_body(uuid.uuid4()))

    assert response.status_code == 422
    error = response.json()["error"]
    assert error["code"] == "unprocessable_entity"


async def test_malformed_latitude_returns_422(
    api_client: AsyncClient, db_session: AsyncSession
) -> None:
    vehicle = make_vehicle()
    await flush(db_session, vehicle)

    response = await api_client.post("/api/v1/telemetry", json=_body(vehicle.id, latitude=999.0))

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"


async def test_missing_required_field_returns_422(
    api_client: AsyncClient, db_session: AsyncSession
) -> None:
    vehicle = make_vehicle()
    await flush(db_session, vehicle)
    body = _body(vehicle.id)
    del body["speed_mps"]

    response = await api_client.post("/api/v1/telemetry", json=body)

    assert response.status_code == 422


async def test_stale_clock_skew_returns_422(
    api_client: AsyncClient, db_session: AsyncSession
) -> None:
    vehicle = make_vehicle()
    await flush(db_session, vehicle)
    ancient = (datetime.now(UTC) - timedelta(hours=1)).isoformat()

    response = await api_client.post("/api/v1/telemetry", json=_body(vehicle.id, timestamp=ancient))

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "unprocessable_entity"


async def test_get_fleet_state_returns_ingested_vehicle(
    api_client: AsyncClient, db_session: AsyncSession
) -> None:
    vehicle = make_vehicle()
    await flush(db_session, vehicle)
    await api_client.post("/api/v1/telemetry", json=_body(vehicle.id))

    response = await api_client.get(f"/api/v1/fleet/{vehicle.id}")

    assert response.status_code == 200
    payload = response.json()
    assert payload["vehicle_id"] == str(vehicle.id)
    assert payload["latitude"] == 10.0
    assert payload["freshness"] == "live"


async def test_get_fleet_state_404_when_no_telemetry(
    api_client: AsyncClient, db_session: AsyncSession
) -> None:
    vehicle = make_vehicle()
    await flush(db_session, vehicle)

    response = await api_client.get(f"/api/v1/fleet/{vehicle.id}")

    assert response.status_code == 404


async def test_list_fleet_state_includes_ingested_vehicle(
    api_client: AsyncClient, db_session: AsyncSession
) -> None:
    vehicle = make_vehicle()
    await flush(db_session, vehicle)
    await api_client.post("/api/v1/telemetry", json=_body(vehicle.id))

    response = await api_client.get("/api/v1/fleet")

    assert response.status_code == 200
    ids = {row["vehicle_id"] for row in response.json()}
    assert str(vehicle.id) in ids
