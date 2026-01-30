"""S3 storage layer for Bronze layer data."""

import re
from collections.abc import Iterable
from typing import Any

import boto3
import structlog

from prediction_data.core.compression import compress_jsonl
from prediction_data.storage.manifest import Manifest

# Pattern for Bronze layer S3 key prefix
# Format: bronze/{platform}/{entity}/dt={YYYY-MM-DD}/run_id={uuid}/
# run_id can be any alphanumeric string with hyphens (UUIDs, custom IDs, etc.)
BRONZE_KEY_PREFIX_PATTERN = re.compile(
    r"^bronze/[a-z0-9_-]+/[a-z0-9_-]+/dt=\d{4}-\d{2}-\d{2}/run_id=[a-zA-Z0-9_-]+/$"
)

# Pattern for Bronze layer S3 key (full path with file)
BRONZE_KEY_PATTERN = re.compile(
    r"^bronze/[a-z0-9_-]+/[a-z0-9_-]+/dt=\d{4}-\d{2}-\d{2}/run_id=[a-zA-Z0-9_-]+/[^/]+$"
)

logger = structlog.stdlib.get_logger(__name__)


def build_s3_key_prefix(platform: str, entity: str, dt: str, run_id: str) -> str:
    """Build the S3 key prefix for Bronze layer storage.

    Args:
        platform: Prediction market platform (e.g., "polymarket", "kalshi").
        entity: Entity type (e.g., "markets", "trades").
        dt: Data partition date in YYYY-MM-DD format.
        run_id: Unique run identifier (UUID4).

    Returns:
        S3 key prefix in format: bronze/{platform}/{entity}/dt={dt}/run_id={run_id}/
    """
    return f"bronze/{platform}/{entity}/dt={dt}/run_id={run_id}/"


def validate_bronze_key_prefix(key_prefix: str) -> bool:
    """Validate that a key prefix matches the expected Bronze layout pattern.

    Args:
        key_prefix: S3 key prefix to validate.

    Returns:
        True if the key prefix matches the expected pattern.
    """
    return BRONZE_KEY_PREFIX_PATTERN.match(key_prefix) is not None


def validate_bronze_key(key: str) -> bool:
    """Validate that a full key matches the expected Bronze layout pattern.

    Args:
        key: S3 object key to validate.

    Returns:
        True if the key matches the expected pattern.
    """
    return BRONZE_KEY_PATTERN.match(key) is not None


class S3Client:
    """S3 client for Bronze layer storage operations.

    This client provides methods for uploading JSONL data files and manifests
    to S3 following the Bronze storage contract.

    Example:
        async with S3Client(bucket="my-bucket") as client:
            # Upload data
            key = await client.upload_jsonl(
                records=[{"id": 1}, {"id": 2}],
                platform="polymarket",
                entity="markets",
                dt="2024-01-15",
                run_id="abc-123",
            )

            # Upload manifest
            await client.upload_manifest(manifest)
    """

    def __init__(
        self,
        bucket: str,
        *,
        s3_client: Any | None = None,
        region_name: str | None = None,
    ) -> None:
        """Initialize the S3 client.

        Args:
            bucket: S3 bucket name for storage.
            s3_client: Optional boto3 S3 client (for testing/mocking).
            region_name: AWS region name (optional, uses default if not specified).
        """
        self._bucket = bucket
        self._s3_client = s3_client
        self._region_name = region_name
        self._owns_client = s3_client is None

    @property
    def bucket(self) -> str:
        """Get the S3 bucket name."""
        return self._bucket

    async def __aenter__(self) -> "S3Client":
        """Enter async context manager."""
        if self._s3_client is None:
            self._s3_client = boto3.client("s3", region_name=self._region_name)
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: Any,
    ) -> None:
        """Exit async context manager."""
        # boto3 client doesn't need explicit cleanup in most cases
        pass

    def _get_client(self) -> Any:
        """Get the boto3 S3 client, initializing if needed."""
        if self._s3_client is None:
            self._s3_client = boto3.client("s3", region_name=self._region_name)
        return self._s3_client

    async def upload_jsonl(
        self,
        records: Iterable[dict[str, Any]],
        *,
        platform: str,
        entity: str,
        dt: str,
        run_id: str,
        part_number: int = 0,
    ) -> tuple[str, int]:
        """Upload records as gzip-compressed JSONL to S3.

        The file is uploaded to the Bronze layer path:
        bronze/{platform}/{entity}/dt={dt}/run_id={run_id}/part-{part_number:03d}.jsonl.gz

        Args:
            records: Iterable of dictionaries to serialize and upload.
            platform: Prediction market platform.
            entity: Entity type being ingested.
            dt: Data partition date in YYYY-MM-DD format.
            run_id: Unique run identifier.
            part_number: Part number for the file (default 0).

        Returns:
            Tuple of (S3 key, row count).

        Raises:
            ValueError: If the generated key doesn't match Bronze layout pattern.
        """
        # Build the S3 key
        key_prefix = build_s3_key_prefix(platform, entity, dt, run_id)
        if not validate_bronze_key_prefix(key_prefix):
            raise ValueError(f"Invalid Bronze key prefix: {key_prefix}")

        filename = f"part-{part_number:03d}.jsonl.gz"
        key = f"{key_prefix}{filename}"

        if not validate_bronze_key(key):
            raise ValueError(f"Invalid Bronze key: {key}")

        # Compress the records
        compressed_data, row_count = compress_jsonl(records)

        # Upload to S3
        client = self._get_client()
        client.put_object(
            Bucket=self._bucket,
            Key=key,
            Body=compressed_data,
            ContentType="application/gzip",
            ContentEncoding="gzip",
        )

        logger.info(
            "Uploaded JSONL to S3",
            bucket=self._bucket,
            key=key,
            row_count=row_count,
            size_bytes=len(compressed_data),
        )

        return key, row_count

    async def upload_manifest(self, manifest: Manifest) -> str:
        """Upload a manifest to S3.

        The manifest is uploaded to:
        bronze/{platform}/{entity}/dt={dt}/run_id={run_id}/manifest.json

        Args:
            manifest: Manifest to upload.

        Returns:
            S3 key where the manifest was uploaded.

        Raises:
            ValueError: If the generated key doesn't match Bronze layout pattern.
        """
        # Build the S3 key from manifest fields
        key_prefix = build_s3_key_prefix(
            manifest.platform,
            manifest.entity,
            manifest.dt,
            manifest.run_id,
        )
        if not validate_bronze_key_prefix(key_prefix):
            raise ValueError(f"Invalid Bronze key prefix: {key_prefix}")

        key = f"{key_prefix}manifest.json"

        if not validate_bronze_key(key):
            raise ValueError(f"Invalid Bronze key: {key}")

        # Serialize and upload
        manifest_json = manifest.to_json()
        client = self._get_client()
        client.put_object(
            Bucket=self._bucket,
            Key=key,
            Body=manifest_json.encode("utf-8"),
            ContentType="application/json",
        )

        logger.info(
            "Uploaded manifest to S3",
            bucket=self._bucket,
            key=key,
            run_id=manifest.run_id,
            row_count=manifest.row_count,
        )

        return key

    async def download_manifest(self, key: str) -> Manifest:
        """Download and parse a manifest from S3.

        Args:
            key: S3 key of the manifest.

        Returns:
            Parsed Manifest object.
        """
        client = self._get_client()
        response = client.get_object(Bucket=self._bucket, Key=key)
        manifest_json = response["Body"].read().decode("utf-8")
        return Manifest.from_json(manifest_json)

    async def download_jsonl(self, key: str) -> list[dict[str, Any]]:
        """Download and decompress JSONL data from S3.

        Args:
            key: S3 key of the JSONL file.

        Returns:
            List of parsed records.
        """
        from prediction_data.core.compression import decompress_jsonl

        client = self._get_client()
        response = client.get_object(Bucket=self._bucket, Key=key)
        compressed_data = response["Body"].read()
        return decompress_jsonl(compressed_data)

    async def list_keys(self, prefix: str) -> list[str]:
        """List all keys under a prefix.

        Args:
            prefix: S3 key prefix to list.

        Returns:
            List of S3 keys.
        """
        client = self._get_client()
        paginator = client.get_paginator("list_objects_v2")
        keys: list[str] = []

        for page in paginator.paginate(Bucket=self._bucket, Prefix=prefix):
            for obj in page.get("Contents", []):
                keys.append(obj["Key"])

        return keys

    async def list_prefixes(self, prefix: str, delimiter: str = "/") -> list[str]:
        """List common prefixes (virtual directories) under *prefix*.

        Uses the S3 delimiter trick so only prefix strings are returned,
        not every individual key.  This is much faster than ``list_keys``
        when you only need the partition names.
        """
        client = self._get_client()
        paginator = client.get_paginator("list_objects_v2")
        prefixes: list[str] = []

        for page in paginator.paginate(
            Bucket=self._bucket, Prefix=prefix, Delimiter=delimiter,
        ):
            for cp in page.get("CommonPrefixes", []):
                prefixes.append(cp["Prefix"])

        return prefixes

    async def key_exists(self, key: str) -> bool:
        """Check if a key exists in the bucket.

        Args:
            key: S3 key to check.

        Returns:
            True if the key exists.
        """
        client = self._get_client()
        try:
            client.head_object(Bucket=self._bucket, Key=key)
            return True
        except client.exceptions.ClientError:
            return False
