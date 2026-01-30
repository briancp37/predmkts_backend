"""Stream Bronze JSONL.gz data referenced by manifests.

Provides a reader that loads all JSONL.gz files referenced in a
:class:`~prediction_data.silver.discovery.DiscoveredManifest`, decompresses
them, parses each line, and yields Python dicts.  Handles multi-part files
and provides a records-read counter for progress tracking.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

import structlog

from prediction_data.core.compression import decompress_jsonl

if TYPE_CHECKING:
    from prediction_data.silver.discovery import DiscoveredManifest
    from prediction_data.storage.s3 import S3Client

logger = structlog.stdlib.get_logger(__name__)


@dataclass
class ReadResult:
    """Result of reading all Bronze data for a single manifest.

    Attributes:
        records: Parsed records from all referenced files.
        records_read: Total number of records read.
        files_read: Number of files successfully read.
        errors: Number of files that failed to read.
    """

    records: list[dict[str, Any]] = field(default_factory=list)
    records_read: int = 0
    files_read: int = 0
    errors: int = 0


async def read_manifest_data(
    s3_client: S3Client,
    manifest: DiscoveredManifest,
) -> ReadResult:
    """Read all Bronze JSONL.gz files referenced by a discovered manifest.

    Downloads each file listed in ``manifest.manifest.files``, decompresses
    the gzip data, parses JSONL lines, and collects all records.

    Args:
        s3_client: Initialised S3Client bound to the Bronze bucket.
        manifest: A discovered manifest whose files should be read.

    Returns:
        A :class:`ReadResult` with all parsed records and read statistics.

    Raises:
        ValueError: If the manifest references no files.
    """
    files = manifest.manifest.files
    if not files:
        raise ValueError(
            f"Manifest {manifest.run_id} for {manifest.platform}/{manifest.entity} "
            f"dt={manifest.dt} has no files"
        )

    result = ReadResult()

    for file_ref in files:
        key = file_ref.key
        try:
            compressed = s3_client._get_client().get_object(
                Bucket=file_ref.bucket, Key=key,
            )["Body"].read()
            records = decompress_jsonl(compressed)

            result.records.extend(records)
            result.records_read += len(records)
            result.files_read += 1

            logger.debug(
                "Read Bronze file",
                key=key,
                records=len(records),
                running_total=result.records_read,
            )
        except Exception:
            logger.warning(
                "Failed to read Bronze file",
                key=key,
                manifest_run_id=manifest.run_id,
                exc_info=True,
            )
            result.errors += 1

    logger.info(
        "Finished reading manifest data",
        platform=manifest.platform,
        entity=manifest.entity,
        dt=manifest.dt,
        run_id=manifest.run_id,
        records_read=result.records_read,
        files_read=result.files_read,
        errors=result.errors,
        expected_row_count=manifest.row_count,
    )

    return result
