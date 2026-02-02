"""Tests for Gold dimension table loaders."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pyarrow as pa
import pytest

from prediction_data.gold.dimensions import (
    DIM_PLATFORM_SCHEMA,
    PLATFORMS,
    _platforms_to_arrow,
    load_dim_platform,
)


class TestPlatformsToArrow:
    def test_returns_arrow_table(self) -> None:
        table = _platforms_to_arrow()
        assert isinstance(table, pa.Table)

    def test_schema_matches(self) -> None:
        table = _platforms_to_arrow()
        assert table.schema.equals(DIM_PLATFORM_SCHEMA)

    def test_row_count(self) -> None:
        table = _platforms_to_arrow()
        assert table.num_rows == len(PLATFORMS)

    def test_platform_ids(self) -> None:
        table = _platforms_to_arrow()
        ids = table.column("platform_id").to_pylist()
        assert "polymarket" in ids
        assert "kalshi" in ids


class TestLoadDimPlatform:
    def test_dry_run_returns_count_without_writing(self) -> None:
        rows = load_dim_platform(dry_run=True)
        assert rows == len(PLATFORMS)

    def test_writes_to_s3_and_clickhouse(self, mock_s3_gold: MagicMock) -> None:
        mock_ch = MagicMock()
        with patch(
            "prediction_data.gold.dimensions.write_gold_parquet"
        ) as mock_write:
            rows = load_dim_platform(
                gold_bucket="test-gold",
                s3_client=mock_s3_gold,
                clickhouse_client=mock_ch,
            )

        assert rows == len(PLATFORMS)
        mock_write.assert_called_once()
        mock_ch.insert.assert_called_once()

        # Verify insert arguments.
        call_args = mock_ch.insert.call_args
        assert call_args[0][0] == "dim_platform"
        assert len(call_args[1]["data"]) == len(PLATFORMS)

    def test_skips_s3_when_no_bucket(self) -> None:
        mock_ch = MagicMock()
        with patch(
            "prediction_data.gold.dimensions.write_gold_parquet"
        ) as mock_write:
            load_dim_platform(
                gold_bucket=None,
                clickhouse_client=mock_ch,
            )

        mock_write.assert_not_called()
        mock_ch.insert.assert_called_once()

    def test_creates_client_when_not_provided(self, mock_s3_gold: MagicMock) -> None:
        with (
            patch("prediction_data.gold.dimensions.write_gold_parquet"),
            patch("prediction_data.gold.dimensions.get_client") as mock_get,
        ):
            mock_get.return_value = MagicMock()
            load_dim_platform(
                gold_bucket="test-gold",
                s3_client=mock_s3_gold,
            )

        mock_get.assert_called_once()
