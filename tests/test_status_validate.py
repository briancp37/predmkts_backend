"""Tests for the status validate command."""

from __future__ import annotations

from typing import Any
from unittest.mock import patch

from pydantic import ValidationError
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
    part_key: str | None = None,
) -> Manifest:
    key = part_key or f"bronze/{platform}/{entity}/dt={dt}/run_id={run_id}/part-000.jsonl.gz"
    return Manifest(
        run_id=run_id,
        platform=platform,
        entity=entity,
        dt=dt,
        generated_at=generated_at,
        files=[FileReference(bucket="test-bucket", key=key)],
        row_count=row_count,
        source=Source(api_base_url="https://example.com", pagination="cursor", cursor=None),
    )


class FakeS3Client:
    """Fake S3Client for testing validate command."""

    def __init__(
        self,
        keys_by_prefix: dict[str, list[str]],
        manifests: dict[str, Manifest],
        bad_manifests: set[str] | None = None,
    ) -> None:
        self._keys_by_prefix = keys_by_prefix
        self._manifests = manifests
        self._bad_manifests = bad_manifests or set()

    async def __aenter__(self) -> FakeS3Client:
        return self

    async def __aexit__(self, *args: Any) -> None:
        pass

    async def list_keys(self, prefix: str) -> list[str]:
        return self._keys_by_prefix.get(prefix, [])

    async def download_manifest(self, key: str) -> Manifest:
        if key in self._bad_manifests:
            raise ValidationError.from_exception_data(
                title="Manifest",
                line_errors=[],
                input_type="json",
            )
        return self._manifests[key]


def _invoke(fake: FakeS3Client, **extra_args: str) -> Any:
    args = [
        "status", "validate",
        "--start-date", extra_args.get("start_date", "2024-01-01"),
        "--end-date", extra_args.get("end_date", "2024-01-01"),
        "--platform", extra_args.get("platform", "polymarket"),
        "--entity", extra_args.get("entity", "trades"),
        "--bucket", "test-bucket",
    ]
    with patch("prediction_data.storage.s3.S3Client", return_value=fake):
        return runner.invoke(app, args)


class TestValidateCommand:
    def test_valid_data(self) -> None:
        """All runs have valid manifests and all parts exist."""
        manifest = _make_manifest()
        prefix = "bronze/polymarket/trades/dt=2024-01-01/"
        mk = prefix + "run_id=run-001/manifest.json"
        pk = prefix + "run_id=run-001/part-000.jsonl.gz"

        fake = FakeS3Client(
            keys_by_prefix={prefix: [mk, pk]},
            manifests={mk: manifest},
        )
        result = _invoke(fake)

        assert result.exit_code == 0
        assert "Valid runs:         1" in result.output
        assert "Invalid manifests:  0" in result.output
        assert "Missing part files: 0" in result.output
        assert "Orphaned files:     0" in result.output

    def test_invalid_manifest(self) -> None:
        """Unparseable manifest is flagged."""
        prefix = "bronze/polymarket/trades/dt=2024-01-01/"
        mk = prefix + "run_id=run-001/manifest.json"

        fake = FakeS3Client(
            keys_by_prefix={prefix: [mk]},
            manifests={},
            bad_manifests={mk},
        )
        result = _invoke(fake)

        assert result.exit_code == 1
        assert "Invalid manifests:  1" in result.output
        assert "Invalid manifest" in result.output

    def test_missing_part_files(self) -> None:
        """Manifest references a part file that doesn't exist in S3."""
        # Manifest references part-000.jsonl.gz but it's not in S3 keys
        manifest = _make_manifest()
        prefix = "bronze/polymarket/trades/dt=2024-01-01/"
        mk = prefix + "run_id=run-001/manifest.json"
        # Only manifest key exists, no part file
        fake = FakeS3Client(
            keys_by_prefix={prefix: [mk]},
            manifests={mk: manifest},
        )
        result = _invoke(fake)

        assert result.exit_code == 1
        assert "Missing part files: 1" in result.output
        assert "Missing part file" in result.output

    def test_orphaned_files(self) -> None:
        """Data files exist in a run directory without a manifest."""
        prefix = "bronze/polymarket/trades/dt=2024-01-01/"
        orphan = prefix + "run_id=run-001/part-000.jsonl.gz"

        fake = FakeS3Client(
            keys_by_prefix={prefix: [orphan]},
            manifests={},
        )
        result = _invoke(fake)

        assert result.exit_code == 1
        assert "Orphaned files:     1" in result.output
        assert "Orphaned file" in result.output

    def test_empty_run(self) -> None:
        """Manifest with row_count=0 is flagged as empty."""
        manifest = _make_manifest(row_count=0)
        prefix = "bronze/polymarket/trades/dt=2024-01-01/"
        mk = prefix + "run_id=run-001/manifest.json"
        pk = prefix + "run_id=run-001/part-000.jsonl.gz"

        fake = FakeS3Client(
            keys_by_prefix={prefix: [mk, pk]},
            manifests={mk: manifest},
        )
        result = _invoke(fake)

        # Empty runs are flagged but don't cause non-zero exit on their own
        assert result.exit_code == 0
        assert "Empty runs:         1" in result.output
        assert "Empty run" in result.output

    def test_no_data(self) -> None:
        """No data at all for the date range — nothing to validate."""
        fake = FakeS3Client(keys_by_prefix={}, manifests={})
        result = _invoke(fake)

        assert result.exit_code == 0
        assert "Valid runs:         0" in result.output

    def test_invalid_date(self) -> None:
        """Bad date format exits with error."""
        result = runner.invoke(app, [
            "status", "validate",
            "--start-date", "not-a-date",
            "--end-date", "2024-01-01",
            "--bucket", "test-bucket",
        ])
        assert result.exit_code == 1
        assert "Invalid date" in result.output

    def test_no_bucket(self) -> None:
        """Missing bucket exits with error."""
        with patch.dict("os.environ", {}, clear=True):
            result = runner.invoke(app, [
                "status", "validate",
                "--start-date", "2024-01-01",
                "--end-date", "2024-01-01",
            ])
        assert result.exit_code == 1

    def test_start_after_end(self) -> None:
        """Start date after end date exits with error."""
        result = runner.invoke(app, [
            "status", "validate",
            "--start-date", "2024-01-05",
            "--end-date", "2024-01-01",
            "--bucket", "test-bucket",
        ])
        assert result.exit_code == 1
        assert "start-date must be" in result.output
