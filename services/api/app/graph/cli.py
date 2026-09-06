"""Canonical road graph CLI.

Usage (from services/api):
    uv run python -m app.graph.cli build
    uv run python -m app.graph.cli validate

Reads only from canonical PostGIS (via the same session-factory pattern
as app.db.seed and app.ingestion.cli) - never touches OSM or any external
source. No HTTP endpoint is exposed for this; doc TASK-203 §19 prefers a
CLI, matching TASK-202's precedent.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys

from app.core.logging import configure_logging
from app.db.session import dispose_engine, get_session_factory
from app.graph.builder import build_road_graph, load_known_intersection_ids
from app.graph.validation import validate_graph

logger = logging.getLogger(__name__)


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="aura-graph", description="Build/validate AURA's canonical road graph."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("build", help="build the graph and print statistics")
    subparsers.add_parser("validate", help="build the graph and run validation checks")
    return parser


async def _run(args: argparse.Namespace) -> int:
    session_factory = get_session_factory()
    async with session_factory() as session:
        result = await build_road_graph(session)

        if args.command == "build":
            print(json.dumps(result.stats.as_dict(), indent=2))
            return 0

        # validate
        segment_rows = [
            (data["road_segment_id"], u, v, data["is_oneway"])
            for u, v, data in result.graph.edges(data=True)
            if not data["reversed"]
        ]
        known_intersection_ids = await load_known_intersection_ids(session)
        report = validate_graph(
            result.graph,
            known_intersection_ids=known_intersection_ids,
            segment_rows=segment_rows,
        )
        output = {"stats": result.stats.as_dict(), "validation": report.as_dict()}
        print(json.dumps(output, indent=2))
        return 0 if report.is_valid else 1


async def _main_async(args: argparse.Namespace) -> int:
    try:
        return await _run(args)
    finally:
        # Same event loop as _run() - see app.ingestion.cli for why two
        # separate asyncio.run() calls break the pooled connection.
        await dispose_engine()


def main() -> int:
    configure_logging()
    args = _build_arg_parser().parse_args()
    return asyncio.run(_main_async(args))


if __name__ == "__main__":
    sys.exit(main())
