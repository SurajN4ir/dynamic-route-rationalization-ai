"""Unit tests for app.graph.validation.validate_graph - pure in-memory
graphs and synthetic segment_rows, no database involved. Validation never
repairs data, it only reports, so every test here checks the reported
issue set rather than any mutation of the graph.
"""

from __future__ import annotations

import uuid

import networkx as nx

from app.graph.validation import validate_graph


def _ids(n: int) -> list[uuid.UUID]:
    return [uuid.uuid4() for _ in range(n)]


def test_well_formed_bidirectional_segment_is_valid() -> None:
    a, b, seg = _ids(3)
    graph: nx.MultiDiGraph = nx.MultiDiGraph()
    graph.add_node(a)
    graph.add_node(b)
    graph.add_edge(a, b, key=seg, reversed=False)
    graph.add_edge(b, a, key=seg, reversed=True)

    report = validate_graph(
        graph,
        known_intersection_ids={a, b},
        segment_rows=[(seg, a, b, False)],
    )

    assert report.is_valid
    assert report.errors == []


def test_well_formed_oneway_segment_is_valid() -> None:
    a, b, seg = _ids(3)
    graph: nx.MultiDiGraph = nx.MultiDiGraph()
    graph.add_node(a)
    graph.add_node(b)
    graph.add_edge(a, b, key=seg, reversed=False)

    report = validate_graph(
        graph,
        known_intersection_ids={a, b},
        segment_rows=[(seg, a, b, True)],
    )

    assert report.is_valid


def test_graph_node_with_no_matching_intersection_is_orphan() -> None:
    a = uuid.uuid4()
    graph: nx.MultiDiGraph = nx.MultiDiGraph()
    graph.add_node(a)

    report = validate_graph(graph, known_intersection_ids=set(), segment_rows=[])

    assert not report.is_valid
    assert [i.code for i in report.errors] == ["orphan_graph_node"]


def test_known_intersection_missing_from_graph_is_reported() -> None:
    a = uuid.uuid4()
    graph: nx.MultiDiGraph = nx.MultiDiGraph()

    report = validate_graph(graph, known_intersection_ids={a}, segment_rows=[])

    assert not report.is_valid
    assert [i.code for i in report.errors] == ["missing_graph_node"]


def test_segment_referencing_unknown_start_is_reported() -> None:
    a, b, seg = _ids(3)
    graph: nx.MultiDiGraph = nx.MultiDiGraph()
    graph.add_node(b)

    report = validate_graph(
        graph,
        known_intersection_ids={b},
        segment_rows=[(seg, a, b, True)],
    )

    codes = [i.code for i in report.errors]
    assert "segment_references_unknown_start" in codes


def test_segment_referencing_unknown_end_is_reported() -> None:
    a, b, seg = _ids(3)
    graph: nx.MultiDiGraph = nx.MultiDiGraph()
    graph.add_node(a)

    report = validate_graph(
        graph,
        known_intersection_ids={a},
        segment_rows=[(seg, a, b, True)],
    )

    codes = [i.code for i in report.errors]
    assert "segment_references_unknown_end" in codes


def test_missing_forward_edge_is_reported() -> None:
    """A canonical segment with no corresponding graph edge at all -
    the builder failed to materialize it."""
    a, b, seg = _ids(3)
    graph: nx.MultiDiGraph = nx.MultiDiGraph()
    graph.add_node(a)
    graph.add_node(b)

    report = validate_graph(
        graph,
        known_intersection_ids={a, b},
        segment_rows=[(seg, a, b, True)],
    )

    assert [i.code for i in report.errors] == ["missing_forward_edge"]


def test_oneway_segment_with_unexpected_reverse_edge_is_reported() -> None:
    a, b, seg = _ids(3)
    graph: nx.MultiDiGraph = nx.MultiDiGraph()
    graph.add_node(a)
    graph.add_node(b)
    graph.add_edge(a, b, key=seg, reversed=False)
    graph.add_edge(b, a, key=seg, reversed=True)  # should not exist for a oneway segment

    report = validate_graph(
        graph,
        known_intersection_ids={a, b},
        segment_rows=[(seg, a, b, True)],
    )

    assert [i.code for i in report.errors] == ["unexpected_reverse_edge"]


def test_bidirectional_segment_missing_reverse_edge_is_reported() -> None:
    a, b, seg = _ids(3)
    graph: nx.MultiDiGraph = nx.MultiDiGraph()
    graph.add_node(a)
    graph.add_node(b)
    graph.add_edge(a, b, key=seg, reversed=False)  # reverse missing

    report = validate_graph(
        graph,
        known_intersection_ids={a, b},
        segment_rows=[(seg, a, b, False)],
    )

    assert [i.code for i in report.errors] == ["missing_reverse_edge"]


def test_oneway_self_loop_does_not_trigger_unexpected_reverse_edge() -> None:
    """Regression: a self-loop's forward and reverse queries collapse to
    the identical (u, v, key) triple, so without a guard a one-way
    self-loop would incorrectly appear to have "a reverse edge"."""
    a, seg = _ids(2)
    graph: nx.MultiDiGraph = nx.MultiDiGraph()
    graph.add_node(a)
    graph.add_edge(a, a, key=seg, reversed=False)

    report = validate_graph(
        graph,
        known_intersection_ids={a},
        segment_rows=[(seg, a, a, True)],
    )

    assert report.is_valid


def test_missing_start_short_circuits_further_checks_for_that_segment() -> None:
    """Once start is reported unknown, the end/forward/reverse checks for
    that same segment are skipped rather than piling on redundant noise."""
    a, b, seg = _ids(3)
    graph: nx.MultiDiGraph = nx.MultiDiGraph()
    graph.add_node(b)

    report = validate_graph(
        graph,
        known_intersection_ids={b},
        segment_rows=[(seg, a, b, True)],
    )

    assert len(report.errors) == 1
