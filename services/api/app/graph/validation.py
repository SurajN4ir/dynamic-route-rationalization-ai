"""Graph validation - see docs/architecture/TASK203_DESIGN.md §15/§11/§12.

Validation never "repairs" data - it only reports. A failure here means
the canonical PostGIS data (or the builder itself) violates a required
invariant and needs investigation, not silent correction.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Literal

import networkx as nx

Severity = Literal["error", "warning"]


@dataclass(frozen=True, slots=True)
class ValidationIssue:
    severity: Severity
    code: str
    message: str


@dataclass
class ValidationReport:
    issues: list[ValidationIssue] = field(default_factory=list)

    @property
    def errors(self) -> list[ValidationIssue]:
        return [i for i in self.issues if i.severity == "error"]

    @property
    def warnings(self) -> list[ValidationIssue]:
        return [i for i in self.issues if i.severity == "warning"]

    @property
    def is_valid(self) -> bool:
        return not self.errors

    def as_dict(self) -> dict[str, object]:
        return {
            "is_valid": self.is_valid,
            "errors": [{"code": i.code, "message": i.message} for i in self.errors],
            "warnings": [{"code": i.code, "message": i.message} for i in self.warnings],
        }


def validate_graph(
    graph: nx.MultiDiGraph,
    *,
    known_intersection_ids: set[uuid.UUID],
    segment_rows: list[tuple[uuid.UUID, uuid.UUID, uuid.UUID, bool]],
) -> ValidationReport:
    """`segment_rows` is `(segment_id, start_intersection_id,
    end_intersection_id, is_oneway)` for every canonical RoadSegment -
    the same rows the builder used, so validation checks the graph
    against the same source of truth, not against itself."""
    report = ValidationReport()

    graph_node_ids = set(graph.nodes())
    orphan_nodes = graph_node_ids - known_intersection_ids
    for node_id in sorted(orphan_nodes, key=str):
        report.issues.append(
            ValidationIssue(
                "error",
                "orphan_graph_node",
                f"graph node {node_id} does not correspond to a known Intersection",
            )
        )

    missing_nodes = known_intersection_ids - graph_node_ids
    for node_id in sorted(missing_nodes, key=str):
        report.issues.append(
            ValidationIssue(
                "error",
                "missing_graph_node",
                f"Intersection {node_id} has no corresponding graph node",
            )
        )

    for segment_id, start_id, end_id, is_oneway in segment_rows:
        if start_id not in known_intersection_ids:
            report.issues.append(
                ValidationIssue(
                    "error",
                    "segment_references_unknown_start",
                    f"RoadSegment {segment_id} start_intersection_id {start_id} not found",
                )
            )
            continue
        if end_id not in known_intersection_ids:
            report.issues.append(
                ValidationIssue(
                    "error",
                    "segment_references_unknown_end",
                    f"RoadSegment {segment_id} end_intersection_id {end_id} not found",
                )
            )
            continue

        forward_exists = graph.has_edge(start_id, end_id, key=segment_id)
        if not forward_exists:
            report.issues.append(
                ValidationIssue(
                    "error",
                    "missing_forward_edge",
                    f"RoadSegment {segment_id} has no forward ({start_id} -> {end_id}) edge",
                )
            )

        if start_id == end_id:
            # A self-loop's "forward" and "reverse" queries are the exact
            # same (u, v, key) triple - there is only ever one edge, and
            # asking whether a distinct reverse direction exists is
            # meaningless. The forward_exists check above already covers
            # everything a self-loop needs.
            continue

        reverse_exists = graph.has_edge(end_id, start_id, key=segment_id)
        if is_oneway and reverse_exists:
            report.issues.append(
                ValidationIssue(
                    "error",
                    "unexpected_reverse_edge",
                    f"RoadSegment {segment_id} is one-way but a reverse "
                    f"({end_id} -> {start_id}) edge exists",
                )
            )
        elif not is_oneway and not reverse_exists:
            report.issues.append(
                ValidationIssue(
                    "error",
                    "missing_reverse_edge",
                    f"RoadSegment {segment_id} is bidirectional but no reverse "
                    f"({end_id} -> {start_id}) edge exists",
                )
            )

    return report
