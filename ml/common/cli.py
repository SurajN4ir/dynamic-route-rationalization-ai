"""Feature dataset CLI - see docs/architecture/TASK205_DESIGN.md §21.

Usage (from the repo root, with `services/api` on PYTHONPATH - see
pyproject.toml's `[tool.pytest.ini_options] pythonpath`):
    python -m ml.common.cli generate --start ... --end ... [--bucket-s 300]
        [--horizons 300,900] [--out data/features/road_segment_traffic_v1]
    python -m ml.common.cli stats --dataset-dir data/features/road_segment_traffic_v1
    python -m ml.common.cli validate --dataset-dir data/features/road_segment_traffic_v1

Not a public API - TASK-205 explicitly does not serve predictions.
Follows the same single-`asyncio.run()`/`dispose_engine()` pattern
`app.ingestion.cli`/`app.graph.cli` already established.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
from datetime import datetime
from pathlib import Path

from app.core.logging import configure_logging
from app.db.session import dispose_engine, get_session_factory
from ml.common.contract import ROAD_SEGMENT_FEATURE_CONTRACT
from ml.common.dataset import DatasetGenerationConfig, generate_road_segment_dataset, write_dataset
from ml.common.stats import compute_dataset_stats
from ml.common.targets import TARGET_HORIZONS_S

logger = logging.getLogger(__name__)


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="aura-features", description="Generate/inspect AURA's prediction feature datasets."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    generate = subparsers.add_parser("generate", help="generate a road_segment x timestamp dataset")
    generate.add_argument("--start", required=True, help="ISO 8601 UTC timestamp, inclusive")
    generate.add_argument("--end", required=True, help="ISO 8601 UTC timestamp, inclusive")
    generate.add_argument("--bucket-s", type=int, default=300)
    generate.add_argument(
        "--horizons",
        default=",".join(str(h) for h in TARGET_HORIZONS_S),
        help="comma-separated seconds",
    )
    generate.add_argument("--out", default="data/features/road_segment_traffic_v1")

    stats = subparsers.add_parser("stats", help="report descriptive statistics for a dataset")
    stats.add_argument("--dataset-dir", required=True)

    validate = subparsers.add_parser("validate", help="sanity-check a generated dataset")
    validate.add_argument("--dataset-dir", required=True)

    return parser


def _parse_iso(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        raise ValueError(f"{value!r} is not timezone-aware - pass an explicit UTC offset")
    return parsed


async def _run_generate(args: argparse.Namespace) -> int:
    config = DatasetGenerationConfig(
        start=_parse_iso(args.start),
        end=_parse_iso(args.end),
        bucket_s=args.bucket_s,
        horizons_s=tuple(int(h) for h in args.horizons.split(",")),
    )
    session_factory = get_session_factory()
    async with session_factory() as session:
        rows = await generate_road_segment_dataset(session, config)
    csv_path, manifest_path = write_dataset(rows, config, Path(args.out))
    print(
        json.dumps(
            {"csv": str(csv_path), "manifest": str(manifest_path), "rows": len(rows)}, indent=2
        )
    )
    return 0


def _run_stats(args: argparse.Namespace) -> int:
    dataset_dir = Path(args.dataset_dir)
    manifest = json.loads((dataset_dir / "manifest.json").read_text(encoding="utf-8"))
    result = compute_dataset_stats(dataset_dir / "dataset.csv", manifest)
    print(
        json.dumps(
            {
                "row_count": result.row_count,
                "entity_count": result.entity_count,
                "time_range": result.time_range,
                "feature_set_version": result.feature_set_version,
                "target_availability": result.target_availability,
                "columns": [
                    {
                        "name": c.name,
                        "non_missing_count": c.non_missing_count,
                        "missing_count": c.missing_count,
                        "min": c.min_value,
                        "max": c.max_value,
                        "mean": c.mean_value,
                    }
                    for c in result.columns
                ],
            },
            indent=2,
            default=str,
        )
    )
    return 0


def _run_validate(args: argparse.Namespace) -> int:
    dataset_dir = Path(args.dataset_dir)
    manifest_path = dataset_dir / "manifest.json"
    csv_path = dataset_dir / "dataset.csv"
    if not manifest_path.exists() or not csv_path.exists():
        print(json.dumps({"is_valid": False, "errors": ["missing dataset.csv or manifest.json"]}))
        return 1

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    errors: list[str] = []

    expected_columns = [f.name for f in ROAD_SEGMENT_FEATURE_CONTRACT] + [
        f"target_traffic_speed_mps_h{h}" for h in manifest.get("horizons_s", [])
    ]
    if manifest.get("columns") != expected_columns:
        errors.append("manifest columns do not match the current feature contract")

    with csv_path.open(newline="", encoding="utf-8") as f:
        actual_row_count = sum(1 for _ in f) - 1  # minus header
    if actual_row_count != manifest.get("row_count"):
        errors.append(
            f"manifest row_count ({manifest.get('row_count')}) does not match "
            f"actual CSV row count ({actual_row_count})"
        )

    print(json.dumps({"is_valid": not errors, "errors": errors}, indent=2))
    return 0 if not errors else 1


async def _main_async(args: argparse.Namespace) -> int:
    try:
        return await _run_generate(args)
    finally:
        await dispose_engine()


def main() -> int:
    configure_logging()
    args = _build_arg_parser().parse_args()

    if args.command == "stats":
        return _run_stats(args)
    if args.command == "validate":
        return _run_validate(args)
    return asyncio.run(_main_async(args))


if __name__ == "__main__":
    sys.exit(main())
