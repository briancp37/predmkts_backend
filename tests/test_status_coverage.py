"""Tests for the status coverage command."""

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
    """Fake S3Client for testing coverage command."""

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


class TestCoverageCommand:
    def test_full_coverage(self) -> None:
        """All dates in range have data."""
        manifest1 = _make_manifest(dt="2024-01-01", row_count=50, generated_at="2024-01-01T12:00:00+00:00")
        manifest2 = _make_manifest(dt="2024-01-02", row_count=75, generated_at="2024-01-02T12:00:00+00:00")

        keys_by_prefix = {
            "bronze/polymarket/trades/dt=2024-01-01/": [
                "bronze/polymarket/trades/dt=2024-01-01/run_id=run-001/manifest.json",
                "bronze/polymarket/trades/dt=2024-01-01/run_id=run-001/part-000.jsonl.gz",
            ],
            "bronze/polymarket/trades/dt=2024-01-02/": [
                "bronze/polymarket/trades/dt=2024-01-02/run_id=run-001/manifest.json",
                "bronze/polymarket/trades/dt=2024-01-02/run_id=run-001/part-000.jsonl.gz",
            ],
        }
        manifests = {
            "bronze/polymarket/trades/dt=2024-01-01/run_id=run-001/manifest.json": manifest1,
            "bronze/polymarket/trades/dt=2024-01-02/run_id=run-001/manifest.json": manifest2,
        }
        fake = FakeS3Client(keys_by_prefix, manifests)

        with patch("prediction_data.storage.s3.S3Client", return_value=fake):
            result = runner.invoke(app, [
                "status", "coverage",
                "--start-date", "2024-01-01",
                "--end-date", "2024-01-02",
                "--platform", "polymarket",
                "--entity", "trades",
                "--bucket", "test-bucket",
            ])

        assert result.exit_code == 0
        assert "2024-01-01" in result.output
        assert "2024-01-02" in result.output
        assert "OK" in result.output
        assert "MISSING" not in result.output
        assert "2 with data" in result.output
        assert "0 missing" in result.output
        assert "125 total rows" in result.output

    def test_partial_gaps(self) -> None:
        """Some dates have data, some are missing."""
        manifest = _make_manifest(dt="2024-01-01", row_count=200)

        keys_by_prefix = {
            "bronze/polymarket/trades/dt=2024-01-01/": [
                "bronze/polymarket/trades/dt=2024-01-01/run_id=run-001/manifest.json",
            ],
            "bronze/polymarket/trades/dt=2024-01-02/": [],
            "bronze/polymarket/trades/dt=2024-01-03/": [],
        }
        manifests = {
            "bronze/polymarket/trades/dt=2024-01-01/run_id=run-001/manifest.json": manifest,
        }
        fake = FakeS3Client(keys_by_prefix, manifests)

        with patch("prediction_data.storage.s3.S3Client", return_value=fake):
            result = runner.invoke(app, [
                "status", "coverage",
                "--start-date", "2024-01-01",
                "--end-date", "2024-01-03",
                "--platform", "polymarket",
                "--entity", "trades",
                "--bucket", "test-bucket",
            ])

        assert result.exit_code == 0
        assert "OK" in result.output
        assert "MISSING" in result.output
        assert "1 with data" in result.output
        assert "2 missing" in result.output
        assert "200 total rows" in result.output

    def test_empty_range(self) -> None:
        """No data for any date in range."""
        fake = FakeS3Client({}, {})

        with patch("prediction_data.storage.s3.S3Client", return_value=fake):
            result = runner.invoke(app, [
                "status", "coverage",
                "--start-date", "2024-06-01",
                "--end-date", "2024-06-02",
                "--platform", "kalshi",
                "--entity", "markets",
                "--bucket", "test-bucket",
            ])

        assert result.exit_code == 0
        assert "0 with data" in result.output
        assert "2 missing" in result.output
        assert "0 total rows" in result.output

    def test_multiple_runs_per_date(self) -> None:
        """A date with multiple ingestion runs sums row counts."""
        m1 = _make_manifest(dt="2024-01-01", run_id="run-001", row_count=100, generated_at="2024-01-01T10:00:00+00:00")
        m2 = _make_manifest(dt="2024-01-01", run_id="run-002", row_count=50, generated_at="2024-01-01T14:00:00+00:00")

        keys_by_prefix = {
            "bronze/polymarket/trades/dt=2024-01-01/": [
                "bronze/polymarket/trades/dt=2024-01-01/run_id=run-001/manifest.json",
                "bronze/polymarket/trades/dt=2024-01-01/run_id=run-002/manifest.json",
                "bronze/polymarket/trades/dt=2024-01-01/run_id=run-001/part-000.jsonl.gz",
                "bronze/polymarket/trades/dt=2024-01-01/run_id=run-002/part-000.jsonl.gz",
            ],
        }
        manifests = {
            "bronze/polymarket/trades/dt=2024-01-01/run_id=run-001/manifest.json": m1,
            "bronze/polymarket/trades/dt=2024-01-01/run_id=run-002/manifest.json": m2,
        }
        fake = FakeS3Client(keys_by_prefix, manifests)

        with patch("prediction_data.storage.s3.S3Client", return_value=fake):
            result = runner.invoke(app, [
                "status", "coverage",
                "--start-date", "2024-01-01",
                "--end-date", "2024-01-01",
                "--platform", "polymarket",
                "--entity", "trades",
                "--bucket", "test-bucket",
            ])

        assert result.exit_code == 0
        # 2 runs
        assert "2" in result.output
        # 150 total rows
        assert "150 total rows" in result.output

    def test_invalid_date_format(self) -> None:
        """Bad date format exits with error."""
        result = runner.invoke(app, [
            "status", "coverage",
            "--start-date", "not-a-date",
            "--end-date", "2024-01-01",
            "--bucket", "test-bucket",
        ])
        assert result.exit_code == 1
        assert "Invalid date" in result.output

    def test_start_after_end(self) -> None:
        """Start date after end date exits with error."""
        result = runner.invoke(app, [
            "status", "coverage",
            "--start-date", "2024-01-05",
            "--end-date", "2024-01-01",
            "--bucket", "test-bucket",
        ])
        assert result.exit_code == 1
        assert "start-date must be" in result.output

    def test_no_bucket(self) -> None:
        """Missing bucket exits with error."""
        with patch.dict("os.environ", {}, clear=True):
            result = runner.invoke(app, [
                "status", "coverage",
                "--start-date", "2024-01-01",
                "--end-date", "2024-01-01",
            ])
        assert result.exit_code == 1

    def test_default_all_platforms_entities(self) -> None:
        """Without --platform/--entity, iterates all combos."""
        fake = FakeS3Client({}, {})

        with patch("prediction_data.storage.s3.S3Client", return_value=fake):
            result = runner.invoke(app, [
                "status", "coverage",
                "--start-date", "2024-01-01",
                "--end-date", "2024-01-01",
                "--bucket", "test-bucket",
            ])

        assert result.exit_code == 0
        # 2 platforms * 4 entities * 1 date = 8 date combos
        assert "8 date(s)" in result.output
        assert "8 missing" in result.output
