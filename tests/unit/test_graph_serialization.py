"""Unit tests for app.graph.serialization.graph_to_dict - determinism is
the whole point of this module (doc TASK-203 §18/§10), so these tests
build the same graph with nodes/edges inserted in different orders and
assert the serialized output is identical either way.
"""

from __future__ import annotations

import uuid

import networkx as nx

from app.graph.serialization import graph_to_dict


def test_output_is_independent_of_insertion_order() -> None:
    a, b, c = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    seg1, seg2 = uuid.uuid4(), uuid.uuid4()

    g1: nx.MultiDiGraph = nx.MultiDiGraph()
    g1.add_node(a, x=1.0, y=1.0)
    g1.add_node(b, x=2.0, y=2.0)
    g1.add_node(c, x=3.0, y=3.0)
    g1.add_edge(a, b, key=seg1, reversed=False, length_m=10.0)
    g1.add_edge(b, c, key=seg2, reversed=False, length_m=20.0)

    g2: nx.MultiDiGraph = nx.MultiDiGraph()
    g2.add_node(c, x=3.0, y=3.0)
    g2.add_node(a, x=1.0, y=1.0)
    g2.add_edge(b, c, key=seg2, reversed=False, length_m=20.0)
    g2.add_node(b, x=2.0, y=2.0)
    g2.add_edge(a, b, key=seg1, reversed=False, length_m=10.0)

    assert graph_to_dict(g1) == graph_to_dict(g2)


def test_uuid_values_are_serialized_as_strings() -> None:
    a, b = uuid.uuid4(), uuid.uuid4()
    seg = uuid.uuid4()
    road_id = uuid.uuid4()
    graph: nx.MultiDiGraph = nx.MultiDiGraph()
    graph.add_node(a, intersection_id=a)
    graph.add_node(b, intersection_id=b)
    graph.add_edge(a, b, key=seg, road_segment_id=seg, road_id=road_id)

    result = graph_to_dict(graph)

    node = next(n for n in result["nodes"] if n["id"] == str(a))
    assert node["intersection_id"] == str(a)
    edge = result["edges"][0]
    assert edge["road_segment_id"] == str(seg)
    assert edge["road_id"] == str(road_id)
    assert edge["u"] == str(a)
    assert edge["v"] == str(b)
    assert edge["key"] == str(seg)


def test_non_uuid_values_pass_through_unchanged() -> None:
    a, b = uuid.uuid4(), uuid.uuid4()
    graph: nx.MultiDiGraph = nx.MultiDiGraph()
    graph.add_node(a)
    graph.add_node(b)
    graph.add_edge(a, b, key=uuid.uuid4(), length_m=42.5, is_oneway=True, road_class=None)

    edge = graph_to_dict(graph)["edges"][0]

    assert edge["length_m"] == 42.5
    assert edge["is_oneway"] is True
    assert edge["road_class"] is None


def test_edges_are_sorted_by_u_then_v_then_key() -> None:
    a, b = uuid.uuid4(), uuid.uuid4()
    seg_low, seg_high = sorted([uuid.uuid4(), uuid.uuid4()], key=str)
    graph: nx.MultiDiGraph = nx.MultiDiGraph()
    graph.add_edge(a, b, key=seg_high)
    graph.add_edge(a, b, key=seg_low)

    edges = graph_to_dict(graph)["edges"]

    assert [e["key"] for e in edges] == [str(seg_low), str(seg_high)]
