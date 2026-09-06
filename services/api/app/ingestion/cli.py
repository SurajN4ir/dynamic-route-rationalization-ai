"""OSM road-network ingestion CLI.

Usage (from services/api):
    uv run python -m app.ingestion.cli <path-to-osm-xml> [--dry-run] [--source osm]

Deliberately a CLI, not an HTTP endpoint - doc TASK-202 §14: ingestion is
an operator-run/scripted concern, not something the public API surface
needs to expose. Follows the same session-factory / dispose_engine
pattern as app.db.seed (TASK-201's precedent for a standalone script).
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
from pathlib import Path

from app.core.logging import configure_logging
from app.db.session import dispose_engine, get_session_factory
from app.ingestion.osm.errors import OSMParseError
from app.ingestion.osm.pipeline import ingest_osm_file

logger = logging.getLogger(__name__)


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="ingest-osm", description="Ingest an OSM XML road-network extract into AURA."
    )
    parser.add_argument("input", type=Path, help="path to a .osm XML extract")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="report what would change without writing to the database",
    )
    parser.add_argument(
        "--source",
        default="osm",
        help="source label recorded on every ingested row (default: osm)",
    )
    return parser


async def _run(args: argparse.Namespace) -> int:
    if not args.input.exists():
        logger.error("input file not found", extra={"input_path": str(args.input)})
        return 2

    session_factory = get_session_factory()
    async with session_factory() as session:
        try:
            stats = await ingest_osm_file(
                session, args.input, source=args.source, dry_run=args.dry_run
            )
        except OSMParseError as exc:
            await session.rollback()
            logger.error("osm parse error", extra={"error": str(exc)})
            return 1
        except Exception:
            await session.rollback()
            logger.exception("ingestion failed - rolling back, no partial state persisted")
            return 1

        if args.dry_run:
            await session.rollback()  # defensive: dry-run must never leave writes pending
        else:
            await session.commit()

    print(json.dumps(stats.as_dict(), indent=2))
    return 0


async def _main_async(args: argparse.Namespace) -> int:
    try:
        return await _run(args)
    finally:
        # Must run in the *same* event loop as _run() - the engine's
        # pooled connections are bound to whichever loop opened them, and
        # a second, separate asyncio.run() call gets a brand new loop
        # (this bit us for real in Docker testing: "attached to a
        # different loop" / "Event loop is closed" tearing down the pool).
        await dispose_engine()


def main() -> int:
    configure_logging()
    args = _build_arg_parser().parse_args()
    return asyncio.run(_main_async(args))


if __name__ == "__main__":
    sys.exit(main())
