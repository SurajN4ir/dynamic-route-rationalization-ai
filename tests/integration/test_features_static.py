"""Integration tests for ml.common.static_features.load_static_segment_features
against real PostGIS - the RoadSegment column passthrough and the
TASK-203 graph-derived intersection-degree computation."""

from __future__ import annotations

from shapely.geometry import Point
from sqlalchemy.ext.asyncio import AsyncSession

from ml.common.static_features import load_static_segment_features
from tests.fixtures.transportation import flush, make_intersection, make_road_segment


async def test_segment_columns_pass_through_unchanged(db_session: AsyncSession) -> None:
    a = make_intersection(1.0, 1.0)
    b = make_intersection(1.001, 1.001)
    await flush(db_session, a, b)
    segment = make_road_segment(
        a,
        b,
        Point(1.0, 1.0),
        Point(1.001, 1.001),
        length_m=123.4,
        road_class="residential",
        lanes=2,
        maxspeed_kph=50,
        is_oneway=True,
    )
    await flush(db_session, segment)

    features = await load_static_segment_features(db_session)

    result = features[segment.id]
    assert result.length_m == 123.4
    assert result.road_class == "residential"
    assert result.lanes == 2
    assert result.maxspeed_kph == 50
    assert result.is_oneway is True


async def test_junction_intersection_has_higher_degree_than_dead_end(
    db_session: AsyncSession,
) -> None:
    """A (dead end) -> C (junction) <- B (dead end), C -> D (dead end):
    C's degree must exceed A's/B's/D's."""
    a = make_intersection(2.0, 2.0)
    b = make_intersection(2.001, 2.0)
    c = make_intersection(2.0005, 2.001)
    d = make_intersection(2.0005, 2.002)
    await flush(db_session, a, b, c, d)
    seg_ac = make_road_segment(a, c, Point(2.0, 2.0), Point(2.0005, 2.001), is_oneway=True)
    seg_bc = make_road_segment(b, c, Point(2.001, 2.0), Point(2.0005, 2.001), is_oneway=True)
    seg_cd = make_road_segment(c, d, Point(2.0005, 2.001), Point(2.0005, 2.002), is_oneway=True)
    await flush(db_session, seg_ac, seg_bc, seg_cd)

    features = await load_static_segment_features(db_session)

    c_degree = features[seg_cd.id].start_intersection_degree
    a_degree = features[seg_ac.id].start_intersection_degree
    assert c_degree is not None and a_degree is not None
    assert c_degree > a_degree


async def test_every_canonical_segment_appears_in_the_result(db_session: AsyncSession) -> None:
    a = make_intersection(3.0, 3.0)
    b = make_intersection(3.001, 3.001)
    await flush(db_session, a, b)
    segment = make_road_segment(a, b, Point(3.0, 3.0), Point(3.001, 3.001))
    await flush(db_session, segment)

    features = await load_static_segment_features(db_session)

    assert segment.id in features
