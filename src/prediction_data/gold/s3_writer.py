"""S3 Gold Parquet writer for canonical Gold table output."""

from __future__ import annotations

from typing import Any

import boto3
import pyarrow as pa
import pyarrow.parquet as pq
import structlog

from prediction_data.gold.config import GOLD_PATH_TEMPLATE

logger = structlog.stdlib.get_logger(__name__)


def _build_partition_prefix(table_name: str, day: str) -> str:
    """Build the S3 key prefix for a Gold partition.

    Returns prefix like ``gold/<table_name>/day=YYYY-MM-DD/``.
    """
    return f"gold/{table_name}/day={day}/"


def _build_parquet_key(table_name: str, day: str, part_number: int) -> str:
    """Build the full S3 key for a Gold Parquet part file."""
    filename = f"part-{part_number:03d}.parquet"
    return GOLD_PATH_TEMPLATE.format(table_name=table_name, day=day, filename=filename)


def _delete_existing_partition(
    s3_client: Any,
    bucket: str,
    table_name: str,
    day: str,
) -> int:
    """Delete all existing files under a Gold partition prefix.

    Returns the number of objects deleted.
    """
    prefix = _build_partition_prefix(table_name, day)
    paginator = s3_client.get_paginator("list_objects_v2")
    keys_to_delete: list[dict[str, str]] = []

    for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
        for obj in page.get("Contents", []):
            keys_to_delete.append({"Key": obj["Key"]})

    if not keys_to_delete:
        return 0

    # delete_objects supports up to 1000 keys per call
    deleted = 0
    for i in range(0, len(keys_to_delete), 1000):
        batch = keys_to_delete[i : i + 1000]
        s3_client.delete_objects(Bucket=bucket, Delete={"Objects": batch})
        deleted += len(batch)

    logger.info(
        "deleted_existing_partition",
        bucket=bucket,
        prefix=prefix,
        count=deleted,
    )
    return deleted


def write_gold_parquet(
    table: pa.Table,
    bucket: str,
    table_name: str,
    day: str,
    *,
    part_number: int = 0,
    s3_client: Any | None = None,
    compression: str = "zstd",
) -> str:
    """Write a PyArrow Table to S3 as a Gold Parquet file.

    Performs idempotent partition overwrite: deletes all existing files under the
    partition prefix before writing the new file.

    Args:
        table: PyArrow Table to write.
        bucket: S3 bucket name.
        table_name: Gold table name (e.g. ``"fact_trades"``).
        day: Partition day in ``YYYY-MM-DD`` format.
        part_number: Part file number (default 0).
        s3_client: Optional boto3 S3 client (created if not provided).
        compression: Parquet compression codec (default ``"zstd"``).

    Returns:
        The S3 key of the written Parquet file.
    """
    import io

    if s3_client is None:
        s3_client = boto3.client("s3")

    # Idempotent: remove existing partition data first
    _delete_existing_partition(s3_client, bucket, table_name, day)

    # Write Parquet to in-memory buffer
    buf = io.BytesIO()
    pq.write_table(table, buf, compression=compression)
    buf.seek(0)

    key = _build_parquet_key(table_name, day, part_number)
    s3_client.put_object(
        Bucket=bucket,
        Key=key,
        Body=buf.getvalue(),
        ContentType="application/octet-stream",
    )

    logger.info(
        "wrote_gold_parquet",
        bucket=bucket,
        key=key,
        num_rows=table.num_rows,
        compression=compression,
    )
    return key
