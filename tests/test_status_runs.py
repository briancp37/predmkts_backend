"""Tests for the status runs command."""

from __future__ import annotations

from typing import Any
from unittest.mock import patch

from typer.testing import CliRunner

from prediction_data.cli.main import app
from prediction_data.storage.manifest import FileReference, Manifest, Source

runner = CliRunner()


def _make_manifest(
    *,
    platform: str = "polymarket",
    entity: str = "trades",
    dt: str = "2024-01-01",
    run_id: str = "run-001",
    row_count: int = 100,
    generated_at: str = "2024-01-01T12:00:00+00:00",
) -> Manifest:
    return Manifest(
        run_id=run_id,
        platform=platform,
        entity=entity,
        dt=dt,
        generated_at=generated_at,
        files=[FileReference(bucket="test-bucket", key=f"bronze/{platform}/{entity}/dt={dt}/run_id={run_id}/part-000.jsonl.gz")],
        row_count=row_count,
        source=Source(api_base_url="https://example.com", pagination="cursor", cursor=None),
    )


class FakeS3Client:
    """Fake S3Client for testing runs command."""

    def __init__(self, keys_by_prefix: dict[str, list[str]], manifests: dict[str, Manifest]) -> None:
        self._keys_by_prefix = keys_by_prefix
        self._manifests = manifests

    async def __aenter__(self) -> FakeS3Client:
        return self

    async def __aexit__(self, *args: Any) -> None:
        pass

    async def list_keys(self, prefix: str) -> list[str]:
        return self._keys_by_prefix.get(prefix, [])

    async def download_manifest(self, key: str) -> Manifest:
        return self._manifests[key]


class TestRunsCommand:
    def test_list_recent_runs(self) -> None:
        """Lists runs sorted by generated_at descending."""
        m1 = _make_manifest(run_id="run-001", dt="2024-01-01", row_count=100, generated_at="2024-01-01T10:00:00+00:00")
        m2 = _make_manifest(run_id="run-002", dt="2024-01-01", row_count=200, generated_at="2024-01-01T14:00:00+00:00")
        m3 = _make_manifest(run_id="run-003", dt="2024-01-02", row_count=150, generated_at="2024-01-02T09:00:00+00:00")

        keys_by_prefix = {
            "bronze/polymarket/trades/": [
                "bronze/polymarket/trades/dt=2024-01-01/run_id=run-001/manifest.json",
                "bronze/polymarket/trades/dt=2024-01-01/run_id=run-002/manifest.json",
                "bronze/polymarket/trades/dt=2024-01-02/run_id=run-003/manifest.json",
            ],
        }
        manifests = {
            "bronze/polymarket/trades/dt=2024-01-01/run_id=run-001/manifest.json": m1,
            "bronze/polymarket/trades/dt=2024-01-01/run_id=run-002/manifest.json": m2,
            "bronze/polymarket/trades/dt=2024-01-02/run_id=run-003/manifest.json": m3,
        }
        fake = FakeS3Client(keys_by_prefix, manifests)

        with patch("prediction_data.storage.s3.S3Client", return_value=fake):
            result = runner.invoke(app, [
                "status", "runs",
                "--platform", "polymarket",
                "--entity", "trades",
                "--bucket", "test-bucket",
            ])

        assert result.exit_code == 0
        # Most recent first
        lines = result.output.strip().split("\n")
        data_lines = [line for line in lines if "run-" in line]
        assert "run-003" in data_lines[0]
        assert "run-002" in data_lines[1]
        assert "run-001" in data_lines[2]

    def test_last_limit(self) -> None:
        """--last limits the number of runs returned."""
        m1 = _make_manifest(run_id="run-001", generated_at="2024-01-01T10:00:00+00:00")
        m2 = _make_manifest(run_id="run-002", generated_at="2024-01-01T14:00:00+00:00")
        m3 = _make_manifest(run_id="run-003", dt="2024-01-02", generated_at="2024-01-02T09:00:00+00:00")

        keys_by_prefix = {
            "bronze/polymarket/trades/": [
                "bronze/polymarket/trades/dt=2024-01-01/run_id=run-001/manifest.json",
                "bronze/polymarket/trades/dt=2024-01-01/run_id=run-002/manifest.json",
                "bronze/polymarket/trades/dt=2024-01-02/run_id=run-003/manifest.json",
            ],
        }
        manifests = {
            "bronze/polymarket/trades/dt=2024-01-01/run_id=run-001/manifest.json": m1,
            "bronze/polymarket/trades/dt=2024-01-01/run_id=run-002/manifest.json": m2,
            "bronze/polymarket/trades/dt=2024-01-02/run_id=run-003/manifest.json": m3,
        }
        fake = FakeS3Client(keys_by_prefix, manifests)

        with patch("prediction_data.storage.s3.S3Client", return_value=fake):
            result = runner.invoke(app, [
                "status", "runs",
                "--platform", "polymarket",
                "--entity", "trades",
                "--bucket", "test-bucket",
                "--last", "2",
            ])

        assert result.exit_code == 0
        assert "run-003" in result.output
        assert "run-002" in result.output
        assert "run-001" not in result.output

    def test_dt_filter_shows_all_runs(self) -> None:
        """--dt shows all runs for that date, ignoring --last."""
        m1 = _make_manifest(run_id="run-001", dt="2024-01-01", generated_at="2024-01-01T10:00:00+00:00")
        m2 = _make_manifest(run_id="run-002", dt="2024-01-01", generated_at="2024-01-01T14:00:00+00:00")
        m3 = _make_manifest(run_id="run-003", dt="2024-01-01", generated_at="2024-01-01T18:00:00+00:00")

        keys_by_prefix = {
            "bronze/polymarket/trades/dt=2024-01-01/": [
                "bronze/polymarket/trades/dt=2024-01-01/run_id=run-001/manifest.json",
                "bronze/polymarket/trades/dt=2024-01-01/run_id=run-002/manifest.json",
                "bronze/polymarket/trades/dt=2024-01-01/run_id=run-003/manifest.json",
            ],
        }
        manifests = {
            "bronze/polymarket/trades/dt=2024-01-01/run_id=run-001/manifest.json": m1,
            "bronze/polymarket/trades/dt=2024-01-01/run_id=run-002/manifest.json": m2,
            "bronze/polymarket/trades/dt=2024-01-01/run_id=run-003/manifest.json": m3,
        }
        fake = FakeS3Client(keys_by_prefix, manifests)

        with patch("prediction_data.storage.s3.S3Client", return_value=fake):
            result = runner.invoke(app, [
                "status", "runs",
                "--platform", "polymarket",
                "--entity", "trades",
                "--bucket", "test-bucket",
                "--dt", "2024-01-01",
                "--last", "1",  # Should be ignored with --dt
            ])

        assert result.exit_code == 0
        assert "run-001" in result.output
        assert "run-002" in result.output
        assert "run-003" in result.output

    def test_no_runs_found(self) -> None:
        """Empty result when no runs exist."""
        fake = FakeS3Client({}, {})

        with patch("prediction_data.storage.s3.S3Client", return_value=fake):
            result = runner.invoke(app, [
                "status", "runs",
                "--platform", "polymarket",
                "--entity", "trades",
                "--bucket", "test-bucket",
            ])

        assert result.exit_code == 0
        assert "no data" in result.output

    def test_invalid_dt_format(self) -> None:
        """Bad --dt format exits with error."""
        result = runner.invoke(app, [
            "status", "runs",
            "--dt", "not-a-date",
            "--bucket", "test-bucket",
        ])
        assert result.exit_code == 1
        assert "Invalid date" in result.output

    def test_no_bucket(self) -> None:
        """Missing bucket exits with error."""
        with patch.dict("os.environ", {}, clear=True):
            result = runner.invoke(app, [
                "status", "runs",
            ])
        assert result.exit_code == 1

    def test_sorting_across_platforms(self) -> None:
        """Runs from different platforms are sorted together by generated_at."""
        m1 = _make_manifest(platform="polymarket", run_id="pm-001", generated_at="2024-01-01T10:00:00+00:00")
        m2 = _make_manifest(platform="kalshi", entity="trades", run_id="ka-001", generated_at="2024-01-01T15:00:00+00:00")

        keys_by_prefix = {
            "bronze/polymarket/trades/": [
                "bronze/polymarket/trades/dt=2024-01-01/run_id=pm-001/manifest.json",
            ],
            "bronze/kalshi/trades/": [
                "bronze/kalshi/trades/dt=2024-01-01/run_id=ka-001/manifest.json",
            ],
        }
        manifests = {
            "bronze/polymarket/trades/dt=2024-01-01/run_id=pm-001/manifest.json": m1,
            "bronze/kalshi/trades/dt=2024-01-01/run_id=ka-001/manifest.json": m2,
        }
        fake = FakeS3Client(keys_by_prefix, manifests)

        with patch("prediction_data.storage.s3.S3Client", return_value=fake):
            result = runner.invoke(app, [
                "status", "runs",
                "--entity", "trades",
                "--bucket", "test-bucket",
            ])

        assert result.exit_code == 0
        lines = [line for line in result.output.strip().split("\n") if "ka-001" in line or "pm-001" in line]
        # kalshi run is more recent, should be first
        assert "ka-001" in lines[0]
        assert "pm-001" in lines[1]
