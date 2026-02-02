"""ClickHouse loading pattern: read Parquet from S3 and insert into ClickHouse.

This module will be fleshed out once the ClickHouse Python client and S3 Gold
writer are in place (see python_client and gold_s3_writer sprint categories).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import pyarrow as pa  # type: ignore[import-untyped]


def load_parquet_to_clickhouse(
    table_name: str,
    arrow_table: pa.Table,
    *,
    clickhouse_host: str = "localhost",
    clickhouse_port: int = 8123,
    database: str = "prediction_gold",
) -> int:
    """Insert an Arrow table into a ClickHouse table.

    Returns the number of rows inserted.

    .. note::
        Stub implementation — requires ``clickhouse-connect`` dependency
        (added in the python_client sprint category).
    """
    raise NotImplementedError(
        "ClickHouse loader requires clickhouse-connect. "
        "See python_client sprint category."
    )
