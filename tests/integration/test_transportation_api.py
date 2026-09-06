"""API-level tests for the Phase 2 read endpoints - request validation,
the doc 05 error envelope, and correct data round-tripping through the
GeoJSON serialization layer."""

from __future__ import annotations

import uuid

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from tests.fixtures.transportation import (
    flush,
    make_intersection,
    make_road,
    make_road_segment,
    make_route,
    make_route_stop,
    make_stop,
    make_vehicle,
)


async def test_list_routes_returns_seeded_route(
    api_client: AsyncClient, db_session: AsyncSession
) -> None:
    route = make_route(code="TEST_API_ROUTE")
    await flush(db_session, route)

    response = await api_client.get("/api/v1/routes")

    assert response.status_code == 200
    codes = {r["code"] for r in response.json()}
    assert "TEST_API_ROUTE" in codes


async def test_get_route_stops_returns_ordered_stops_with_geojson(
    api_client: AsyncClient, db_session: AsyncSession
) -> None:
    route = make_route()
    stop_a = make_stop(10.0, 20.0)
    stop_b = make_stop(10.001, 20.001)
    await flush(db_session, route, stop_a, stop_b)
    db_session.add(make_route_stop(route, 1, stop_b))
    db_session.add(make_route_stop(route, 0, stop_a))
    await db_session.flush()

    response = await api_client.get(f"/api/v1/routes/{route.id}/stops")

    assert response.status_code == 200
    body = response.json()
    assert [rs["sequence"] for rs in body] == [0, 1]
    assert body[0]["stop"]["location"] == {"type": "Point", "coordinates": [10.0, 20.0]}


async def test_get_route_stops_404_for_unknown_route(api_client: AsyncClient) -> None:
    response = await api_client.get(f"/api/v1/routes/{uuid.uuid4()}/stops")

    assert response.status_code == 404
    body = response.json()
    assert body["error"]["code"] == "not_found"


async def test_get_route_stops_empty_list_for_route_with_no_stops(
    api_client: AsyncClient, db_session: AsyncSession
) -> None:
    """A route that exists but has zero stops is a 200 [] , not a 404 -
    distinct from "route doesn't exist"."""
    route = make_route()
    await flush(db_session, route)

    response = await api_client.get(f"/api/v1/routes/{route.id}/stops")

    assert response.status_code == 200
    assert response.json() == []


async def test_invalid_route_id_format_returns_422(api_client: AsyncClient) -> None:
    response = await api_client.get("/api/v1/routes/not-a-uuid")

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"


async def test_stops_nearby_validates_query_params(api_client: AsyncClient) -> None:
    response = await api_client.get(
        "/api/v1/stops/nearby", params={"lat": 999, "lon": 0, "radius_m": 100}
    )

    assert response.status_code == 422


async def test_stops_nearby_returns_geojson_points(
    api_client: AsyncClient, db_session: AsyncSession
) -> None:
    stop = make_stop(60.0, 60.0, code="TEST_API_NEARBY")
    await flush(db_session, stop)

    response = await api_client.get(
        "/api/v1/stops/nearby", params={"lat": 60.0, "lon": 60.0, "radius_m": 100}
    )

    assert response.status_code == 200
    codes = {s["code"] for s in response.json()}
    assert "TEST_API_NEARBY" in codes


async def test_get_road_includes_segments(
    api_client: AsyncClient, db_session: AsyncSession
) -> None:
    from shapely.geometry import Point

    road = make_road(name="TEST_API_ROAD")
    i1 = make_intersection(70.0, 70.0)
    i2 = make_intersection(70.001, 70.001)
    await flush(db_session, road, i1, i2)
    segment = make_road_segment(i1, i2, Point(70.0, 70.0), Point(70.001, 70.001), road_id=road.id)
    await flush(db_session, segment)

    response = await api_client.get(f"/api/v1/roads/{road.id}")

    assert response.status_code == 200
    body = response.json()
    assert body["name"] == "TEST_API_ROAD"
    assert len(body["segments"]) == 1
    assert body["segments"][0]["geometry"]["type"] == "LineString"


async def test_get_vehicle_by_id(api_client: AsyncClient, db_session: AsyncSession) -> None:
    vehicle = make_vehicle(external_code="TEST_API_VEHICLE")
    await flush(db_session, vehicle)

    response = await api_client.get(f"/api/v1/vehicles/{vehicle.id}")

    assert response.status_code == 200
    assert response.json()["external_code"] == "TEST_API_VEHICLE"


async def test_get_vehicle_404(api_client: AsyncClient) -> None:
    response = await api_client.get(f"/api/v1/vehicles/{uuid.uuid4()}")

    assert response.status_code == 404
