"""Integration tests for the OSM ingestion pipeline against a real
PostGIS database - idempotency, updates, transactional rollback, and the
resulting canonical data, not just "it runs" (doc TASK-202 §11/§12/§15).
"""

from __future__ import annotations

from pathlib import Path

import pytest
from geoalchemy2.shape import to_shape
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

import app.ingestion.osm.pipeline as pipeline_module
from app.ingestion.osm.pipeline import ingest_osm_file
from app.models.road_network import Intersection, Road, RoadSegment

FIXTURE = Path(__file__).parent.parent / "fixtures" / "osm" / "sample_extract.osm"


def _counts(stats_dict: dict) -> tuple[int, int, int]:
    return (
        stats_dict["intersections_created"],
        stats_dict["roads_created"],
        stats_dict["segments_created"],
    )


async def _table_counts(session: AsyncSession) -> tuple[int, int, int]:
    intersections = await session.scalar(select(func.count()).select_from(Intersection))
    roads = await session.scalar(select(func.count()).select_from(Road))
    segments = await session.scalar(select(func.count()).select_from(RoadSegment))
    assert intersections is not None and roads is not None and segments is not None
    return intersections, roads, segments


async def test_ingest_creates_expected_canonical_rows(db_session: AsyncSession) -> None:
    stats = await ingest_osm_file(db_session, FIXTURE, dry_run=False)
    await db_session.flush()

    # source features: 6 ways total in the fixture
    assert stats.source_features_read == 6
    # eligible: 100, 200, 700 (300/400/500 rejected)
    assert stats.eligible_road_features == 3
    assert stats.rejected_features == 3
    assert stats.validation_failures == 3

    # intersections: nodes 1, 2, 3, 4, 6, 7 (5 excludes node 5, which only
    # belongs to the rejected footway, and node 999 doesn't exist)
    assert stats.intersections_created == 6
    # roads: "Test Main Street", "Test Cross Street", "Test Reverse Road"
    assert stats.roads_created == 3
    # segments: way 100 splits into 2, way 200 -> 1, way 700 -> 1
    assert stats.segments_created == 4

    intersections, roads, segments = await _table_counts(db_session)
    assert (intersections, roads, segments) == (6, 3, 4)


async def test_ingest_persists_correct_directionality(db_session: AsyncSession) -> None:
    await ingest_osm_file(db_session, FIXTURE, dry_run=False)
    await db_session.flush()

    reverse_road_segment = await db_session.scalar(
        select(RoadSegment).where(RoadSegment.osm_way_id == 700)
    )
    assert reverse_road_segment is not None
    assert reverse_road_segment.is_oneway is True

    start = await db_session.get(Intersection, reverse_road_segment.start_intersection_id)
    end = await db_session.get(Intersection, reverse_road_segment.end_intersection_id)
    assert start is not None and start.osm_node_id == 7
    assert end is not None and end.osm_node_id == 6


async def test_ingest_is_idempotent_on_repeat_run(db_session: AsyncSession) -> None:
    stats_1 = await ingest_osm_file(db_session, FIXTURE, dry_run=False)
    await db_session.flush()
    counts_after_first = await _table_counts(db_session)

    stats_2 = await ingest_osm_file(db_session, FIXTURE, dry_run=False)
    await db_session.flush()
    counts_after_second = await _table_counts(db_session)

    assert counts_after_first == counts_after_second == (6, 3, 4)
    assert _counts(stats_1.as_dict()) == (6, 3, 4)
    # second run creates nothing new
    assert _counts(stats_2.as_dict()) == (0, 0, 0)
    assert stats_2.skipped_duplicates == 4  # all 4 segments unchanged


async def test_reingest_updates_changed_attributes(
    db_session: AsyncSession, tmp_path: Path
) -> None:
    """Re-ingesting the same osm_way_id with a changed tag must UPDATE the
    existing row, not create a duplicate - doc TASK-202 §11."""
    original = FIXTURE.read_text()
    modified = original.replace('<tag k="maxspeed" v="40"/>', '<tag k="maxspeed" v="60"/>')
    modified_file = tmp_path / "modified.osm"
    modified_file.write_text(modified)

    await ingest_osm_file(db_session, FIXTURE, dry_run=False)
    await db_session.flush()

    stats = await ingest_osm_file(db_session, modified_file, dry_run=False)
    await db_session.flush()

    assert stats.segments_created == 0
    assert stats.segments_updated >= 1

    updated_segment = await db_session.scalar(
        select(RoadSegment).where(RoadSegment.osm_way_id == 100, RoadSegment.way_seq == 0)
    )
    assert updated_segment is not None
    assert updated_segment.maxspeed_kph == 60

    intersections, roads, segments = await _table_counts(db_session)
    assert (intersections, roads, segments) == (6, 3, 4)  # no duplicates created


async def test_dry_run_does_not_mutate_database(db_session: AsyncSession) -> None:
    before = await _table_counts(db_session)

    stats = await ingest_osm_file(db_session, FIXTURE, dry_run=True)
    await db_session.flush()

    after = await _table_counts(db_session)
    assert before == after == (0, 0, 0)

    # but the stats still report what WOULD have happened
    assert _counts(stats.as_dict()) == (6, 3, 4)
    assert stats.dry_run is True


async def test_dry_run_then_real_run_produce_the_same_plan(db_session: AsyncSession) -> None:
    dry_stats = await ingest_osm_file(db_session, FIXTURE, dry_run=True)
    real_stats = await ingest_osm_file(db_session, FIXTURE, dry_run=False)

    assert _counts(dry_stats.as_dict()) == _counts(real_stats.as_dict())


async def test_forced_failure_mid_ingestion_leaves_no_partial_state(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """doc TASK-202 §12: a failed ingestion must not leave a half-written
    canonical network. Forces a failure after intersections/roads have
    already been flushed but before all segments are - the pipeline
    itself doesn't commit, so a caller-level rollback (simulated here,
    exactly what the CLI does on exception) must undo everything."""
    real_resolve_segment = pipeline_module._resolve_segment
    call_count = {"n": 0}

    async def _flaky_resolve_segment(*args, **kwargs):
        call_count["n"] += 1
        if call_count["n"] == 3:
            raise RuntimeError("forced failure for transactional test")
        return await real_resolve_segment(*args, **kwargs)

    monkeypatch.setattr(pipeline_module, "_resolve_segment", _flaky_resolve_segment)

    try:
        await ingest_osm_file(db_session, FIXTURE, dry_run=False)
        raise AssertionError("expected the forced RuntimeError to propagate")
    except RuntimeError:
        pass

    # simulate the CLI's exception handler: roll back, nothing persisted
    await db_session.rollback()

    counts = await _table_counts(db_session)
    assert counts == (0, 0, 0)


async def test_road_segment_geometry_matches_expected_coordinates(
    db_session: AsyncSession,
) -> None:
    await ingest_osm_file(db_session, FIXTURE, dry_run=False)
    await db_session.flush()

    segment = await db_session.scalar(select(RoadSegment).where(RoadSegment.osm_way_id == 200))
    assert segment is not None
    line = to_shape(segment.geometry)
    # node 2 (77.5900, 12.9710) -> node 4 (77.5910, 12.9710)
    assert list(line.coords) == [(77.5900, 12.9710), (77.5910, 12.9710)]


async def test_ingested_geometry_is_spatially_queryable(db_session: AsyncSession) -> None:
    """The GIST indexes (unchanged by migration 0003) must actually work
    against real ingested data, not just empty/synthetic rows - a
    proximity search around node 2's coordinates must find the segments
    meeting there via ST_DWithin, using the index doc TASK-201 created."""
    from geoalchemy2 import Geography
    from sqlalchemy import cast, func

    await ingest_osm_file(db_session, FIXTURE, dry_run=False)
    await db_session.flush()

    point = func.ST_SetSRID(func.ST_MakePoint(77.5900, 12.9710), 4326)
    nearby = await db_session.execute(
        select(RoadSegment.osm_way_id).where(
            func.ST_DWithin(cast(RoadSegment.geometry, Geography), cast(point, Geography), 50)
        )
    )
    way_ids = {row[0] for row in nearby}
    assert {100, 200} <= way_ids
