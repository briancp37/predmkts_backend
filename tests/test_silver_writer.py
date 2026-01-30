"""Tests for Silver Iceberg writer."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import MagicMock, PropertyMock, patch

import pyarrow as pa
import pytest

from prediction_data.silver.writer import (
    IcebergWriteError,
    WriteResult,
    _to_arrow_table,
    write_to_iceberg,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _sample_records(n: int = 3) -> list[dict]:
    """Build sample normalized Polymarket trades records."""
    base_ts = datetime(2024, 6, 15, 12, 0, 0, tzinfo=UTC)
    return [
        {
            "event_ts": datetime(2024, 6, 15, 12, 0, i, tzinfo=UTC),
            "platform_market_id": f"market-{i}",
            "platform_trade_id": f"trade-{i}",
            "maker": f"0xmaker{i}",
            "taker": f"0xtaker{i}",
            "nonusdc_side": "maker",
            "maker_direction": "buy",
            "taker_direction": "sell",
            "price": 0.65 + i * 0.01,
            "usd_amount": 100.0 + i,
            "token_amount": 153.0 + i,
            "transaction_hash": f"0xhash{i}",
            "bronze_run_id": "run-abc",
            "silver_ingestion_ts": base_ts,
        }
        for i in range(n)
    ]


# ---------------------------------------------------------------------------
# _to_arrow_table
# ---------------------------------------------------------------------------

class TestToArrowTable:
    """Tests for dict-to-Arrow conversion."""

    def test_converts_records_to_arrow(self) -> None:
        from prediction_data.silver.tables import SILVER_TABLES

        schema, _ = SILVER_TABLES[("silver_polymarket", "trades")]
        records = _sample_records(2)

        result = _to_arrow_table(records, schema)

        assert isinstance(result, pa.Table)
        assert result.num_rows == 2
        assert result.num_columns == 14  # 14 fields in polymarket trades schema

    def test_missing_optional_fields_become_null(self) -> None:
        from prediction_data.silver.tables import SILVER_TABLES

        schema, _ = SILVER_TABLES[("silver_polymarket", "trades")]
        records = _sample_records(1)
        del records[0]["transaction_hash"]
        del records[0]["bronze_run_id"]
        del records[0]["silver_ingestion_ts"]

        result = _to_arrow_table(records, schema)

        assert result.num_rows == 1
        assert result.column("transaction_hash")[0].as_py() is None

    def test_type_mismatch_raises(self) -> None:
        from prediction_data.silver.tables import SILVER_TABLES

        schema, _ = SILVER_TABLES[("silver_polymarket", "trades")]
        records = [{"event_ts": "not-a-datetime", "platform_market_id": "m1",
                     "platform_trade_id": "t1", "maker": "a", "taker": "b",
                     "nonusdc_side": "maker", "maker_direction": "buy",
                     "taker_direction": "sell", "price": 0.5,
                     "usd_amount": 100.0, "token_amount": 200.0}]

        with pytest.raises(IcebergWriteError, match="Failed to convert"):
            _to_arrow_table(records, schema)


# ---------------------------------------------------------------------------
# write_to_iceberg
# ---------------------------------------------------------------------------

class TestWriteToIceberg:
    """Tests for the full write path with mocked catalog/table."""

    def _mock_catalog(self) -> MagicMock:
        catalog = MagicMock()
        mock_table = MagicMock()
        mock_snapshot = MagicMock()
        mock_snapshot.snapshot_id = 12345
        mock_table.current_snapshot.return_value = mock_snapshot
        catalog.load_table.return_value = mock_table
        return catalog

    def test_successful_write(self) -> None:
        catalog = self._mock_catalog()
        records = _sample_records(3)

        result = write_to_iceberg(
            records, catalog, "silver_polymarket", "trades"
        )

        assert isinstance(result, WriteResult)
        assert result.rows_written == 3
        assert result.snapshot_id == 12345
        assert result.namespace == "silver_polymarket"
        assert result.table_name == "trades"
        assert result.duration_seconds >= 0

        # Verify append was called with a PyArrow Table
        mock_table = catalog.load_table.return_value
        mock_table.append.assert_called_once()
        arg = mock_table.append.call_args[0][0]
        assert isinstance(arg, pa.Table)
        assert arg.num_rows == 3

    def test_empty_records_raises(self) -> None:
        catalog = self._mock_catalog()

        with pytest.raises(IcebergWriteError, match="empty record batch"):
            write_to_iceberg([], catalog, "silver_polymarket", "trades")

    def test_unknown_table_key_raises(self) -> None:
        catalog = self._mock_catalog()

        with pytest.raises(KeyError):
            write_to_iceberg(
                _sample_records(1), catalog, "nonexistent", "table"
            )

    def test_table_not_found_raises(self) -> None:
        catalog = MagicMock()
        catalog.load_table.side_effect = Exception("NoSuchTableException")

        with pytest.raises(IcebergWriteError, match="not found in catalog"):
            write_to_iceberg(
                _sample_records(1), catalog, "silver_polymarket", "trades"
            )

    def test_append_failure_raises(self) -> None:
        catalog = MagicMock()
        mock_table = MagicMock()
        mock_table.append.side_effect = RuntimeError("S3 write failed")
        catalog.load_table.return_value = mock_table

        with pytest.raises(IcebergWriteError, match="append failed"):
            write_to_iceberg(
                _sample_records(1), catalog, "silver_polymarket", "trades"
            )

    def test_no_snapshot_returns_negative_one(self) -> None:
        catalog = MagicMock()
        mock_table = MagicMock()
        mock_table.current_snapshot.return_value = None
        catalog.load_table.return_value = mock_table

        result = write_to_iceberg(
            _sample_records(1), catalog, "silver_polymarket", "trades"
        )

        assert result.snapshot_id == -1

    def test_works_with_markets_schema(self) -> None:
        """Verify writer works with a different entity schema."""
        catalog = self._mock_catalog()
        base_ts = datetime(2024, 6, 15, tzinfo=UTC)
        records = [
            {
                "event_ts": base_ts,
                "platform_market_id": "market-1",
                "question": "Will it rain?",
                "description": "Weather market",
                "market_slug": "will-it-rain",
                "status": "active",
                "outcome": None,
                "tokens": "[{\"id\": \"tok1\"}]",
                "event_id": "evt-1",
                "updated_at": base_ts,
                "bronze_run_id": "run-1",
                "silver_ingestion_ts": base_ts,
            }
        ]

        result = write_to_iceberg(
            records, catalog, "silver_polymarket", "markets"
        )

        assert result.rows_written == 1


class TestWriteResult:
    """Tests for WriteResult dataclass."""

    def test_fields(self) -> None:
        r = WriteResult(
            namespace="ns",
            table_name="tbl",
            rows_written=10,
            snapshot_id=999,
            duration_seconds=1.5,
        )
        assert r.namespace == "ns"
        assert r.table_name == "tbl"
        assert r.rows_written == 10
        assert r.snapshot_id == 999
        assert r.duration_seconds == 1.5
