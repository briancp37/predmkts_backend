"""Tests for Gold dimension table loaders."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pyarrow as pa
import pytest

from prediction_data.gold.canonical import CanonicalResolver
from prediction_data.gold.dimensions import (
    DIM_MARKET_COLUMNS,
    DIM_MARKET_SCHEMA,
    DIM_OUTCOME_COLUMNS,
    DIM_OUTCOME_SCHEMA,
    DIM_PLATFORM_SCHEMA,
    PLATFORMS,
    _platforms_to_arrow,
    _silver_to_dim_market,
    _silver_to_dim_outcome,
    load_dim_market,
    load_dim_outcome,
    load_dim_platform,
    parse_tokens,
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


# ---------------------------------------------------------------------------
# dim_market tests
# ---------------------------------------------------------------------------


def _fake_silver_markets() -> pa.Table:
    """Build a small Arrow table mimicking Silver polymarket.markets."""
    return pa.table(
        {
            "event_ts": pa.array(
                [1_700_000_000, 1_700_000_001], type=pa.timestamp("us", tz="UTC")
            ),
            "platform_market_id": ["mkt-1", "mkt-2"],
            "question": ["Will it rain?", "Will it snow?"],
            "description": ["Rain market", "Snow market"],
            "market_slug": ["will-it-rain", "will-it-snow"],
            "status": ["active", "closed"],
            "outcome": ["", ""],
            "tokens": ['[{"id":"t1"}]', '[{"id":"t2"}]'],
            "event_id": ["evt-1", "evt-2"],
            "updated_at": pa.array(
                [1_700_000_000, 1_700_000_001], type=pa.timestamp("us", tz="UTC")
            ),
            "bronze_run_id": ["run1", "run2"],
            "silver_ingestion_ts": pa.array(
                [1_700_000_000, 1_700_000_001], type=pa.timestamp("us", tz="UTC")
            ),
        }
    )


class TestSilverToDimMarket:
    def test_schema_matches(self) -> None:
        resolver = CanonicalResolver(yaml_path=None)
        result = _silver_to_dim_market(_fake_silver_markets(), "polymarket", resolver)
        assert result.schema.equals(DIM_MARKET_SCHEMA)

    def test_row_count(self) -> None:
        resolver = CanonicalResolver(yaml_path=None)
        result = _silver_to_dim_market(_fake_silver_markets(), "polymarket", resolver)
        assert result.num_rows == 2

    def test_platform_column(self) -> None:
        resolver = CanonicalResolver(yaml_path=None)
        result = _silver_to_dim_market(_fake_silver_markets(), "polymarket", resolver)
        assert result.column("platform").to_pylist() == ["polymarket", "polymarket"]

    def test_canonical_fallback(self) -> None:
        """Unmapped IDs fall back to the platform-native ID."""
        resolver = CanonicalResolver(yaml_path=None)
        result = _silver_to_dim_market(_fake_silver_markets(), "polymarket", resolver)
        assert result.column("canonical_market_id").to_pylist() == ["mkt-1", "mkt-2"]

    def test_canonical_mapped(self, tmp_path: object) -> None:
        """Mapped IDs resolve to their canonical ID."""
        import tempfile
        from pathlib import Path

        yaml_content = (
            "mappings:\n"
            "  canonical-rain:\n"
            "    polymarket: mkt-1\n"
        )
        yaml_file = Path(tempfile.mktemp(suffix=".yaml"))
        yaml_file.write_text(yaml_content)
        try:
            resolver = CanonicalResolver(yaml_path=yaml_file)
            result = _silver_to_dim_market(
                _fake_silver_markets(), "polymarket", resolver
            )
            canonical_ids = result.column("canonical_market_id").to_pylist()
            assert canonical_ids[0] == "canonical-rain"
            assert canonical_ids[1] == "mkt-2"  # unmapped fallback
        finally:
            yaml_file.unlink(missing_ok=True)

    def test_null_fields_become_empty_strings(self) -> None:
        """Null Silver fields convert to empty strings in dim_market."""
        arrow = pa.table(
            {
                "event_ts": pa.array(
                    [1_700_000_000], type=pa.timestamp("us", tz="UTC")
                ),
                "platform_market_id": ["mkt-x"],
                "question": [None],
                "description": [None],
                "market_slug": [None],
                "status": [None],
                "outcome": [None],
                "tokens": [None],
                "event_id": [None],
                "updated_at": pa.array([None], type=pa.timestamp("us", tz="UTC")),
                "bronze_run_id": [None],
                "silver_ingestion_ts": pa.array(
                    [None], type=pa.timestamp("us", tz="UTC")
                ),
            }
        )
        resolver = CanonicalResolver(yaml_path=None)
        result = _silver_to_dim_market(arrow, "polymarket", resolver)
        row = result.to_pylist()[0]
        assert row["question"] == ""
        assert row["tokens"] == ""


class TestLoadDimMarket:
    def test_dry_run_returns_count(self) -> None:
        mock_catalog = MagicMock()
        mock_table = MagicMock()
        mock_catalog.load_table.return_value = mock_table
        mock_table.scan.return_value.to_arrow.return_value = _fake_silver_markets()

        rows = load_dim_market(
            catalog=mock_catalog,
            dry_run=True,
        )
        assert rows == 2

    def test_writes_to_s3_and_clickhouse(self, mock_s3_gold: MagicMock) -> None:
        mock_ch = MagicMock()
        mock_catalog = MagicMock()
        mock_table = MagicMock()
        mock_catalog.load_table.return_value = mock_table
        mock_table.scan.return_value.to_arrow.return_value = _fake_silver_markets()

        with patch(
            "prediction_data.gold.dimensions.write_gold_parquet"
        ) as mock_write:
            rows = load_dim_market(
                gold_bucket="test-gold",
                s3_client=mock_s3_gold,
                clickhouse_client=mock_ch,
                catalog=mock_catalog,
            )

        assert rows == 2
        mock_write.assert_called_once()
        mock_ch.insert.assert_called_once()

        call_args = mock_ch.insert.call_args
        assert call_args[0][0] == "dim_market"
        assert len(call_args[1]["data"]) == 2

    def test_skips_s3_when_no_bucket(self) -> None:
        mock_ch = MagicMock()
        mock_catalog = MagicMock()
        mock_table = MagicMock()
        mock_catalog.load_table.return_value = mock_table
        mock_table.scan.return_value.to_arrow.return_value = _fake_silver_markets()

        with patch(
            "prediction_data.gold.dimensions.write_gold_parquet"
        ) as mock_write:
            load_dim_market(
                gold_bucket=None,
                clickhouse_client=mock_ch,
                catalog=mock_catalog,
            )

        mock_write.assert_not_called()
        mock_ch.insert.assert_called_once()


# ---------------------------------------------------------------------------
# dim_outcome tests
# ---------------------------------------------------------------------------


def _fake_silver_markets_with_tokens() -> pa.Table:
    """Silver markets with realistic token_id/outcome token data."""
    return pa.table(
        {
            "event_ts": pa.array(
                [1_700_000_000, 1_700_000_001], type=pa.timestamp("us", tz="UTC")
            ),
            "platform_market_id": ["mkt-1", "mkt-2"],
            "question": ["Will it rain?", "Will it snow?"],
            "description": ["Rain market", "Snow market"],
            "market_slug": ["will-it-rain", "will-it-snow"],
            "status": ["active", "closed"],
            "outcome": ["", ""],
            "tokens": [
                '[{"token_id":"tok-1a","outcome":"Yes"},{"token_id":"tok-1b","outcome":"No"}]',
                '[{"token_id":"tok-2a","outcome":"Yes"},{"token_id":"tok-2b","outcome":"No"}]',
            ],
            "event_id": ["evt-1", "evt-2"],
            "updated_at": pa.array(
                [1_700_000_000, 1_700_000_001], type=pa.timestamp("us", tz="UTC")
            ),
            "bronze_run_id": ["run1", "run2"],
            "silver_ingestion_ts": pa.array(
                [1_700_000_000, 1_700_000_001], type=pa.timestamp("us", tz="UTC")
            ),
        }
    )


class TestParseTokens:
    def test_valid_json(self) -> None:
        result = parse_tokens('[{"token_id":"a","outcome":"Yes"}]')
        assert len(result) == 1
        assert result[0]["token_id"] == "a"

    def test_none(self) -> None:
        assert parse_tokens(None) == []

    def test_empty_string(self) -> None:
        assert parse_tokens("") == []

    def test_invalid_json(self) -> None:
        assert parse_tokens("not json") == []

    def test_non_list_json(self) -> None:
        assert parse_tokens('{"token_id":"a"}') == []

    def test_filters_non_dict_items(self) -> None:
        result = parse_tokens('[{"token_id":"a"}, "bad", 123]')
        assert len(result) == 1


class TestSilverToDimOutcome:
    def test_schema_matches(self) -> None:
        result = _silver_to_dim_outcome(
            _fake_silver_markets_with_tokens(), "polymarket"
        )
        assert result.schema.equals(DIM_OUTCOME_SCHEMA)

    def test_two_markets_produce_four_outcomes(self) -> None:
        result = _silver_to_dim_outcome(
            _fake_silver_markets_with_tokens(), "polymarket"
        )
        assert result.num_rows == 4

    def test_side_assignment(self) -> None:
        result = _silver_to_dim_outcome(
            _fake_silver_markets_with_tokens(), "polymarket"
        )
        sides = result.column("side").to_pylist()
        assert sides == ["token1", "token2", "token1", "token2"]

    def test_outcome_id_format(self) -> None:
        result = _silver_to_dim_outcome(
            _fake_silver_markets_with_tokens(), "polymarket"
        )
        ids = result.column("outcome_id").to_pylist()
        assert ids == ["mkt-1_0", "mkt-1_1", "mkt-2_0", "mkt-2_1"]

    def test_token_ids(self) -> None:
        result = _silver_to_dim_outcome(
            _fake_silver_markets_with_tokens(), "polymarket"
        )
        token_ids = result.column("token_id").to_pylist()
        assert token_ids == ["tok-1a", "tok-1b", "tok-2a", "tok-2b"]

    def test_outcome_labels(self) -> None:
        result = _silver_to_dim_outcome(
            _fake_silver_markets_with_tokens(), "polymarket"
        )
        labels = result.column("outcome_label").to_pylist()
        assert labels == ["Yes", "No", "Yes", "No"]

    def test_market_with_no_tokens_skipped(self) -> None:
        arrow = pa.table(
            {
                "event_ts": pa.array(
                    [1_700_000_000], type=pa.timestamp("us", tz="UTC")
                ),
                "platform_market_id": ["mkt-x"],
                "question": ["Q"],
                "description": ["D"],
                "market_slug": ["q"],
                "status": ["active"],
                "outcome": [""],
                "tokens": [None],
                "event_id": ["evt-x"],
                "updated_at": pa.array(
                    [1_700_000_000], type=pa.timestamp("us", tz="UTC")
                ),
                "bronze_run_id": ["run1"],
                "silver_ingestion_ts": pa.array(
                    [1_700_000_000], type=pa.timestamp("us", tz="UTC")
                ),
            }
        )
        result = _silver_to_dim_outcome(arrow, "polymarket")
        assert result.num_rows == 0


class TestLoadDimOutcome:
    def test_dry_run_returns_count(self) -> None:
        mock_catalog = MagicMock()
        mock_table = MagicMock()
        mock_catalog.load_table.return_value = mock_table
        mock_table.scan.return_value.to_arrow.return_value = (
            _fake_silver_markets_with_tokens()
        )

        rows = load_dim_outcome(catalog=mock_catalog, dry_run=True)
        assert rows == 4

    def test_writes_to_s3_and_clickhouse(self, mock_s3_gold: MagicMock) -> None:
        mock_ch = MagicMock()
        mock_catalog = MagicMock()
        mock_table = MagicMock()
        mock_catalog.load_table.return_value = mock_table
        mock_table.scan.return_value.to_arrow.return_value = (
            _fake_silver_markets_with_tokens()
        )

        with patch(
            "prediction_data.gold.dimensions.write_gold_parquet"
        ) as mock_write:
            rows = load_dim_outcome(
                gold_bucket="test-gold",
                s3_client=mock_s3_gold,
                clickhouse_client=mock_ch,
                catalog=mock_catalog,
            )

        assert rows == 4
        mock_write.assert_called_once()
        mock_ch.insert.assert_called_once()

        call_args = mock_ch.insert.call_args
        assert call_args[0][0] == "dim_outcome"
        assert len(call_args[1]["data"]) == 4

    def test_skips_s3_when_no_bucket(self) -> None:
        mock_ch = MagicMock()
        mock_catalog = MagicMock()
        mock_table = MagicMock()
        mock_catalog.load_table.return_value = mock_table
        mock_table.scan.return_value.to_arrow.return_value = (
            _fake_silver_markets_with_tokens()
        )

        with patch(
            "prediction_data.gold.dimensions.write_gold_parquet"
        ) as mock_write:
            load_dim_outcome(
                gold_bucket=None,
                clickhouse_client=mock_ch,
                catalog=mock_catalog,
            )

        mock_write.assert_not_called()
        mock_ch.insert.assert_called_once()
