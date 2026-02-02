"""Unit tests for the Gold S3 Parquet writer."""

from __future__ import annotations

from unittest.mock import MagicMock

import pyarrow as pa
import pyarrow.parquet as pq

from prediction_data.gold.s3_writer import (
    _build_parquet_key,
    _delete_existing_partition,
    write_gold_parquet,
)


def _sample_table() -> pa.Table:
    return pa.table({"id": [1, 2, 3], "value": ["a", "b", "c"]})


class TestBuildParquetKey:
    def test_key_format(self) -> None:
        key = _build_parquet_key("fact_trades", "2024-06-15", 0)
        assert key == "gold/fact_trades/day=2024-06-15/part-000.parquet"

    def test_part_number_padding(self) -> None:
        key = _build_parquet_key("fact_trades", "2024-06-15", 12)
        assert key == "gold/fact_trades/day=2024-06-15/part-012.parquet"


class TestDeleteExistingPartition:
    def test_no_existing_files(self) -> None:
        s3 = MagicMock()
        paginator = MagicMock()
        paginator.paginate.return_value = [{"Contents": []}]
        s3.get_paginator.return_value = paginator

        deleted = _delete_existing_partition(s3, "my-bucket", "fact_trades", "2024-06-15")
        assert deleted == 0
        s3.delete_objects.assert_not_called()

    def test_deletes_existing_files(self) -> None:
        s3 = MagicMock()
        paginator = MagicMock()
        paginator.paginate.return_value = [
            {
                "Contents": [
                    {"Key": "gold/fact_trades/day=2024-06-15/part-000.parquet"},
                    {"Key": "gold/fact_trades/day=2024-06-15/part-001.parquet"},
                ]
            }
        ]
        s3.get_paginator.return_value = paginator

        deleted = _delete_existing_partition(s3, "my-bucket", "fact_trades", "2024-06-15")
        assert deleted == 2
        s3.delete_objects.assert_called_once()


class TestWriteGoldParquet:
    def test_writes_parquet_with_zstd(self) -> None:
        s3 = MagicMock()
        paginator = MagicMock()
        paginator.paginate.return_value = [{"Contents": []}]
        s3.get_paginator.return_value = paginator

        table = _sample_table()
        key = write_gold_parquet(
            table, "gold-bucket", "fact_trades", "2024-06-15", s3_client=s3
        )

        assert key == "gold/fact_trades/day=2024-06-15/part-000.parquet"
        s3.put_object.assert_called_once()
        put_kwargs = s3.put_object.call_args.kwargs
        assert put_kwargs["Bucket"] == "gold-bucket"
        assert put_kwargs["Key"] == key
        assert put_kwargs["ContentType"] == "application/octet-stream"

        # Verify the body is valid Parquet with ZSTD
        import io

        buf = io.BytesIO(put_kwargs["Body"])
        read_back = pq.read_table(buf)
        assert read_back.num_rows == 3
        metadata = pq.read_metadata(buf)
        assert metadata.row_group(0).column(0).compression == "ZSTD"

    def test_idempotent_overwrites_partition(self) -> None:
        s3 = MagicMock()
        paginator = MagicMock()
        paginator.paginate.return_value = [
            {"Contents": [{"Key": "gold/t/day=2024-01-01/part-000.parquet"}]}
        ]
        s3.get_paginator.return_value = paginator

        table = _sample_table()
        write_gold_parquet(table, "b", "t", "2024-01-01", s3_client=s3)

        # Should delete first, then put
        s3.delete_objects.assert_called_once()
        s3.put_object.assert_called_once()

    def test_custom_compression(self) -> None:
        s3 = MagicMock()
        paginator = MagicMock()
        paginator.paginate.return_value = [{"Contents": []}]
        s3.get_paginator.return_value = paginator

        table = _sample_table()
        write_gold_parquet(
            table, "b", "t", "2024-01-01", s3_client=s3, compression="snappy"
        )

        import io

        put_kwargs = s3.put_object.call_args.kwargs
        buf = io.BytesIO(put_kwargs["Body"])
        metadata = pq.read_metadata(buf)
        assert metadata.row_group(0).column(0).compression == "SNAPPY"
