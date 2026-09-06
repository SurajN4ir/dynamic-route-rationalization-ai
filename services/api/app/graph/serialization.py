"""Deterministic graph -> plain-dict serialization, for tests/debugging
only (doc TASK-203 §18) - never written to disk as a committed artifact,
and not a caching mechanism. Sorting node/edge keys makes the output
byte-for-byte comparable across two builds of the same canonical data,
which is exactly what the "rebuild produces an identical result" test
needs without relying on dict/graph object identity.
"""

from __future__ import annotations

import uuid
from typing import Any

import networkx as nx


def graph_to_dict(graph: nx.MultiDiGraph) -> dict[str, Any]:
    nodes = [
        {"id": str(node_id), **{k: _jsonable(v) for k, v in sorted(attrs.items())}}
        for node_id, attrs in sorted(graph.nodes(data=True), key=lambda item: str(item[0]))
    ]
    edges = [
        {
            "u": str(u),
            "v": str(v),
            "key": str(key),
            **{k: _jsonable(val) for k, val in sorted(attrs.items())},
        }
        for u, v, key, attrs in sorted(
            graph.edges(keys=True, data=True),
            key=lambda item: (str(item[0]), str(item[1]), str(item[2])),
        )
    ]
    return {"nodes": nodes, "edges": edges}


def _jsonable(value: object) -> object:
    if isinstance(value, uuid.UUID):
        return str(value)
    return value
