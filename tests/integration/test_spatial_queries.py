"""Spatial capability tests: SRID correctness, GIST indexes actually
exist, and the proximity query repository function returns geometrically
correct results - not just "doesn't crash"."""

from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.stops import find_stops_near
from tests.fixtures.transportation import flush, make_stop


async def test_geometry_columns_use_srid_4326(db_session: AsyncSession) -> None:
    result = await db_session.execute(
        text(
            "SELECT f_table_name, f_geometry_column, srid, type "
            "FROM geometry_columns WHERE f_table_schema = 'public'"
        )
    )
    rows = {(r.f_table_name, r.f_geometry_column): (r.srid, r.type) for r in result}

    assert rows[("stops", "location")] == (4326, "POINT")
    assert rows[("intersections", "location")] == (4326, "POINT")
    assert rows[("routes", "geometry")] == (4326, "LINESTRING")
    assert rows[("road_segments", "geometry")] == (4326, "LINESTRING")


async def test_spatial_gist_indexes_exist(db_session: AsyncSession) -> None:
    result = await db_session.execute(
        text(
            "SELECT tablename, indexname FROM pg_indexes "
            "WHERE schemaname = 'public' AND indexdef ILIKE '%USING gist%'"
        )
    )
    gist_indexes = {(r.tablename, r.indexname) for r in result}

    assert ("stops", "ix_stops_location") in gist_indexes
    assert ("intersections", "ix_intersections_location") in gist_indexes
    assert ("routes", "ix_routes_geometry") in gist_indexes
    assert ("road_segments", "ix_road_segments_geometry") in gist_indexes


async def test_find_stops_near_respects_radius(db_session: AsyncSession) -> None:
    origin_lon, origin_lat = 40.0, 40.0
    near = make_stop(origin_lon + 0.0005, origin_lat, code="TEST_NEAR")  # ~40m away
    far = make_stop(origin_lon + 0.5, origin_lat, code="TEST_FAR")  # ~40km away
    await flush(db_session, near, far)

    results = await find_stops_near(db_session, lon=origin_lon, lat=origin_lat, radius_m=200)

    codes = {s.code for s in results}
    assert "TEST_NEAR" in codes
    assert "TEST_FAR" not in codes


async def test_find_stops_near_orders_by_distance(db_session: AsyncSession) -> None:
    origin_lon, origin_lat = 50.0, 50.0
    closer = make_stop(origin_lon + 0.001, origin_lat, code="TEST_CLOSER")
    farther = make_stop(origin_lon + 0.003, origin_lat, code="TEST_FARTHER")
    # insert farther first to prove ordering isn't just insertion order
    await flush(db_session, farther, closer)

    results = await find_stops_near(db_session, lon=origin_lon, lat=origin_lat, radius_m=1000)

    codes = [s.code for s in results if s.code in {"TEST_CLOSER", "TEST_FARTHER"}]
    assert codes == ["TEST_CLOSER", "TEST_FARTHER"]
