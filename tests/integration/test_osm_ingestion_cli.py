"""CLI tests - doc TASK-202 §15's "dry-run does not mutate database",
"actual ingestion persists expected records", "useful summary statistics
are emitted".

`app.ingestion.cli.get_session_factory` is monkeypatched to the test's
own rolled-back-transaction factory so the CLI's real commit()/rollback()
calls run for real, but never escape the test (see
tests/integration/conftest.py's db_session_factory fixture). `main()`
itself is not called (it disposes the *global* engine, which other tests
still need) - `_run()` is the actual orchestration logic under test.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

import app.ingestion.cli as cli_module
from app.ingestion.cli import _build_arg_parser, _run
from app.models.road_network import RoadSegment

FIXTURE = Path(__file__).parent.parent / "fixtures" / "osm" / "sample_extract.osm"


@pytest.fixture(autouse=True)
def _patch_session_factory(
    monkeypatch: pytest.MonkeyPatch, db_session_factory: async_sessionmaker[AsyncSession]
) -> None:
    monkeypatch.setattr(cli_module, "get_session_factory", lambda: db_session_factory)


async def test_dry_run_flag_parses() -> None:
    args = _build_arg_parser().parse_args([str(FIXTURE), "--dry-run"])
    assert args.dry_run is True
    assert args.source == "osm"


async def test_cli_dry_run_does_not_persist(
    db_session: AsyncSession, capsys: pytest.CaptureFixture[str]
) -> None:
    args = _build_arg_parser().parse_args([str(FIXTURE), "--dry-run"])

    exit_code = await _run(args)

    assert exit_code == 0
    count = await db_session.scalar(select(func.count()).select_from(RoadSegment))
    assert count == 0

    printed = json.loads(capsys.readouterr().out)
    assert printed["dry_run"] is True
    assert printed["segments_created"] == 4


async def test_cli_real_run_persists_expected_records(
    db_session: AsyncSession, capsys: pytest.CaptureFixture[str]
) -> None:
    args = _build_arg_parser().parse_args([str(FIXTURE)])

    exit_code = await _run(args)

    assert exit_code == 0
    count = await db_session.scalar(select(func.count()).select_from(RoadSegment))
    assert count == 4

    printed = json.loads(capsys.readouterr().out)
    assert printed["dry_run"] is False
    assert printed["segments_created"] == 4
    assert printed["roads_created"] == 3
    assert printed["intersections_created"] == 6


async def test_cli_reports_rejection_breakdown(capsys: pytest.CaptureFixture[str]) -> None:
    args = _build_arg_parser().parse_args([str(FIXTURE), "--dry-run"])

    await _run(args)

    printed = json.loads(capsys.readouterr().out)
    assert printed["rejected_features"] == 3
    assert printed["rejections_by_reason"]["unsupported_highway_value"] == 1
    assert printed["rejections_by_reason"]["too_few_nodes"] == 1
    assert printed["rejections_by_reason"]["unresolved_node_reference"] == 1


async def test_cli_missing_input_file_returns_nonzero(tmp_path: Path) -> None:
    args = _build_arg_parser().parse_args([str(tmp_path / "does-not-exist.osm")])

    exit_code = await _run(args)

    assert exit_code == 2


async def test_cli_malformed_input_returns_nonzero(tmp_path: Path) -> None:
    bad_file = tmp_path / "bad.osm"
    bad_file.write_text("<osm><node id='1' lat='0' lon='0'></osm>")

    args = _build_arg_parser().parse_args([str(bad_file)])
    exit_code = await _run(args)

    assert exit_code == 1


async def test_cli_custom_source_label_is_recorded(db_session: AsyncSession) -> None:
    args = _build_arg_parser().parse_args([str(FIXTURE), "--source", "osm-import-2026"])

    await _run(args)

    segment = await db_session.scalar(select(RoadSegment).where(RoadSegment.osm_way_id == 200))
    assert segment is not None
    assert segment.source == "osm"  # the *row* source is always "osm" (doc 04's source enum);
    # --source is the run-level provenance label reported in stats, see
    # docs/architecture/TASK202_DESIGN.md §6 known limitations.
