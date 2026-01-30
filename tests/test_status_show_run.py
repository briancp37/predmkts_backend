"""Tests for the status show-run command."""

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
    cursor: str | None = "abc123",
) -> Manifest:
    return Manifest(
        run_id=run_id,
        platform=platform,
        entity=entity,
        dt=dt,
        generated_at=generated_at,
        files=[
            FileReference(bucket="test-bucket", key=f"bronze/{platform}/{entity}/dt={dt}/run_id={run_id}/part-000.jsonl.gz"),
            FileReference(bucket="test-bucket", key=f"bronze/{platform}/{entity}/dt={dt}/run_id={run_id}/part-001.jsonl.gz"),
        ],
        row_count=row_count,
        source=Source(api_base_url="https://clob.polymarket.com", pagination="cursor", cursor=cursor),
    )


class FakeS3Client:
    """Fake S3Client for testing show-run command."""

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


class TestShowRunCommand:
    def test_show_run_found(self) -> None:
        """Displays full manifest details when run is found."""
        m = _make_manifest(run_id="run-001", cursor="final-cursor-xyz")
        keys_by_prefix = {
            "bronze/polymarket/trades/": [
                "bronze/polymarket/trades/dt=2024-01-01/run_id=run-001/manifest.json",
            ],
        }
        manifests = {
            "bronze/polymarket/trades/dt=2024-01-01/run_id=run-001/manifest.json": m,
        }
        fake = FakeS3Client(keys_by_prefix, manifests)

        with patch("prediction_data.storage.s3.S3Client", return_value=fake):
            result = runner.invoke(app, [
                "status", "show-run", "run-001",
                "--platform", "polymarket",
                "--entity", "trades",
                "--bucket", "test-bucket",
            ])

        assert result.exit_code == 0
        assert "run-001" in result.output
        assert "polymarket" in result.output
        assert "trades" in result.output
        assert "2024-01-01" in result.output
        assert "100" in result.output
        assert "https://clob.polymarket.com" in result.output
        assert "cursor" in result.output
        assert "final-cursor-xyz" in result.output
        assert "part-000.jsonl.gz" in result.output
        assert "part-001.jsonl.gz" in result.output
        assert "Files (2)" in result.output

    def test_show_run_not_found(self) -> None:
        """Exits with error when run not found."""
        fake = FakeS3Client({}, {})

        with patch("prediction_data.storage.s3.S3Client", return_value=fake):
            result = runner.invoke(app, [
                "status", "show-run", "nonexistent-run",
                "--platform", "polymarket",
                "--entity", "trades",
                "--bucket", "test-bucket",
            ])

        assert result.exit_code == 1
        assert "No run found" in result.output
        assert "nonexistent-run" in result.output

    def test_show_run_partial_prefix_match(self) -> None:
        """Supports partial prefix matching for run_id."""
        m = _make_manifest(run_id="abcdef-1234-5678-ghij")
        keys_by_prefix = {
            "bronze/polymarket/trades/": [
                "bronze/polymarket/trades/dt=2024-01-01/run_id=abcdef-1234-5678-ghij/manifest.json",
            ],
        }
        manifests = {
            "bronze/polymarket/trades/dt=2024-01-01/run_id=abcdef-1234-5678-ghij/manifest.json": m,
        }
        fake = FakeS3Client(keys_by_prefix, manifests)

        with patch("prediction_data.storage.s3.S3Client", return_value=fake):
            result = runner.invoke(app, [
                "status", "show-run", "abcdef",
                "--platform", "polymarket",
                "--entity", "trades",
                "--bucket", "test-bucket",
            ])

        assert result.exit_code == 0
        assert "abcdef-1234-5678-ghij" in result.output

    def test_show_run_no_bucket(self) -> None:
        """Missing bucket exits with error."""
        with patch.dict("os.environ", {}, clear=True):
            result = runner.invoke(app, [
                "status", "show-run", "run-001",
            ])
        assert result.exit_code == 1

    def test_show_run_no_cursor(self) -> None:
        """Displays (none) when cursor is null."""
        m = _make_manifest(run_id="run-nocursor", cursor=None)
        keys_by_prefix = {
            "bronze/polymarket/trades/": [
                "bronze/polymarket/trades/dt=2024-01-01/run_id=run-nocursor/manifest.json",
            ],
        }
        manifests = {
            "bronze/polymarket/trades/dt=2024-01-01/run_id=run-nocursor/manifest.json": m,
        }
        fake = FakeS3Client(keys_by_prefix, manifests)

        with patch("prediction_data.storage.s3.S3Client", return_value=fake):
            result = runner.invoke(app, [
                "status", "show-run", "run-nocursor",
                "--platform", "polymarket",
                "--entity", "trades",
                "--bucket", "test-bucket",
            ])

        assert result.exit_code == 0
        assert "(none)" in result.output

    def test_show_run_hint_message(self) -> None:
        """Shows helpful hint when run not found."""
        fake = FakeS3Client({}, {})

        with patch("prediction_data.storage.s3.S3Client", return_value=fake):
            result = runner.invoke(app, [
                "status", "show-run", "missing",
                "--platform", "polymarket",
                "--entity", "trades",
                "--bucket", "test-bucket",
            ])

        assert result.exit_code == 1
        assert "prediction-data status runs" in result.output
