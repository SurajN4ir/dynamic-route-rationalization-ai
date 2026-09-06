"""Deterministic graph statistics - see docs/architecture/TASK203_DESIGN.md
§14 for what each figure means and why "connected component" specifically
means *weakly* connected for this directed graph.
"""

from __future__ import annotations

from dataclasses import dataclass

import networkx as nx


@dataclass
class GraphStats:
    node_count: int
    edge_count: int  # canonical RoadSegment rows represented (not directed edges)
    directed_edge_count: int  # actual edges in the graph (>= edge_count; 2x for bidirectional)
    self_loop_count: int
    parallel_edge_group_count: int  # (u, v) pairs with 2+ distinct edges
    isolated_node_count: int  # nodes with total degree 0
    weakly_connected_component_count: int
    total_length_m: float

    def as_dict(self) -> dict[str, object]:
        return {
            "node_count": self.node_count,
            "edge_count": self.edge_count,
            "directed_edge_count": self.directed_edge_count,
            "self_loop_count": self.self_loop_count,
            "parallel_edge_group_count": self.parallel_edge_group_count,
            "isolated_node_count": self.isolated_node_count,
            "weakly_connected_component_count": self.weakly_connected_component_count,
            "total_length_m": round(self.total_length_m, 3),
        }


def compute_stats(graph: nx.MultiDiGraph, *, canonical_segment_count: int) -> GraphStats:
    self_loops = sum(1 for u, v in graph.edges() if u == v)

    parallel_groups = 0
    for _u, neighbors in graph.adjacency():
        for _v, edges in neighbors.items():
            if len(edges) >= 2:
                parallel_groups += 1

    isolated = sum(1 for n in graph.nodes() if graph.degree(n) == 0)

    # Sum physical segment length once per canonical RoadSegment, not once
    # per directed edge - a bidirectional segment produces two edges
    # sharing the same length_m, and counting both would double the real
    # network length. The non-reversed edge is the canonical direction.
    total_length = sum(
        data.get("length_m") or 0.0
        for _u, _v, data in graph.edges(data=True)
        if not data.get("reversed")
    )

    return GraphStats(
        node_count=graph.number_of_nodes(),
        edge_count=canonical_segment_count,
        directed_edge_count=graph.number_of_edges(),
        self_loop_count=self_loops,
        parallel_edge_group_count=parallel_groups,
        isolated_node_count=isolated,
        weakly_connected_component_count=nx.number_weakly_connected_components(graph),
        total_length_m=total_length,
    )
