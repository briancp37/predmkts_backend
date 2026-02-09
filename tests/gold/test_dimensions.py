"""Tests for Gold dimension table loaders."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pyarrow as pa
import pytest

from prediction_data.gold.canonical import CanonicalResolver
from prediction_data.gold.dimensions import (
    DIM_CATEGORY_COLUMNS,
    DIM_CATEGORY_SCHEMA,
    DIM_EVENT_COLUMNS,
    DIM_EVENT_SCHEMA,
    DIM_MARKET_COLUMNS,
    DIM_MARKET_SCHEMA,
    DIM_OUTCOME_COLUMNS,
    DIM_OUTCOME_SCHEMA,
    DIM_PLATFORM_SCHEMA,
    DIM_WALLET_COLUMNS,
    DIM_WALLET_SCHEMA,
    PLATFORMS,
    _platforms_to_arrow,
    _silver_events_to_dim_category,
    _silver_to_dim_event,
    _silver_to_dim_market,
    _silver_to_dim_outcome,
    _silver_trades_to_dim_wallet,
    load_dim_category,
    load_dim_event,
    load_dim_market,
    load_dim_outcome,
    load_dim_platform,
    load_dim_wallet,
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


# ---------------------------------------------------------------------------
# dim_wallet tests
# ---------------------------------------------------------------------------


def _fake_silver_trades() -> pa.Table:
    """Build a small Arrow table mimicking Silver polymarket.trades."""
    return pa.table(
        {
            "event_ts": pa.array(
                [1_700_000_000, 1_700_100_000, 1_700_200_000],
                type=pa.timestamp("us", tz="UTC"),
            ),
            "platform_market_id": ["mkt-1", "mkt-1", "mkt-2"],
            "platform_trade_id": ["t1", "t2", "t3"],
            "maker": ["wallet-a", "wallet-b", "wallet-a"],
            "taker": ["wallet-b", "wallet-a", "wallet-c"],
            "nonusdc_side": ["buy", "sell", "buy"],
            "maker_direction": ["buy", "sell", "buy"],
            "taker_direction": ["sell", "buy", "sell"],
            "price": [0.5, 0.6, 0.7],
            "usd_amount": [100.0, 200.0, 300.0],
            "token_amount": [200.0, 333.33, 428.57],
            "transaction_hash": ["0xabc", "0xdef", "0x123"],
            "bronze_run_id": ["run1", "run1", "run2"],
            "silver_ingestion_ts": pa.array(
                [1_700_000_000, 1_700_000_000, 1_700_000_000],
                type=pa.timestamp("us", tz="UTC"),
            ),
        }
    )


class TestSilverTradesToDimWallet:
    def test_schema_matches(self) -> None:
        result = _silver_trades_to_dim_wallet(_fake_silver_trades(), "polymarket")
        assert result.schema.equals(DIM_WALLET_SCHEMA)

    def test_unique_wallets(self) -> None:
        result = _silver_trades_to_dim_wallet(_fake_silver_trades(), "polymarket")
        addresses = sorted(result.column("wallet_address").to_pylist())
        assert addresses == ["wallet-a", "wallet-b", "wallet-c"]

    def test_trade_count(self) -> None:
        result = _silver_trades_to_dim_wallet(_fake_silver_trades(), "polymarket")
        rows = {r["wallet_address"]: r for r in result.to_pylist()}
        # wallet-a: maker in t1, taker in t2, maker in t3 = 3
        assert rows["wallet-a"]["trade_count"] == 3
        # wallet-b: taker in t1, maker in t2 = 2
        assert rows["wallet-b"]["trade_count"] == 2
        # wallet-c: taker in t3 = 1
        assert rows["wallet-c"]["trade_count"] == 1

    def test_first_last_trade_ts(self) -> None:
        result = _silver_trades_to_dim_wallet(_fake_silver_trades(), "polymarket")
        rows = {r["wallet_address"]: r for r in result.to_pylist()}
        # wallet-a appears in trades at ts 1_700_000_000, 1_700_100_000, 1_700_200_000
        a = rows["wallet-a"]
        assert a["first_trade_ts"] < a["last_trade_ts"]

    def test_platform_column(self) -> None:
        result = _silver_trades_to_dim_wallet(_fake_silver_trades(), "polymarket")
        platforms = result.column("platform").to_pylist()
        assert all(p == "polymarket" for p in platforms)

    def test_empty_trades(self) -> None:
        empty = pa.table(
            {
                "event_ts": pa.array([], type=pa.timestamp("us", tz="UTC")),
                "platform_market_id": pa.array([], type=pa.string()),
                "platform_trade_id": pa.array([], type=pa.string()),
                "maker": pa.array([], type=pa.string()),
                "taker": pa.array([], type=pa.string()),
                "nonusdc_side": pa.array([], type=pa.string()),
                "maker_direction": pa.array([], type=pa.string()),
                "taker_direction": pa.array([], type=pa.string()),
                "price": pa.array([], type=pa.float64()),
                "usd_amount": pa.array([], type=pa.float64()),
                "token_amount": pa.array([], type=pa.float64()),
                "transaction_hash": pa.array([], type=pa.string()),
                "bronze_run_id": pa.array([], type=pa.string()),
                "silver_ingestion_ts": pa.array([], type=pa.timestamp("us", tz="UTC")),
            }
        )
        result = _silver_trades_to_dim_wallet(empty, "polymarket")
        assert result.num_rows == 0
        assert result.schema.equals(DIM_WALLET_SCHEMA)

    def test_null_address_skipped(self) -> None:
        arrow = pa.table(
            {
                "event_ts": pa.array(
                    [1_700_000_000], type=pa.timestamp("us", tz="UTC")
                ),
                "platform_market_id": ["mkt-1"],
                "platform_trade_id": ["t1"],
                "maker": [None],
                "taker": ["wallet-x"],
                "nonusdc_side": ["buy"],
                "maker_direction": ["buy"],
                "taker_direction": ["sell"],
                "price": [0.5],
                "usd_amount": [100.0],
                "token_amount": [200.0],
                "transaction_hash": ["0xabc"],
                "bronze_run_id": ["run1"],
                "silver_ingestion_ts": pa.array(
                    [1_700_000_000], type=pa.timestamp("us", tz="UTC")
                ),
            }
        )
        result = _silver_trades_to_dim_wallet(arrow, "polymarket")
        assert result.num_rows == 1
        assert result.column("wallet_address").to_pylist() == ["wallet-x"]


class TestLoadDimWallet:
    def test_dry_run_returns_count(self) -> None:
        mock_catalog = MagicMock()
        mock_table = MagicMock()
        mock_catalog.load_table.return_value = mock_table
        mock_table.scan.return_value.to_arrow.return_value = _fake_silver_trades()

        rows = load_dim_wallet(catalog=mock_catalog, dry_run=True)
        assert rows == 3  # 3 unique wallets

    def test_writes_to_s3_and_clickhouse(self, mock_s3_gold: MagicMock) -> None:
        mock_ch = MagicMock()
        mock_catalog = MagicMock()
        mock_table = MagicMock()
        mock_catalog.load_table.return_value = mock_table
        mock_table.scan.return_value.to_arrow.return_value = _fake_silver_trades()

        with patch(
            "prediction_data.gold.dimensions.write_gold_parquet"
        ) as mock_write:
            rows = load_dim_wallet(
                gold_bucket="test-gold",
                s3_client=mock_s3_gold,
                clickhouse_client=mock_ch,
                catalog=mock_catalog,
            )

        assert rows == 3
        mock_write.assert_called_once()
        mock_ch.insert.assert_called_once()

        call_args = mock_ch.insert.call_args
        assert call_args[0][0] == "dim_wallet"
        assert len(call_args[1]["data"]) == 3

    def test_skips_s3_when_no_bucket(self) -> None:
        mock_ch = MagicMock()
        mock_catalog = MagicMock()
        mock_table = MagicMock()
        mock_catalog.load_table.return_value = mock_table
        mock_table.scan.return_value.to_arrow.return_value = _fake_silver_trades()

        with patch(
            "prediction_data.gold.dimensions.write_gold_parquet"
        ) as mock_write:
            load_dim_wallet(
                gold_bucket=None,
                clickhouse_client=mock_ch,
                catalog=mock_catalog,
            )

        mock_write.assert_not_called()
        mock_ch.insert.assert_called_once()


# ---------------------------------------------------------------------------
# dim_event tests
# ---------------------------------------------------------------------------


def _fake_silver_events() -> pa.Table:
    """Build a small Arrow table mimicking Silver polymarket.events."""
    return pa.table(
        {
            "event_ts": pa.array(
                [1_700_000_000, 1_700_000_001], type=pa.timestamp("us", tz="UTC")
            ),
            "platform_event_id": ["evt-1", "evt-2"],
            "title": ["US Election", "Super Bowl"],
            "description": ["Presidential election", "Football championship"],
            "slug": ["us-election", "super-bowl"],
            "status": ["active", "closed"],
            "category": ["politics", "sports"],
            "updated_at": pa.array(
                [1_700_000_000, 1_700_000_001], type=pa.timestamp("us", tz="UTC")
            ),
            "bronze_run_id": ["run1", "run2"],
            "silver_ingestion_ts": pa.array(
                [1_700_000_000, 1_700_000_001], type=pa.timestamp("us", tz="UTC")
            ),
            "tags": [["Politics", "Elections"], ["Sports", "NFL"]],
        }
    )


class TestSilverToDimEvent:
    def test_schema_matches(self) -> None:
        result = _silver_to_dim_event(_fake_silver_events(), "polymarket")
        assert result.schema.equals(DIM_EVENT_SCHEMA)

    def test_row_count(self) -> None:
        result = _silver_to_dim_event(_fake_silver_events(), "polymarket")
        assert result.num_rows == 2

    def test_platform_column(self) -> None:
        result = _silver_to_dim_event(_fake_silver_events(), "polymarket")
        assert result.column("platform").to_pylist() == ["polymarket", "polymarket"]

    def test_field_mapping(self) -> None:
        result = _silver_to_dim_event(_fake_silver_events(), "polymarket")
        rows = result.to_pylist()
        assert rows[0]["title"] == "US Election"
        assert rows[0]["category"] == "politics"
        assert rows[1]["slug"] == "super-bowl"
        assert rows[1]["status"] == "closed"

    def test_null_fields_become_empty_strings(self) -> None:
        arrow = pa.table(
            {
                "event_ts": pa.array(
                    [1_700_000_000], type=pa.timestamp("us", tz="UTC")
                ),
                "platform_event_id": ["evt-x"],
                "title": [None],
                "description": [None],
                "slug": [None],
                "status": [None],
                "category": [None],
                "updated_at": pa.array([None], type=pa.timestamp("us", tz="UTC")),
                "bronze_run_id": [None],
                "silver_ingestion_ts": pa.array(
                    [None], type=pa.timestamp("us", tz="UTC")
                ),
                "tags": [None],
            }
        )
        result = _silver_to_dim_event(arrow, "polymarket")
        row = result.to_pylist()[0]
        assert row["title"] == ""
        assert row["description"] == ""
        assert row["slug"] == ""
        assert row["status"] == ""
        assert row["category"] == ""
        assert row["tags"] == []

    def test_dedup_by_platform_event_id(self) -> None:
        """Duplicate event IDs are deduplicated (last-write-wins)."""
        arrow = pa.table(
            {
                "event_ts": pa.array(
                    [1_700_000_000, 1_700_000_001], type=pa.timestamp("us", tz="UTC")
                ),
                "platform_event_id": ["evt-1", "evt-1"],
                "title": ["Old Title", "New Title"],
                "description": ["Old", "New"],
                "slug": ["old-slug", "new-slug"],
                "status": ["active", "closed"],
                "category": ["politics", "politics"],
                "updated_at": pa.array(
                    [1_700_000_000, 1_700_000_001], type=pa.timestamp("us", tz="UTC")
                ),
                "bronze_run_id": ["run1", "run2"],
                "silver_ingestion_ts": pa.array(
                    [1_700_000_000, 1_700_000_001], type=pa.timestamp("us", tz="UTC")
                ),
                "tags": [["Politics"], ["Politics", "Elections"]],
            }
        )
        result = _silver_to_dim_event(arrow, "polymarket")
        assert result.num_rows == 1
        row = result.to_pylist()[0]
        assert row["title"] == "New Title"
        assert row["status"] == "closed"
        assert row["tags"] == ["Politics", "Elections"]

    def test_empty_events(self) -> None:
        empty = pa.table(
            {
                "event_ts": pa.array([], type=pa.timestamp("us", tz="UTC")),
                "platform_event_id": pa.array([], type=pa.string()),
                "title": pa.array([], type=pa.string()),
                "description": pa.array([], type=pa.string()),
                "slug": pa.array([], type=pa.string()),
                "status": pa.array([], type=pa.string()),
                "category": pa.array([], type=pa.string()),
                "updated_at": pa.array([], type=pa.timestamp("us", tz="UTC")),
                "bronze_run_id": pa.array([], type=pa.string()),
                "silver_ingestion_ts": pa.array([], type=pa.timestamp("us", tz="UTC")),
                "tags": pa.array([], type=pa.list_(pa.string())),
            }
        )
        result = _silver_to_dim_event(empty, "polymarket")
        assert result.num_rows == 0
        assert result.schema.equals(DIM_EVENT_SCHEMA)

    def test_tags_extracted(self) -> None:
        """Tags are properly extracted from Silver events."""
        result = _silver_to_dim_event(_fake_silver_events(), "polymarket")
        rows = result.to_pylist()
        assert rows[0]["tags"] == ["Politics", "Elections"]
        assert rows[1]["tags"] == ["Sports", "NFL"]


class TestLoadDimEvent:
    def test_dry_run_returns_count(self) -> None:
        mock_catalog = MagicMock()
        mock_table = MagicMock()
        mock_catalog.load_table.return_value = mock_table
        mock_table.scan.return_value.to_arrow.return_value = _fake_silver_events()

        rows = load_dim_event(catalog=mock_catalog, dry_run=True)
        assert rows == 2

    def test_writes_to_s3_and_clickhouse(self, mock_s3_gold: MagicMock) -> None:
        mock_ch = MagicMock()
        mock_catalog = MagicMock()
        mock_table = MagicMock()
        mock_catalog.load_table.return_value = mock_table
        mock_table.scan.return_value.to_arrow.return_value = _fake_silver_events()

        with patch(
            "prediction_data.gold.dimensions.write_gold_parquet"
        ) as mock_write:
            rows = load_dim_event(
                gold_bucket="test-gold",
                s3_client=mock_s3_gold,
                clickhouse_client=mock_ch,
                catalog=mock_catalog,
            )

        assert rows == 2
        mock_write.assert_called_once()
        mock_ch.insert.assert_called_once()

        call_args = mock_ch.insert.call_args
        assert call_args[0][0] == "dim_event"
        assert len(call_args[1]["data"]) == 2

    def test_skips_s3_when_no_bucket(self) -> None:
        mock_ch = MagicMock()
        mock_catalog = MagicMock()
        mock_table = MagicMock()
        mock_catalog.load_table.return_value = mock_table
        mock_table.scan.return_value.to_arrow.return_value = _fake_silver_events()

        with patch(
            "prediction_data.gold.dimensions.write_gold_parquet"
        ) as mock_write:
            load_dim_event(
                gold_bucket=None,
                clickhouse_client=mock_ch,
                catalog=mock_catalog,
            )

        mock_write.assert_not_called()
        mock_ch.insert.assert_called_once()


# ---------------------------------------------------------------------------
# dim_category tests
# ---------------------------------------------------------------------------


class TestSilverEventsToDimCategory:
    def test_schema_matches(self) -> None:
        result = _silver_events_to_dim_category(_fake_silver_events(), "polymarket")
        assert result.schema.equals(DIM_CATEGORY_SCHEMA)

    def test_row_count_matches_distinct_categories(self) -> None:
        result = _silver_events_to_dim_category(_fake_silver_events(), "polymarket")
        # _fake_silver_events has categories: "politics", "sports" → 2 distinct
        assert result.num_rows == 2

    def test_platform_column(self) -> None:
        result = _silver_events_to_dim_category(_fake_silver_events(), "polymarket")
        assert all(p == "polymarket" for p in result.column("platform").to_pylist())

    def test_event_counts(self) -> None:
        result = _silver_events_to_dim_category(_fake_silver_events(), "polymarket")
        rows = {r["category"]: r for r in result.to_pylist()}
        assert rows["politics"]["event_count"] == 1
        assert rows["sports"]["event_count"] == 1

    def test_multiple_events_same_category(self) -> None:
        arrow = pa.table(
            {
                "event_ts": pa.array(
                    [1_700_000_000, 1_700_000_001, 1_700_000_002],
                    type=pa.timestamp("us", tz="UTC"),
                ),
                "platform_event_id": ["evt-1", "evt-2", "evt-3"],
                "title": ["A", "B", "C"],
                "description": ["a", "b", "c"],
                "slug": ["a", "b", "c"],
                "status": ["active", "active", "closed"],
                "category": ["politics", "politics", "sports"],
                "updated_at": pa.array(
                    [1_700_000_000, 1_700_000_001, 1_700_000_002],
                    type=pa.timestamp("us", tz="UTC"),
                ),
                "bronze_run_id": ["run1", "run2", "run3"],
                "silver_ingestion_ts": pa.array(
                    [1_700_000_000, 1_700_000_001, 1_700_000_002],
                    type=pa.timestamp("us", tz="UTC"),
                ),
                "tags": [["Politics"], ["Politics"], ["Sports"]],
            }
        )
        result = _silver_events_to_dim_category(arrow, "polymarket")
        rows = {r["category"]: r for r in result.to_pylist()}
        assert rows["politics"]["event_count"] == 2
        assert rows["sports"]["event_count"] == 1

    def test_dedup_before_counting(self) -> None:
        """Duplicate event IDs should be deduplicated before category counting."""
        arrow = pa.table(
            {
                "event_ts": pa.array(
                    [1_700_000_000, 1_700_000_001], type=pa.timestamp("us", tz="UTC")
                ),
                "platform_event_id": ["evt-1", "evt-1"],
                "title": ["Old", "New"],
                "description": ["old", "new"],
                "slug": ["old", "new"],
                "status": ["active", "closed"],
                "category": ["politics", "politics"],
                "updated_at": pa.array(
                    [1_700_000_000, 1_700_000_001], type=pa.timestamp("us", tz="UTC")
                ),
                "bronze_run_id": ["run1", "run2"],
                "silver_ingestion_ts": pa.array(
                    [1_700_000_000, 1_700_000_001], type=pa.timestamp("us", tz="UTC")
                ),
                "tags": [["Politics"], ["Politics"]],
            }
        )
        result = _silver_events_to_dim_category(arrow, "polymarket")
        rows = {r["category"]: r for r in result.to_pylist()}
        # Only 1 unique event, so count should be 1 not 2.
        assert rows["politics"]["event_count"] == 1

    def test_null_category_becomes_empty_string(self) -> None:
        arrow = pa.table(
            {
                "event_ts": pa.array(
                    [1_700_000_000], type=pa.timestamp("us", tz="UTC")
                ),
                "platform_event_id": ["evt-x"],
                "title": ["T"],
                "description": ["D"],
                "slug": ["s"],
                "status": ["active"],
                "category": [None],
                "updated_at": pa.array([None], type=pa.timestamp("us", tz="UTC")),
                "bronze_run_id": [None],
                "silver_ingestion_ts": pa.array(
                    [None], type=pa.timestamp("us", tz="UTC")
                ),
                "tags": [None],
            }
        )
        result = _silver_events_to_dim_category(arrow, "polymarket")
        assert result.num_rows == 1
        row = result.to_pylist()[0]
        assert row["category"] == ""
        assert row["event_count"] == 1

    def test_empty_events(self) -> None:
        empty = pa.table(
            {
                "event_ts": pa.array([], type=pa.timestamp("us", tz="UTC")),
                "platform_event_id": pa.array([], type=pa.string()),
                "title": pa.array([], type=pa.string()),
                "description": pa.array([], type=pa.string()),
                "slug": pa.array([], type=pa.string()),
                "status": pa.array([], type=pa.string()),
                "category": pa.array([], type=pa.string()),
                "updated_at": pa.array([], type=pa.timestamp("us", tz="UTC")),
                "bronze_run_id": pa.array([], type=pa.string()),
                "silver_ingestion_ts": pa.array([], type=pa.timestamp("us", tz="UTC")),
                "tags": pa.array([], type=pa.list_(pa.string())),
            }
        )
        result = _silver_events_to_dim_category(empty, "polymarket")
        assert result.num_rows == 0
        assert result.schema.equals(DIM_CATEGORY_SCHEMA)

    def test_categories_are_sorted(self) -> None:
        result = _silver_events_to_dim_category(_fake_silver_events(), "polymarket")
        categories = result.column("category").to_pylist()
        assert categories == sorted(categories)


class TestLoadDimCategory:
    def test_dry_run_returns_count(self) -> None:
        mock_catalog = MagicMock()
        mock_table = MagicMock()
        mock_catalog.load_table.return_value = mock_table
        mock_table.scan.return_value.to_arrow.return_value = _fake_silver_events()

        rows = load_dim_category(catalog=mock_catalog, dry_run=True)
        assert rows == 2  # 2 distinct categories

    def test_writes_to_s3_and_clickhouse(self, mock_s3_gold: MagicMock) -> None:
        mock_ch = MagicMock()
        mock_catalog = MagicMock()
        mock_table = MagicMock()
        mock_catalog.load_table.return_value = mock_table
        mock_table.scan.return_value.to_arrow.return_value = _fake_silver_events()

        with patch(
            "prediction_data.gold.dimensions.write_gold_parquet"
        ) as mock_write:
            rows = load_dim_category(
                gold_bucket="test-gold",
                s3_client=mock_s3_gold,
                clickhouse_client=mock_ch,
                catalog=mock_catalog,
            )

        assert rows == 2
        mock_write.assert_called_once()
        mock_ch.insert.assert_called_once()

        call_args = mock_ch.insert.call_args
        assert call_args[0][0] == "dim_category"
        assert len(call_args[1]["data"]) == 2

    def test_skips_s3_when_no_bucket(self) -> None:
        mock_ch = MagicMock()
        mock_catalog = MagicMock()
        mock_table = MagicMock()
        mock_catalog.load_table.return_value = mock_table
        mock_table.scan.return_value.to_arrow.return_value = _fake_silver_events()

        with patch(
            "prediction_data.gold.dimensions.write_gold_parquet"
        ) as mock_write:
            load_dim_category(
                gold_bucket=None,
                clickhouse_client=mock_ch,
                catalog=mock_catalog,
            )

        mock_write.assert_not_called()
        mock_ch.insert.assert_called_once()


# ---------------------------------------------------------------------------
# Integration tests: full pipeline Silver → S3 + ClickHouse for all dims
# ---------------------------------------------------------------------------


class TestFullPipelineAllDims:
    """Test loading all six dimension tables through a single pipeline run.

    Verifies that each loader reads Silver data, writes S3 Parquet, and
    inserts into ClickHouse with correct table names and row counts.
    """

    def _mock_catalog(self) -> MagicMock:
        """Return a catalog that serves markets for dim_market/dim_outcome,
        trades for dim_wallet, and events for dim_event."""
        catalog = MagicMock()

        def _load_table(identifier: tuple[str, str]) -> MagicMock:
            _ns, table_name = identifier
            tbl = MagicMock()
            if table_name == "markets":
                tbl.scan.return_value.to_arrow.return_value = (
                    _fake_silver_markets_with_tokens()
                )
            elif table_name == "trades":
                tbl.scan.return_value.to_arrow.return_value = _fake_silver_trades()
            elif table_name == "events":
                tbl.scan.return_value.to_arrow.return_value = _fake_silver_events()
            return tbl

        catalog.load_table.side_effect = _load_table
        return catalog

    def test_all_dims_write_to_s3_and_clickhouse(
        self, mock_s3_gold: MagicMock
    ) -> None:
        mock_ch = MagicMock()
        catalog = self._mock_catalog()

        with patch(
            "prediction_data.gold.dimensions.write_gold_parquet"
        ) as mock_write:
            p_rows = load_dim_platform(
                gold_bucket="test-gold",
                s3_client=mock_s3_gold,
                clickhouse_client=mock_ch,
            )
            m_rows = load_dim_market(
                gold_bucket="test-gold",
                s3_client=mock_s3_gold,
                clickhouse_client=mock_ch,
                catalog=catalog,
            )
            o_rows = load_dim_outcome(
                gold_bucket="test-gold",
                s3_client=mock_s3_gold,
                clickhouse_client=mock_ch,
                catalog=catalog,
            )
            w_rows = load_dim_wallet(
                gold_bucket="test-gold",
                s3_client=mock_s3_gold,
                clickhouse_client=mock_ch,
                catalog=catalog,
            )
            e_rows = load_dim_event(
                gold_bucket="test-gold",
                s3_client=mock_s3_gold,
                clickhouse_client=mock_ch,
                catalog=catalog,
            )
            c_rows = load_dim_category(
                gold_bucket="test-gold",
                s3_client=mock_s3_gold,
                clickhouse_client=mock_ch,
                catalog=catalog,
            )

        # All loaders returned rows.
        assert p_rows == len(PLATFORMS)
        assert m_rows == 2
        assert o_rows == 4
        assert w_rows == 3
        assert e_rows == 2
        assert c_rows == 2  # 2 distinct categories

        # S3 written for all six tables.
        assert mock_write.call_count == 6
        s3_table_names = [c.args[2] for c in mock_write.call_args_list]
        assert s3_table_names == [
            "dim_platform",
            "dim_market",
            "dim_outcome",
            "dim_wallet",
            "dim_event",
            "dim_category",
        ]

        # ClickHouse insert called for each table.
        assert mock_ch.insert.call_count == 6
        ch_table_names = [c.args[0] for c in mock_ch.insert.call_args_list]
        assert ch_table_names == [
            "dim_platform",
            "dim_market",
            "dim_outcome",
            "dim_wallet",
            "dim_event",
            "dim_category",
        ]

    def test_clickhouse_receives_correct_columns(
        self, mock_s3_gold: MagicMock
    ) -> None:
        """Verify that each ClickHouse insert passes the expected column names."""
        mock_ch = MagicMock()
        catalog = self._mock_catalog()

        with patch("prediction_data.gold.dimensions.write_gold_parquet"):
            load_dim_platform(
                gold_bucket="test-gold",
                s3_client=mock_s3_gold,
                clickhouse_client=mock_ch,
            )
            load_dim_market(
                gold_bucket="test-gold",
                s3_client=mock_s3_gold,
                clickhouse_client=mock_ch,
                catalog=catalog,
            )
            load_dim_outcome(
                gold_bucket="test-gold",
                s3_client=mock_s3_gold,
                clickhouse_client=mock_ch,
                catalog=catalog,
            )
            load_dim_wallet(
                gold_bucket="test-gold",
                s3_client=mock_s3_gold,
                clickhouse_client=mock_ch,
                catalog=catalog,
            )
            load_dim_event(
                gold_bucket="test-gold",
                s3_client=mock_s3_gold,
                clickhouse_client=mock_ch,
                catalog=catalog,
            )
            load_dim_category(
                gold_bucket="test-gold",
                s3_client=mock_s3_gold,
                clickhouse_client=mock_ch,
                catalog=catalog,
            )

        calls = mock_ch.insert.call_args_list
        # dim_platform
        assert calls[0][1]["column_names"] == ["platform_id", "platform_name", "url"]
        # dim_market
        assert calls[1][1]["column_names"] == DIM_MARKET_COLUMNS
        # dim_outcome
        assert calls[2][1]["column_names"] == DIM_OUTCOME_COLUMNS
        # dim_wallet
        assert calls[3][1]["column_names"] == DIM_WALLET_COLUMNS
        # dim_event
        assert calls[4][1]["column_names"] == DIM_EVENT_COLUMNS
        # dim_category
        assert calls[5][1]["column_names"] == DIM_CATEGORY_COLUMNS

    def test_clickhouse_data_is_queryable(self, mock_s3_gold: MagicMock) -> None:
        """Verify inserted data has correct structure for ClickHouse queries.

        Checks that each insert passes dicts/lists with the right keys and
        value types, simulating what ClickHouse would receive.
        """
        mock_ch = MagicMock()
        catalog = self._mock_catalog()

        with patch("prediction_data.gold.dimensions.write_gold_parquet"):
            load_dim_platform(
                gold_bucket="test-gold",
                s3_client=mock_s3_gold,
                clickhouse_client=mock_ch,
            )
            load_dim_market(
                gold_bucket="test-gold",
                s3_client=mock_s3_gold,
                clickhouse_client=mock_ch,
                catalog=catalog,
            )
            load_dim_outcome(
                gold_bucket="test-gold",
                s3_client=mock_s3_gold,
                clickhouse_client=mock_ch,
                catalog=catalog,
            )
            load_dim_wallet(
                gold_bucket="test-gold",
                s3_client=mock_s3_gold,
                clickhouse_client=mock_ch,
                catalog=catalog,
            )
            load_dim_event(
                gold_bucket="test-gold",
                s3_client=mock_s3_gold,
                clickhouse_client=mock_ch,
                catalog=catalog,
            )
            load_dim_category(
                gold_bucket="test-gold",
                s3_client=mock_s3_gold,
                clickhouse_client=mock_ch,
                catalog=catalog,
            )

        calls = mock_ch.insert.call_args_list

        # dim_platform: list of lists
        platform_data = calls[0][1]["data"]
        assert len(platform_data) == 2
        assert platform_data[0] == ["polymarket", "Polymarket", "https://polymarket.com"]

        # dim_market: list of dicts with all expected keys
        market_data = calls[1][1]["data"]
        assert len(market_data) == 2
        for row in market_data:
            assert set(row.keys()) == set(DIM_MARKET_COLUMNS)
            assert isinstance(row["platform"], str)
            assert isinstance(row["platform_market_id"], str)

        # dim_outcome: list of dicts with all expected keys
        outcome_data = calls[2][1]["data"]
        assert len(outcome_data) == 4
        for row in outcome_data:
            assert set(row.keys()) == set(DIM_OUTCOME_COLUMNS)
            assert row["side"] in ("token1", "token2")

        # dim_wallet: list of dicts with all expected keys
        wallet_data = calls[3][1]["data"]
        assert len(wallet_data) == 3
        for row in wallet_data:
            assert set(row.keys()) == set(DIM_WALLET_COLUMNS)
            assert isinstance(row["trade_count"], int)

        # dim_event: list of dicts with all expected keys
        event_data = calls[4][1]["data"]
        assert len(event_data) == 2
        for row in event_data:
            assert set(row.keys()) == set(DIM_EVENT_COLUMNS)
            assert isinstance(row["platform"], str)
            assert isinstance(row["category"], str)

        # dim_category: list of dicts with all expected keys
        category_data = calls[5][1]["data"]
        assert len(category_data) == 2
        for row in category_data:
            assert set(row.keys()) == set(DIM_CATEGORY_COLUMNS)
            assert isinstance(row["category"], str)
            assert isinstance(row["event_count"], int)


# ---------------------------------------------------------------------------
# CLI integration tests
# ---------------------------------------------------------------------------


class TestLoadDimsCLI:
    """Test the `prediction-data gold load-dims` CLI command."""

    def _mock_catalog(self) -> MagicMock:
        catalog = MagicMock()

        def _load_table(identifier: tuple[str, str]) -> MagicMock:
            _ns, table_name = identifier
            tbl = MagicMock()
            if table_name == "markets":
                tbl.scan.return_value.to_arrow.return_value = (
                    _fake_silver_markets_with_tokens()
                )
            elif table_name == "trades":
                tbl.scan.return_value.to_arrow.return_value = _fake_silver_trades()
            elif table_name == "events":
                tbl.scan.return_value.to_arrow.return_value = _fake_silver_events()
            return tbl

        catalog.load_table.side_effect = _load_table
        return catalog

    def test_load_single_table_dry_run(self) -> None:
        from typer.testing import CliRunner

        from prediction_data.cli.main import app as cli_app

        runner = CliRunner()
        result = runner.invoke(cli_app, ["gold", "load-dims", "--table", "dim_platform", "--dry-run"])
        assert result.exit_code == 0
        assert "dim_platform" in result.output
        assert "2 rows loaded" in result.output

    def test_load_all_tables_dry_run(self) -> None:
        from typer.testing import CliRunner

        from prediction_data.cli.main import app as cli_app

        runner = CliRunner()

        with (
            patch("prediction_data.gold.dimensions._read_silver_markets") as mock_markets,
            patch("prediction_data.gold.dimensions._read_silver_trades") as mock_trades,
            patch("prediction_data.gold.dimensions._read_silver_events") as mock_events,
        ):
            mock_markets.return_value = _fake_silver_markets_with_tokens()
            mock_trades.return_value = _fake_silver_trades()
            mock_events.return_value = _fake_silver_events()
            result = runner.invoke(cli_app, ["gold", "load-dims", "--dry-run"])

        assert result.exit_code == 0
        assert "dim_platform" in result.output
        assert "dim_market" in result.output
        assert "dim_outcome" in result.output
        assert "dim_wallet" in result.output
        assert "dim_event" in result.output
        assert "dim_category" in result.output

    def test_unknown_table_fails(self) -> None:
        from typer.testing import CliRunner

        from prediction_data.cli.main import app as cli_app

        runner = CliRunner()
        result = runner.invoke(cli_app, ["gold", "load-dims", "--table", "dim_bogus"])
        assert result.exit_code != 0
        assert "Unknown dimension table" in result.output


# ---------------------------------------------------------------------------
# Streaming dimension loader tests
# ---------------------------------------------------------------------------


def _make_batch_reader(table: pa.Table, batch_size: int = 2):
    """Create a mock batch reader that yields batches from an Arrow table."""
    for i in range(0, table.num_rows, batch_size):
        end = min(i + batch_size, table.num_rows)
        if end - i > 0:
            yield table.slice(i, end - i).to_batches()[0]


class TestLoadDimMarketStreaming:
    """Tests for load_dim_market_streaming."""

    def test_dry_run_returns_count(self) -> None:
        from prediction_data.gold.dimensions import load_dim_market_streaming

        mock_catalog = MagicMock()
        mock_table = MagicMock()
        mock_catalog.load_table.return_value = mock_table
        silver = _fake_silver_markets()
        mock_table.scan.return_value.to_arrow_batch_reader.return_value = _make_batch_reader(
            silver
        )

        rows = load_dim_market_streaming(catalog=mock_catalog, dry_run=True)
        assert rows == 2

    def test_writes_to_clickhouse(self) -> None:
        from prediction_data.gold.dimensions import load_dim_market_streaming

        mock_ch = MagicMock()
        mock_catalog = MagicMock()
        mock_table = MagicMock()
        mock_catalog.load_table.return_value = mock_table
        silver = _fake_silver_markets()
        mock_table.scan.return_value.to_arrow_batch_reader.return_value = _make_batch_reader(
            silver
        )

        rows = load_dim_market_streaming(
            clickhouse_client=mock_ch,
            catalog=mock_catalog,
        )

        assert rows == 2
        assert mock_ch.insert.called
        call_args = mock_ch.insert.call_args
        assert call_args[0][0] == "dim_market"

    def test_deduplication_across_batches(self) -> None:
        """Duplicate market IDs across batches should be deduplicated."""
        from prediction_data.gold.dimensions import load_dim_market_streaming

        # Create table with duplicate market IDs
        silver = pa.table(
            {
                "event_ts": pa.array(
                    [1_700_000_000, 1_700_000_001, 1_700_000_002],
                    type=pa.timestamp("us", tz="UTC"),
                ),
                "platform_market_id": ["mkt-1", "mkt-2", "mkt-1"],  # mkt-1 appears twice
                "question": ["Q1", "Q2", "Q1-updated"],
                "description": ["D1", "D2", "D1-updated"],
                "market_slug": ["q1", "q2", "q1"],
                "status": ["active", "active", "closed"],
                "outcome": ["", "", ""],
                "tokens": ['[{"id":"t1"}]', '[{"id":"t2"}]', '[{"id":"t1"}]'],
                "event_id": ["evt-1", "evt-2", "evt-1"],
                "updated_at": pa.array(
                    [1_700_000_000, 1_700_000_001, 1_700_000_002],
                    type=pa.timestamp("us", tz="UTC"),
                ),
                "bronze_run_id": ["run1", "run2", "run3"],
                "silver_ingestion_ts": pa.array(
                    [1_700_000_000, 1_700_000_001, 1_700_000_002],
                    type=pa.timestamp("us", tz="UTC"),
                ),
            }
        )

        mock_ch = MagicMock()
        mock_catalog = MagicMock()
        mock_table = MagicMock()
        mock_catalog.load_table.return_value = mock_table
        # Use batch_size=1 to force multiple batches
        mock_table.scan.return_value.to_arrow_batch_reader.return_value = _make_batch_reader(
            silver, batch_size=1
        )

        rows = load_dim_market_streaming(
            clickhouse_client=mock_ch,
            catalog=mock_catalog,
        )

        # Should only have 2 unique markets (mkt-1 deduplicated)
        assert rows == 2

    def test_skips_s3_with_warning(self, mock_s3_gold: MagicMock, caplog) -> None:
        """Streaming mode should skip S3 write and log a warning."""
        import logging

        from prediction_data.gold.dimensions import load_dim_market_streaming

        mock_ch = MagicMock()
        mock_catalog = MagicMock()
        mock_table = MagicMock()
        mock_catalog.load_table.return_value = mock_table
        silver = _fake_silver_markets()
        mock_table.scan.return_value.to_arrow_batch_reader.return_value = _make_batch_reader(
            silver
        )

        with caplog.at_level(logging.WARNING):
            load_dim_market_streaming(
                gold_bucket="test-gold",
                s3_client=mock_s3_gold,
                clickhouse_client=mock_ch,
                catalog=mock_catalog,
            )

        # S3 write should be skipped (no call to write_gold_parquet)
        with patch("prediction_data.gold.dimensions.write_gold_parquet") as mock_write:
            load_dim_market_streaming(
                gold_bucket="test-gold",
                s3_client=mock_s3_gold,
                clickhouse_client=mock_ch,
                catalog=mock_catalog,
            )
            mock_write.assert_not_called()


class TestLoadDimOutcomeStreaming:
    """Tests for load_dim_outcome_streaming."""

    def test_dry_run_returns_count(self) -> None:
        from prediction_data.gold.dimensions import load_dim_outcome_streaming

        mock_catalog = MagicMock()
        mock_table = MagicMock()
        mock_catalog.load_table.return_value = mock_table
        silver = _fake_silver_markets_with_tokens()
        mock_table.scan.return_value.to_arrow_batch_reader.return_value = _make_batch_reader(
            silver
        )

        rows = load_dim_outcome_streaming(catalog=mock_catalog, dry_run=True)
        assert rows == 4  # 2 markets × 2 tokens each

    def test_writes_to_clickhouse(self) -> None:
        from prediction_data.gold.dimensions import load_dim_outcome_streaming

        mock_ch = MagicMock()
        mock_catalog = MagicMock()
        mock_table = MagicMock()
        mock_catalog.load_table.return_value = mock_table
        silver = _fake_silver_markets_with_tokens()
        mock_table.scan.return_value.to_arrow_batch_reader.return_value = _make_batch_reader(
            silver
        )

        rows = load_dim_outcome_streaming(
            clickhouse_client=mock_ch,
            catalog=mock_catalog,
        )

        assert rows == 4
        assert mock_ch.insert.called
        call_args = mock_ch.insert.call_args
        assert call_args[0][0] == "dim_outcome"

    def test_deduplication_by_market_id(self) -> None:
        """Duplicate market IDs should produce outcomes only once."""
        from prediction_data.gold.dimensions import load_dim_outcome_streaming

        # Create table with duplicate market IDs
        silver = pa.table(
            {
                "event_ts": pa.array(
                    [1_700_000_000, 1_700_000_001],
                    type=pa.timestamp("us", tz="UTC"),
                ),
                "platform_market_id": ["mkt-1", "mkt-1"],  # duplicate
                "question": ["Q1", "Q1-updated"],
                "description": ["D1", "D1-updated"],
                "market_slug": ["q1", "q1"],
                "status": ["active", "closed"],
                "outcome": ["", ""],
                "tokens": [
                    '[{"token_id":"tok-1a","outcome":"Yes"},{"token_id":"tok-1b","outcome":"No"}]',
                    '[{"token_id":"tok-1a","outcome":"Yes"},{"token_id":"tok-1b","outcome":"No"}]',
                ],
                "event_id": ["evt-1", "evt-1"],
                "updated_at": pa.array(
                    [1_700_000_000, 1_700_000_001],
                    type=pa.timestamp("us", tz="UTC"),
                ),
                "bronze_run_id": ["run1", "run2"],
                "silver_ingestion_ts": pa.array(
                    [1_700_000_000, 1_700_000_001],
                    type=pa.timestamp("us", tz="UTC"),
                ),
            }
        )

        mock_ch = MagicMock()
        mock_catalog = MagicMock()
        mock_table = MagicMock()
        mock_catalog.load_table.return_value = mock_table
        mock_table.scan.return_value.to_arrow_batch_reader.return_value = _make_batch_reader(
            silver
        )

        rows = load_dim_outcome_streaming(
            clickhouse_client=mock_ch,
            catalog=mock_catalog,
        )

        # Should only have 2 outcomes (from 1 unique market)
        assert rows == 2


class TestLoadDimWalletStreaming:
    """Tests for load_dim_wallet_streaming."""

    def test_dry_run_returns_count(self) -> None:
        from prediction_data.gold.dimensions import load_dim_wallet_streaming

        mock_catalog = MagicMock()
        mock_table = MagicMock()
        mock_catalog.load_table.return_value = mock_table
        silver = _fake_silver_trades()
        mock_table.scan.return_value.to_arrow_batch_reader.return_value = _make_batch_reader(
            silver
        )

        rows = load_dim_wallet_streaming(catalog=mock_catalog, dry_run=True)
        assert rows == 3  # 3 unique wallets

    def test_writes_to_clickhouse(self) -> None:
        from prediction_data.gold.dimensions import load_dim_wallet_streaming

        mock_ch = MagicMock()
        mock_catalog = MagicMock()
        mock_table = MagicMock()
        mock_catalog.load_table.return_value = mock_table
        silver = _fake_silver_trades()
        mock_table.scan.return_value.to_arrow_batch_reader.return_value = _make_batch_reader(
            silver
        )

        rows = load_dim_wallet_streaming(
            clickhouse_client=mock_ch,
            catalog=mock_catalog,
        )

        assert rows == 3
        assert mock_ch.insert.called
        call_args = mock_ch.insert.call_args
        assert call_args[0][0] == "dim_wallet"

    def test_aggregation_across_batches(self) -> None:
        """Wallet stats should be aggregated correctly across batches."""
        from prediction_data.gold.dimensions import load_dim_wallet_streaming

        mock_ch = MagicMock()
        mock_catalog = MagicMock()
        mock_table = MagicMock()
        mock_catalog.load_table.return_value = mock_table
        silver = _fake_silver_trades()
        # Use batch_size=1 to force each trade into its own batch
        mock_table.scan.return_value.to_arrow_batch_reader.return_value = _make_batch_reader(
            silver, batch_size=1
        )

        rows = load_dim_wallet_streaming(
            clickhouse_client=mock_ch,
            catalog=mock_catalog,
        )

        assert rows == 3  # 3 unique wallets

        # Verify trade counts are correct (check the data inserted)
        insert_calls = mock_ch.insert.call_args_list
        assert len(insert_calls) >= 1
        # The last call should contain all wallets
        data = insert_calls[-1][1]["data"]
        wallet_data = {row[1]: row[4] for row in data}  # wallet_address: trade_count
        assert wallet_data["wallet-a"] == 3  # maker in t1, taker in t2, maker in t3
        assert wallet_data["wallet-b"] == 2  # taker in t1, maker in t2
        assert wallet_data["wallet-c"] == 1  # taker in t3


class TestLoadDimEventStreaming:
    """Tests for load_dim_event_streaming."""

    def test_dry_run_returns_count(self) -> None:
        from prediction_data.gold.dimensions import load_dim_event_streaming

        mock_catalog = MagicMock()
        mock_table = MagicMock()
        mock_catalog.load_table.return_value = mock_table
        silver = _fake_silver_events()
        mock_table.scan.return_value.to_arrow_batch_reader.return_value = _make_batch_reader(
            silver
        )

        rows = load_dim_event_streaming(catalog=mock_catalog, dry_run=True)
        assert rows == 2

    def test_writes_to_clickhouse(self) -> None:
        from prediction_data.gold.dimensions import load_dim_event_streaming

        mock_ch = MagicMock()
        mock_catalog = MagicMock()
        mock_table = MagicMock()
        mock_catalog.load_table.return_value = mock_table
        silver = _fake_silver_events()
        mock_table.scan.return_value.to_arrow_batch_reader.return_value = _make_batch_reader(
            silver
        )

        rows = load_dim_event_streaming(
            clickhouse_client=mock_ch,
            catalog=mock_catalog,
        )

        assert rows == 2
        assert mock_ch.insert.called
        call_args = mock_ch.insert.call_args
        assert call_args[0][0] == "dim_event"

    def test_deduplication_across_batches(self) -> None:
        """Duplicate event IDs across batches should be deduplicated."""
        from prediction_data.gold.dimensions import load_dim_event_streaming

        silver = pa.table(
            {
                "event_ts": pa.array(
                    [1_700_000_000, 1_700_000_001],
                    type=pa.timestamp("us", tz="UTC"),
                ),
                "platform_event_id": ["evt-1", "evt-1"],  # duplicate
                "title": ["Old Title", "New Title"],
                "description": ["Old", "New"],
                "slug": ["old-slug", "new-slug"],
                "status": ["active", "closed"],
                "category": ["politics", "politics"],
                "updated_at": pa.array(
                    [1_700_000_000, 1_700_000_001],
                    type=pa.timestamp("us", tz="UTC"),
                ),
                "bronze_run_id": ["run1", "run2"],
                "silver_ingestion_ts": pa.array(
                    [1_700_000_000, 1_700_000_001],
                    type=pa.timestamp("us", tz="UTC"),
                ),
                "tags": [["Politics"], ["Politics", "Elections"]],
            }
        )

        mock_ch = MagicMock()
        mock_catalog = MagicMock()
        mock_table = MagicMock()
        mock_catalog.load_table.return_value = mock_table
        mock_table.scan.return_value.to_arrow_batch_reader.return_value = _make_batch_reader(
            silver, batch_size=1
        )

        rows = load_dim_event_streaming(
            clickhouse_client=mock_ch,
            catalog=mock_catalog,
        )

        # Should only have 1 unique event
        assert rows == 1


class TestLoadDimCategoryStreaming:
    """Tests for load_dim_category_streaming."""

    def test_dry_run_returns_count(self) -> None:
        from prediction_data.gold.dimensions import load_dim_category_streaming

        mock_catalog = MagicMock()
        mock_table = MagicMock()
        mock_catalog.load_table.return_value = mock_table
        silver = _fake_silver_events()
        mock_table.scan.return_value.to_arrow_batch_reader.return_value = _make_batch_reader(
            silver
        )

        rows = load_dim_category_streaming(catalog=mock_catalog, dry_run=True)
        assert rows == 2  # 2 distinct categories

    def test_writes_to_clickhouse(self) -> None:
        from prediction_data.gold.dimensions import load_dim_category_streaming

        mock_ch = MagicMock()
        mock_catalog = MagicMock()
        mock_table = MagicMock()
        mock_catalog.load_table.return_value = mock_table
        silver = _fake_silver_events()
        mock_table.scan.return_value.to_arrow_batch_reader.return_value = _make_batch_reader(
            silver
        )

        rows = load_dim_category_streaming(
            clickhouse_client=mock_ch,
            catalog=mock_catalog,
        )

        assert rows == 2
        assert mock_ch.insert.called
        call_args = mock_ch.insert.call_args
        assert call_args[0][0] == "dim_category"

    def test_category_counts_across_batches(self) -> None:
        """Category counts should be accumulated correctly across batches."""
        from prediction_data.gold.dimensions import load_dim_category_streaming

        silver = pa.table(
            {
                "event_ts": pa.array(
                    [1_700_000_000, 1_700_000_001, 1_700_000_002],
                    type=pa.timestamp("us", tz="UTC"),
                ),
                "platform_event_id": ["evt-1", "evt-2", "evt-3"],
                "title": ["A", "B", "C"],
                "description": ["a", "b", "c"],
                "slug": ["a", "b", "c"],
                "status": ["active", "active", "closed"],
                "category": ["politics", "politics", "sports"],
                "updated_at": pa.array(
                    [1_700_000_000, 1_700_000_001, 1_700_000_002],
                    type=pa.timestamp("us", tz="UTC"),
                ),
                "bronze_run_id": ["run1", "run2", "run3"],
                "silver_ingestion_ts": pa.array(
                    [1_700_000_000, 1_700_000_001, 1_700_000_002],
                    type=pa.timestamp("us", tz="UTC"),
                ),
                "tags": [["Politics"], ["Politics"], ["Sports"]],
            }
        )

        mock_ch = MagicMock()
        mock_catalog = MagicMock()
        mock_table = MagicMock()
        mock_catalog.load_table.return_value = mock_table
        mock_table.scan.return_value.to_arrow_batch_reader.return_value = _make_batch_reader(
            silver, batch_size=1
        )

        rows = load_dim_category_streaming(
            clickhouse_client=mock_ch,
            catalog=mock_catalog,
        )

        assert rows == 2  # politics, sports

        # Verify counts
        data = mock_ch.insert.call_args[1]["data"]
        category_counts = {row[1]: row[2] for row in data}  # category: count
        assert category_counts["politics"] == 2
        assert category_counts["sports"] == 1

    def test_deduplication_before_counting(self) -> None:
        """Duplicate events should be deduplicated before category counting."""
        from prediction_data.gold.dimensions import load_dim_category_streaming

        silver = pa.table(
            {
                "event_ts": pa.array(
                    [1_700_000_000, 1_700_000_001],
                    type=pa.timestamp("us", tz="UTC"),
                ),
                "platform_event_id": ["evt-1", "evt-1"],  # duplicate
                "title": ["Old", "New"],
                "description": ["old", "new"],
                "slug": ["old", "new"],
                "status": ["active", "closed"],
                "category": ["politics", "politics"],
                "updated_at": pa.array(
                    [1_700_000_000, 1_700_000_001],
                    type=pa.timestamp("us", tz="UTC"),
                ),
                "bronze_run_id": ["run1", "run2"],
                "silver_ingestion_ts": pa.array(
                    [1_700_000_000, 1_700_000_001],
                    type=pa.timestamp("us", tz="UTC"),
                ),
                "tags": [["Politics"], ["Politics"]],
            }
        )

        mock_ch = MagicMock()
        mock_catalog = MagicMock()
        mock_table = MagicMock()
        mock_catalog.load_table.return_value = mock_table
        mock_table.scan.return_value.to_arrow_batch_reader.return_value = _make_batch_reader(
            silver
        )

        rows = load_dim_category_streaming(
            clickhouse_client=mock_ch,
            catalog=mock_catalog,
        )

        # Only 1 unique event, so count should be 1 not 2
        data = mock_ch.insert.call_args[1]["data"]
        category_counts = {row[1]: row[2] for row in data}
        assert category_counts["politics"] == 1


class TestStreamingVsNonStreamingParity:
    """Verify streaming loaders produce same results as non-streaming loaders."""

    def _mock_catalog(self, silver_markets, silver_trades, silver_events) -> MagicMock:
        """Return a catalog that serves the provided Silver data."""
        catalog = MagicMock()

        def _load_table(identifier: tuple[str, str]) -> MagicMock:
            _ns, table_name = identifier
            tbl = MagicMock()
            if table_name == "markets":
                tbl.scan.return_value.to_arrow.return_value = silver_markets
                tbl.scan.return_value.to_arrow_batch_reader.return_value = _make_batch_reader(
                    silver_markets
                )
            elif table_name == "trades":
                tbl.scan.return_value.to_arrow.return_value = silver_trades
                tbl.scan.return_value.to_arrow_batch_reader.return_value = _make_batch_reader(
                    silver_trades
                )
            elif table_name == "events":
                tbl.scan.return_value.to_arrow.return_value = silver_events
                tbl.scan.return_value.to_arrow_batch_reader.return_value = _make_batch_reader(
                    silver_events
                )
            return tbl

        catalog.load_table.side_effect = _load_table
        return catalog

    def test_market_row_count_parity(self) -> None:
        """Streaming and non-streaming should produce same row count for markets."""
        from prediction_data.gold.dimensions import (
            load_dim_market,
            load_dim_market_streaming,
        )

        silver = _fake_silver_markets()
        catalog = self._mock_catalog(silver, _fake_silver_trades(), _fake_silver_events())

        non_streaming_rows = load_dim_market(catalog=catalog, dry_run=True)

        # Reset catalog for streaming
        catalog = self._mock_catalog(silver, _fake_silver_trades(), _fake_silver_events())
        streaming_rows = load_dim_market_streaming(catalog=catalog, dry_run=True)

        assert non_streaming_rows == streaming_rows

    def test_outcome_row_count_parity(self) -> None:
        """Streaming and non-streaming should produce same row count for outcomes."""
        from prediction_data.gold.dimensions import (
            load_dim_outcome,
            load_dim_outcome_streaming,
        )

        silver = _fake_silver_markets_with_tokens()
        catalog = self._mock_catalog(silver, _fake_silver_trades(), _fake_silver_events())

        non_streaming_rows = load_dim_outcome(catalog=catalog, dry_run=True)

        catalog = self._mock_catalog(silver, _fake_silver_trades(), _fake_silver_events())
        streaming_rows = load_dim_outcome_streaming(catalog=catalog, dry_run=True)

        assert non_streaming_rows == streaming_rows

    def test_wallet_row_count_parity(self) -> None:
        """Streaming and non-streaming should produce same row count for wallets."""
        from prediction_data.gold.dimensions import (
            load_dim_wallet,
            load_dim_wallet_streaming,
        )

        silver = _fake_silver_trades()
        catalog = self._mock_catalog(_fake_silver_markets(), silver, _fake_silver_events())

        non_streaming_rows = load_dim_wallet(catalog=catalog, dry_run=True)

        catalog = self._mock_catalog(_fake_silver_markets(), silver, _fake_silver_events())
        streaming_rows = load_dim_wallet_streaming(catalog=catalog, dry_run=True)

        assert non_streaming_rows == streaming_rows

    def test_event_row_count_parity(self) -> None:
        """Streaming and non-streaming should produce same row count for events."""
        from prediction_data.gold.dimensions import (
            load_dim_event,
            load_dim_event_streaming,
        )

        silver = _fake_silver_events()
        catalog = self._mock_catalog(_fake_silver_markets(), _fake_silver_trades(), silver)

        non_streaming_rows = load_dim_event(catalog=catalog, dry_run=True)

        catalog = self._mock_catalog(_fake_silver_markets(), _fake_silver_trades(), silver)
        streaming_rows = load_dim_event_streaming(catalog=catalog, dry_run=True)

        assert non_streaming_rows == streaming_rows

    def test_category_row_count_parity(self) -> None:
        """Streaming and non-streaming should produce same row count for categories."""
        from prediction_data.gold.dimensions import (
            load_dim_category,
            load_dim_category_streaming,
        )

        silver = _fake_silver_events()
        catalog = self._mock_catalog(_fake_silver_markets(), _fake_silver_trades(), silver)

        non_streaming_rows = load_dim_category(catalog=catalog, dry_run=True)

        catalog = self._mock_catalog(_fake_silver_markets(), _fake_silver_trades(), silver)
        streaming_rows = load_dim_category_streaming(catalog=catalog, dry_run=True)

        assert non_streaming_rows == streaming_rows
