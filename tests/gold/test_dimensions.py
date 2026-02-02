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
    DIM_WALLET_COLUMNS,
    DIM_WALLET_SCHEMA,
    PLATFORMS,
    _platforms_to_arrow,
    _silver_to_dim_market,
    _silver_to_dim_outcome,
    _silver_trades_to_dim_wallet,
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
# Integration tests: full pipeline Silver → S3 + ClickHouse for all dims
# ---------------------------------------------------------------------------


class TestFullPipelineAllDims:
    """Test loading all four dimension tables through a single pipeline run.

    Verifies that each loader reads Silver data, writes S3 Parquet, and
    inserts into ClickHouse with correct table names and row counts.
    """

    def _mock_catalog(self) -> MagicMock:
        """Return a catalog that serves markets for dim_market/dim_outcome
        and trades for dim_wallet."""
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

        # All loaders returned rows.
        assert p_rows == len(PLATFORMS)
        assert m_rows == 2
        assert o_rows == 4
        assert w_rows == 3

        # S3 written for all four tables.
        assert mock_write.call_count == 4
        s3_table_names = [c.args[2] for c in mock_write.call_args_list]
        assert s3_table_names == [
            "dim_platform",
            "dim_market",
            "dim_outcome",
            "dim_wallet",
        ]

        # ClickHouse insert called for each table.
        assert mock_ch.insert.call_count == 4
        ch_table_names = [c.args[0] for c in mock_ch.insert.call_args_list]
        assert ch_table_names == [
            "dim_platform",
            "dim_market",
            "dim_outcome",
            "dim_wallet",
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

        calls = mock_ch.insert.call_args_list
        # dim_platform
        assert calls[0][1]["column_names"] == ["platform_id", "platform_name", "url"]
        # dim_market
        assert calls[1][1]["column_names"] == DIM_MARKET_COLUMNS
        # dim_outcome
        assert calls[2][1]["column_names"] == DIM_OUTCOME_COLUMNS
        # dim_wallet
        assert calls[3][1]["column_names"] == DIM_WALLET_COLUMNS

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
        catalog = self._mock_catalog()

        with (
            patch("prediction_data.gold.dimensions._read_silver_markets") as mock_markets,
            patch("prediction_data.gold.dimensions._read_silver_trades") as mock_trades,
        ):
            mock_markets.return_value = _fake_silver_markets_with_tokens()
            mock_trades.return_value = _fake_silver_trades()
            result = runner.invoke(cli_app, ["gold", "load-dims", "--dry-run"])

        assert result.exit_code == 0
        assert "dim_platform" in result.output
        assert "dim_market" in result.output
        assert "dim_outcome" in result.output
        assert "dim_wallet" in result.output

    def test_unknown_table_fails(self) -> None:
        from typer.testing import CliRunner

        from prediction_data.cli.main import app as cli_app

        runner = CliRunner()
        result = runner.invoke(cli_app, ["gold", "load-dims", "--table", "dim_bogus"])
        assert result.exit_code != 0
        assert "Unknown dimension table" in result.output
