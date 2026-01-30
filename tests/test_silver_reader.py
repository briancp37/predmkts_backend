"""Tests for Silver Bronze data reader."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import MagicMock

import pytest

from prediction_data.core.compression import compress_jsonl
from prediction_data.silver.discovery import DiscoveredManifest
from prediction_data.silver.reader import ReadResult, read_manifest_data
from prediction_data.storage.manifest import FileReference, Manifest, Source


def _make_manifest(
    platform: str = "polymarket",
    entity: str = "trades",
    dt: str = "2024-06-15",
    run_id: str = "run-001",
    row_count: int = 3,
    files: list[FileReference] | None = None,
) -> DiscoveredManifest:
    if files is None:
        files = [
            FileReference(
                bucket="test-bucket",
                key=f"bronze/{platform}/{entity}/dt={dt}/run_id={run_id}/part-000.jsonl.gz",
            )
        ]
    manifest = Manifest(
        run_id=run_id,
        platform=platform,
        entity=entity,
        dt=dt,
        generated_at=datetime(2024, 6, 15, 12, 0, 0, tzinfo=UTC),
        files=files,
        row_count=row_count,
        source=Source(api_base_url="https://example.com", pagination="cursor"),
    )
    return DiscoveredManifest(
        manifest=manifest,
        s3_key=f"bronze/{platform}/{entity}/dt={dt}/run_id={run_id}/manifest.json",
    )


def _mock_s3_with_data(
    data_by_key: dict[str, list[dict]],
) -> MagicMock:
    """Build a mock S3Client that returns compressed JSONL for given keys."""
    boto_client = MagicMock()

    def _get_object(Bucket: str, Key: str) -> dict:  # noqa: N803
        if Key not in data_by_key:
            raise Exception(f"NoSuchKey: {Key}")
        compressed, _ = compress_jsonl(data_by_key[Key])
        body = MagicMock()
        body.read.return_value = compressed
        return {"Body": body}

    boto_client.get_object = MagicMock(side_effect=_get_object)

    s3_client = MagicMock()
    s3_client._get_client.return_value = boto_client
    return s3_client


class TestReadManifestData:
    @pytest.mark.asyncio
    async def test_reads_single_file(self) -> None:
        records = [{"id": "1", "value": 10}, {"id": "2", "value": 20}]
        dm = _make_manifest(row_count=2)
        key = dm.manifest.files[0].key
        s3 = _mock_s3_with_data({key: records})

        result = await read_manifest_data(s3, dm)

        assert result.records == records
        assert result.records_read == 2
        assert result.files_read == 1
        assert result.errors == 0

    @pytest.mark.asyncio
    async def test_reads_multi_part_files(self) -> None:
        files = [
            FileReference(bucket="b", key="bronze/p/e/dt=2024-01-01/run_id=r1/part-000.jsonl.gz"),
            FileReference(bucket="b", key="bronze/p/e/dt=2024-01-01/run_id=r1/part-001.jsonl.gz"),
        ]
        dm = _make_manifest(files=files, row_count=4)
        data = {
            files[0].key: [{"id": "1"}, {"id": "2"}],
            files[1].key: [{"id": "3"}, {"id": "4"}],
        }
        s3 = _mock_s3_with_data(data)

        result = await read_manifest_data(s3, dm)

        assert len(result.records) == 4
        assert result.records_read == 4
        assert result.files_read == 2
        assert result.errors == 0

    @pytest.mark.asyncio
    async def test_empty_files_raises(self) -> None:
        dm = _make_manifest(files=[], row_count=0)
        s3 = _mock_s3_with_data({})

        with pytest.raises(ValueError, match="has no files"):
            await read_manifest_data(s3, dm)

    @pytest.mark.asyncio
    async def test_file_read_error_counted(self) -> None:
        dm = _make_manifest(row_count=0)
        # Don't provide data for the key so get_object raises
        s3 = _mock_s3_with_data({})

        result = await read_manifest_data(s3, dm)

        assert result.records == []
        assert result.records_read == 0
        assert result.files_read == 0
        assert result.errors == 1

    @pytest.mark.asyncio
    async def test_partial_failure(self) -> None:
        """One file succeeds, another fails."""
        files = [
            FileReference(bucket="b", key="bronze/p/e/dt=2024-01-01/run_id=r1/part-000.jsonl.gz"),
            FileReference(bucket="b", key="bronze/p/e/dt=2024-01-01/run_id=r1/part-001.jsonl.gz"),
        ]
        dm = _make_manifest(files=files, row_count=2)
        # Only provide data for first file
        data = {files[0].key: [{"id": "1"}, {"id": "2"}]}
        s3 = _mock_s3_with_data(data)

        result = await read_manifest_data(s3, dm)

        assert len(result.records) == 2
        assert result.records_read == 2
        assert result.files_read == 1
        assert result.errors == 1

    @pytest.mark.asyncio
    async def test_preserves_record_order(self) -> None:
        files = [
            FileReference(bucket="b", key="bronze/p/e/dt=2024-01-01/run_id=r1/part-000.jsonl.gz"),
            FileReference(bucket="b", key="bronze/p/e/dt=2024-01-01/run_id=r1/part-001.jsonl.gz"),
        ]
        dm = _make_manifest(files=files, row_count=3)
        data = {
            files[0].key: [{"seq": 1}],
            files[1].key: [{"seq": 2}, {"seq": 3}],
        }
        s3 = _mock_s3_with_data(data)

        result = await read_manifest_data(s3, dm)

        assert [r["seq"] for r in result.records] == [1, 2, 3]

    @pytest.mark.asyncio
    async def test_handles_utf8_content(self) -> None:
        records = [{"name": "café"}, {"name": "naïve"}]
        dm = _make_manifest(row_count=2)
        key = dm.manifest.files[0].key
        s3 = _mock_s3_with_data({key: records})

        result = await read_manifest_data(s3, dm)

        assert result.records[0]["name"] == "café"
        assert result.records[1]["name"] == "naïve"
