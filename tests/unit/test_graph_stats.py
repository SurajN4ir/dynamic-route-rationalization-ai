"""Unit tests for app.graph.stats.compute_stats - pure in-memory
MultiDiGraph construction, no database involved. Attribute shapes mirror
exactly what app.graph.builder.build_road_graph produces (road_segment_id
as edge key, `reversed` flag, `length_m`) without going through the
builder itself.
"""

from __future__ import annotations

import uuid

import networkx as nx

from app.graph.stats import compute_stats


def _seg_id() -> uuid.UUID:
    return uuid.uuid4()


def test_node_and_edge_counts_are_reported_separately() -> None:
    """`edge_count` is the canonical RoadSegment count; `directed_edge_count`
    is the actual number of graph edges - a bidirectional segment produces
    two of the latter for one of the former."""
    graph: nx.MultiDiGraph = nx.MultiDiGraph()
    a, b = uuid.uuid4(), uuid.uuid4()
    seg = _seg_id()
    graph.add_node(a)
    graph.add_node(b)
    graph.add_edge(a, b, key=seg, reversed=False, length_m=100.0)
    graph.add_edge(b, a, key=seg, reversed=True, length_m=100.0)

    stats = compute_stats(graph, canonical_segment_count=1)

    assert stats.node_count == 2
    assert stats.edge_count == 1
    assert stats.directed_edge_count == 2


def test_self_loop_is_counted_once() -> None:
    graph: nx.MultiDiGraph = nx.MultiDiGraph()
    a = uuid.uuid4()
    graph.add_node(a)
    graph.add_edge(a, a, key=_seg_id(), reversed=False, length_m=0.0)

    stats = compute_stats(graph, canonical_segment_count=1)

    assert stats.self_loop_count == 1


def test_parallel_edges_between_same_pair_are_detected() -> None:
    """Two distinct RoadSegments legitimately connecting the same
    intersection pair (e.g. divided carriageways) form a parallel-edge
    group of size 2 - the group is counted once, not once per edge."""
    graph: nx.MultiDiGraph = nx.MultiDiGraph()
    a, b = uuid.uuid4(), uuid.uuid4()
    graph.add_edge(a, b, key=_seg_id(), reversed=False, length_m=50.0)
    graph.add_edge(a, b, key=_seg_id(), reversed=False, length_m=52.0)

    stats = compute_stats(graph, canonical_segment_count=2)

    assert stats.parallel_edge_group_count == 1


def test_isolated_node_has_zero_degree() -> None:
    graph: nx.MultiDiGraph = nx.MultiDiGraph()
    a, b, isolated = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    graph.add_node(isolated)
    graph.add_edge(a, b, key=_seg_id(), reversed=False, length_m=10.0)

    stats = compute_stats(graph, canonical_segment_count=1)

    assert stats.isolated_node_count == 1


def test_disconnected_components_are_counted_separately() -> None:
    graph: nx.MultiDiGraph = nx.MultiDiGraph()
    a, b, c, d = (uuid.uuid4() for _ in range(4))
    graph.add_edge(a, b, key=_seg_id(), reversed=False, length_m=10.0)
    graph.add_edge(c, d, key=_seg_id(), reversed=False, length_m=10.0)

    stats = compute_stats(graph, canonical_segment_count=2)

    assert stats.weakly_connected_component_count == 2


def test_total_length_counts_each_canonical_segment_once() -> None:
    """A bidirectional segment's length must not be double-counted just
    because it produces two directed edges - only the non-reversed edge
    contributes to total_length_m."""
    graph: nx.MultiDiGraph = nx.MultiDiGraph()
    a, b = uuid.uuid4(), uuid.uuid4()
    seg = _seg_id()
    graph.add_edge(a, b, key=seg, reversed=False, length_m=123.456)
    graph.add_edge(b, a, key=seg, reversed=True, length_m=123.456)

    stats = compute_stats(graph, canonical_segment_count=1)

    assert stats.total_length_m == 123.456


def test_total_length_treats_missing_length_as_zero() -> None:
    graph: nx.MultiDiGraph = nx.MultiDiGraph()
    a, b = uuid.uuid4(), uuid.uuid4()
    graph.add_edge(a, b, key=_seg_id(), reversed=False, length_m=None)

    stats = compute_stats(graph, canonical_segment_count=1)

    assert stats.total_length_m == 0.0


def test_as_dict_rounds_total_length_to_three_decimals() -> None:
    graph: nx.MultiDiGraph = nx.MultiDiGraph()
    a, b = uuid.uuid4(), uuid.uuid4()
    graph.add_edge(a, b, key=_seg_id(), reversed=False, length_m=1.0 / 3)

    stats = compute_stats(graph, canonical_segment_count=1)

    assert stats.as_dict()["total_length_m"] == round(1.0 / 3, 3)
