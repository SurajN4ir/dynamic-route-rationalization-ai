"""Integration tests for app.graph.builder.build_road_graph against real
PostGIS (see tests/integration/conftest.py) - node/edge mapping,
traceability back to canonical rows, and the explicit CASE A-G scenarios
from TASK-203 §22.

Each test creates its own isolated intersections/segments inside the
rolled-back transaction, so cases never interact with each other or with
whatever seed data happens to be in the database.
"""

from __future__ import annotations

import networkx as nx
from shapely.geometry import Point
from sqlalchemy.ext.asyncio import AsyncSession

from app.graph.builder import build_road_graph, load_known_intersection_ids
from app.graph.serialization import graph_to_dict
from app.graph.validation import validate_graph
from tests.fixtures.transportation import flush, make_intersection, make_road_segment


async def test_intersection_maps_to_a_node_with_expected_attributes(
    db_session: AsyncSession,
) -> None:
    intersection = make_intersection(12.5, 34.5, osm_node_id=999, source="osm")
    await flush(db_session, intersection)

    result = await build_road_graph(db_session)

    assert intersection.id in result.graph.nodes
    attrs = result.graph.nodes[intersection.id]
    assert attrs["intersection_id"] == intersection.id
    assert attrs["osm_node_id"] == 999
    assert attrs["source"] == "osm"
    assert attrs["x"] == 12.5
    assert attrs["y"] == 34.5


async def test_edge_traces_back_to_its_canonical_road_segment(
    db_session: AsyncSession,
) -> None:
    a = make_intersection(0.0, 0.0)
    b = make_intersection(0.001, 0.001)
    await flush(db_session, a, b)
    segment = make_road_segment(
        a,
        b,
        Point(0.0, 0.0),
        Point(0.001, 0.001),
        is_oneway=True,
        road_class="residential",
        length_m=157.3,
        maxspeed_kph=50,
        lanes=2,
        access="yes",
        osm_way_id=42,
        way_seq=0,
    )
    await flush(db_session, segment)

    result = await build_road_graph(db_session)

    edge = result.graph[a.id][b.id][segment.id]
    assert edge["road_segment_id"] == segment.id
    assert edge["road_id"] is None
    assert edge["is_oneway"] is True
    assert edge["road_class"] == "residential"
    assert edge["length_m"] == 157.3
    assert edge["weight"] == 157.3
    assert edge["maxspeed_kph"] == 50
    assert edge["lanes"] == 2
    assert edge["access"] == "yes"
    assert edge["osm_way_id"] == 42
    assert edge["way_seq"] == 0
    assert edge["reversed"] is False


async def test_case_a_bidirectional_road_produces_both_directions(
    db_session: AsyncSession,
) -> None:
    a = make_intersection(1.0, 1.0)
    b = make_intersection(1.001, 1.001)
    await flush(db_session, a, b)
    segment = make_road_segment(a, b, Point(1.0, 1.0), Point(1.001, 1.001), is_oneway=False)
    await flush(db_session, segment)

    result = await build_road_graph(db_session)

    assert result.graph.has_edge(a.id, b.id, key=segment.id)
    assert result.graph.has_edge(b.id, a.id, key=segment.id)
    assert result.graph[a.id][b.id][segment.id]["reversed"] is False
    assert result.graph[b.id][a.id][segment.id]["reversed"] is True


async def test_case_b_oneway_road_produces_only_forward_direction(
    db_session: AsyncSession,
) -> None:
    a = make_intersection(2.0, 2.0)
    b = make_intersection(2.001, 2.001)
    await flush(db_session, a, b)
    segment = make_road_segment(a, b, Point(2.0, 2.0), Point(2.001, 2.001), is_oneway=True)
    await flush(db_session, segment)

    result = await build_road_graph(db_session)

    assert result.graph.has_edge(a.id, b.id, key=segment.id)
    assert not result.graph.has_edge(b.id, a.id, key=segment.id)


async def test_case_c_graph_follows_canonical_start_end_not_raw_osm_orientation(
    db_session: AsyncSession,
) -> None:
    """The graph builder never reads raw OSM tags - it only ever sees
    start_intersection_id/end_intersection_id/is_oneway, which TASK-202
    already normalized (reversing node order for oneway=-1 ways). A
    segment recorded as B->A must produce a B->A edge regardless of what
    the original OSM way direction looked like."""
    a = make_intersection(3.0, 3.0)
    b = make_intersection(3.001, 3.001)
    await flush(db_session, a, b)
    # Simulates topology.py's output for a reversed (oneway=-1) OSM way:
    # start/end are already swapped by ingestion, well before the graph
    # builder ever sees this row.
    segment = make_road_segment(b, a, Point(3.001, 3.001), Point(3.0, 3.0), is_oneway=True)
    await flush(db_session, segment)

    result = await build_road_graph(db_session)

    assert result.graph.has_edge(b.id, a.id, key=segment.id)
    assert not result.graph.has_edge(a.id, b.id, key=segment.id)


async def test_case_d_junction_has_all_incident_edges(db_session: AsyncSession) -> None:
    a = make_intersection(4.0, 4.0)
    b = make_intersection(4.001, 4.0)
    c = make_intersection(4.0005, 4.001)
    d = make_intersection(4.0005, 4.002)
    e = make_intersection(4.002, 4.002)
    await flush(db_session, a, b, c, d, e)

    seg_ac = make_road_segment(a, c, Point(4.0, 4.0), Point(4.0005, 4.001), is_oneway=True)
    seg_bc = make_road_segment(b, c, Point(4.001, 4.0), Point(4.0005, 4.001), is_oneway=True)
    seg_cd = make_road_segment(c, d, Point(4.0005, 4.001), Point(4.0005, 4.002), is_oneway=True)
    seg_ce = make_road_segment(c, e, Point(4.0005, 4.001), Point(4.002, 4.002), is_oneway=True)
    await flush(db_session, seg_ac, seg_bc, seg_cd, seg_ce)

    result = await build_road_graph(db_session)

    assert result.graph.has_edge(a.id, c.id, key=seg_ac.id)
    assert result.graph.has_edge(b.id, c.id, key=seg_bc.id)
    assert result.graph.has_edge(c.id, d.id, key=seg_cd.id)
    assert result.graph.has_edge(c.id, e.id, key=seg_ce.id)


async def test_case_e_multiple_segments_between_same_pair_stay_distinct(
    db_session: AsyncSession,
) -> None:
    """Two RoadSegments legitimately connecting the same intersection
    pair (e.g. divided carriageways) must remain two distinct edges, not
    collapsed into one - this is exactly why the graph is a MultiDiGraph."""
    a = make_intersection(5.0, 5.0)
    b = make_intersection(5.001, 5.001)
    await flush(db_session, a, b)
    seg1 = make_road_segment(
        a, b, Point(5.0, 5.0), Point(5.001, 5.001), is_oneway=True, length_m=100.0
    )
    seg2 = make_road_segment(
        a, b, Point(5.0, 5.0), Point(5.0011, 5.0011), is_oneway=True, length_m=105.0
    )
    await flush(db_session, seg1, seg2)

    result = await build_road_graph(db_session)

    assert result.graph.has_edge(a.id, b.id, key=seg1.id)
    assert result.graph.has_edge(a.id, b.id, key=seg2.id)
    assert result.graph.number_of_edges(a.id, b.id) == 2
    assert result.stats.parallel_edge_group_count >= 1


async def test_case_f_disconnected_components_remain_separate(
    db_session: AsyncSession,
) -> None:
    a = make_intersection(6.0, 6.0)
    b = make_intersection(6.001, 6.001)
    c = make_intersection(60.0, 60.0)
    d = make_intersection(60.001, 60.001)
    await flush(db_session, a, b, c, d)
    seg_ab = make_road_segment(a, b, Point(6.0, 6.0), Point(6.001, 6.001), is_oneway=False)
    seg_cd = make_road_segment(c, d, Point(60.0, 60.0), Point(60.001, 60.001), is_oneway=False)
    await flush(db_session, seg_ab, seg_cd)

    result = await build_road_graph(db_session)

    components = list(nx.weakly_connected_components(result.graph))
    ab_component = next(comp for comp in components if a.id in comp)
    cd_component = next(comp for comp in components if c.id in comp)
    assert ab_component != cd_component
    assert b.id in ab_component
    assert d.id in cd_component


async def test_case_g_rebuild_from_unchanged_data_is_identical(
    db_session: AsyncSession,
) -> None:
    a = make_intersection(7.0, 7.0)
    b = make_intersection(7.001, 7.001)
    await flush(db_session, a, b)
    segment = make_road_segment(
        a, b, Point(7.0, 7.0), Point(7.001, 7.001), is_oneway=False, length_m=88.0
    )
    await flush(db_session, segment)

    first = await build_road_graph(db_session)
    second = await build_road_graph(db_session)

    assert graph_to_dict(first.graph) == graph_to_dict(second.graph)
    assert first.stats == second.stats


async def test_self_loop_segment_is_permitted_and_reported_once(
    db_session: AsyncSession,
) -> None:
    """Nothing in the canonical schema forbids start == end (e.g. a real
    loop road); the builder must not reject or silently discard it, and
    validation must not misreport it as having an unexpected reverse."""
    node = make_intersection(8.0, 8.0)
    await flush(db_session, node)
    segment = make_road_segment(
        node, node, Point(8.0, 8.0), Point(8.0001, 8.0001), is_oneway=True, length_m=25.0
    )
    await flush(db_session, segment)

    result = await build_road_graph(db_session)

    assert result.graph.has_edge(node.id, node.id, key=segment.id)
    assert result.graph.number_of_edges(node.id, node.id) == 1
    assert result.stats.self_loop_count == 1

    known_ids = await load_known_intersection_ids(db_session)
    segment_rows = [
        (data["road_segment_id"], u, v, data["is_oneway"])
        for u, v, data in result.graph.edges(data=True)
        if not data["reversed"]
    ]
    report = validate_graph(
        result.graph, known_intersection_ids=known_ids, segment_rows=segment_rows
    )
    assert report.is_valid


async def test_load_known_intersection_ids_matches_graph_nodes_for_well_formed_data(
    db_session: AsyncSession,
) -> None:
    a = make_intersection(9.0, 9.0)
    b = make_intersection(9.001, 9.001)
    await flush(db_session, a, b)
    segment = make_road_segment(a, b, Point(9.0, 9.0), Point(9.001, 9.001), is_oneway=False)
    await flush(db_session, segment)

    result = await build_road_graph(db_session)
    known_ids = await load_known_intersection_ids(db_session)

    assert set(result.graph.nodes()) <= known_ids
    segment_rows = [
        (data["road_segment_id"], u, v, data["is_oneway"])
        for u, v, data in result.graph.edges(data=True)
        if not data["reversed"]
    ]
    report = validate_graph(
        result.graph, known_intersection_ids=known_ids, segment_rows=segment_rows
    )
    assert report.is_valid
