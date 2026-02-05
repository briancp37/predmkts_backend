"""Data Quality Validation Tests for Gold Layer.

Tests that verify data quality constraints across all Gold tables.
These tests validate primary key integrity, business logic constraints,
price bounds, and Parquet schema conformance.

PRD Reference: plans/release/03_gold_level/sprint/09_validation_and_delivery/prd.json
Category: data_quality_validation
"""

from __future__ import annotations

from datetime import UTC, date, datetime

import pyarrow as pa
import pytest

from prediction_data.gold.accounting import PositionState
from prediction_data.gold.fill_splitter import Fill
from prediction_data.gold.ledger import LEDGER_SCHEMA, LedgerWriter, build_ledger_for_day
from prediction_data.gold.market_marks import (
    MARKET_MARK_DAILY_SCHEMA,
    compute_marks_for_day,
)
from prediction_data.gold.position_state import (
    POSITION_STATE_SCHEMA,
    positions_to_arrow,
)
from prediction_data.gold.wallet_pnl import (
    WALLET_PNL_DAILY_SCHEMA,
    aggregate_pnl_for_day,
)


def _ts(minute: int = 0) -> datetime:
    """Helper to create test timestamps."""
    return datetime(2024, 6, 15, 12, minute, 0, tzinfo=UTC)


def _fill(
    *,
    ts: datetime | None = None,
    wallet: str = "0xTEST",
    platform: str = "polymarket",
    market_id: str = "MKT1",
    outcome_id: str = "MKT1_0",
    side: str = "buy",
    qty_delta: float = 100.0,
    price: float = 0.50,
    fees_usd: float = 0.0,
) -> Fill:
    """Helper to create a Fill."""
    return Fill(
        ts=ts or _ts(),
        wallet=wallet,
        platform=platform,
        market_id=market_id,
        outcome_id=outcome_id,
        side=side,
        qty_delta=qty_delta,
        price=price,
        fees_usd=fees_usd,
    )


# =============================================================================
# PRIMARY KEY VALIDATION TESTS
# =============================================================================


class TestNoPrimaryKeysNull:
    """Verify no null primary keys in any Gold table.

    Primary keys for each Gold table:
    - wallet_position_state: (wallet, platform, market_id, outcome_id)
    - wallet_position_ledger: (ts, wallet, platform, market_id, outcome_id)
    - market_mark_daily: (platform, market_id, outcome_id, day_utc)
    - wallet_pnl_daily: (day_utc, wallet)
    """

    def test_position_state_no_null_primary_keys(self) -> None:
        """wallet_position_state: all primary key fields are non-null."""
        pos = PositionState(
            wallet="0xTEST",
            platform="polymarket",
            market_id="MKT1",
            outcome_id="MKT1_0",
        )
        pos.apply_fill("buy", 100.0, 0.50, 0.0, _ts(0))

        positions = {("0xTEST", "polymarket", "MKT1", "MKT1_0"): pos}
        table = positions_to_arrow(positions)

        # Verify primary key columns have no nulls
        assert table.num_rows == 1
        for pk_col in ["wallet", "platform", "market_id", "outcome_id"]:
            col = table.column(pk_col)
            assert col.null_count == 0, f"{pk_col} should have no nulls"
            # Also verify the values are non-empty strings
            for val in col.to_pylist():
                assert val is not None and val != "", f"{pk_col} should be non-empty"

    def test_ledger_no_null_primary_keys(self) -> None:
        """wallet_position_ledger: all primary key fields are non-null."""
        fills = [
            _fill(ts=_ts(0), side="buy", qty_delta=100.0, price=0.50),
            _fill(ts=_ts(1), side="sell", qty_delta=100.0, price=0.70),
        ]
        writer, _ = build_ledger_for_day(fills, {})
        table = writer.to_arrow()

        # Verify primary key columns have no nulls
        assert table.num_rows == 2
        for pk_col in ["ts", "wallet", "platform", "market_id", "outcome_id"]:
            col = table.column(pk_col)
            assert col.null_count == 0, f"{pk_col} should have no nulls"

    def test_market_mark_daily_no_null_primary_keys(self) -> None:
        """market_mark_daily: all primary key fields are non-null."""
        trades = [
            {
                "platform_market_id": "MKT1",
                "nonusdc_side": "MKT1_0",
                "price": 0.50,
                "usd_amount": 100.0,
                "event_ts": _ts(0),
                "maker": "0xMAKER",
                "taker": "0xTAKER",
            },
        ]
        table = compute_marks_for_day(trades, "polymarket", date(2024, 6, 15))

        # Verify primary key columns have no nulls
        assert table.num_rows == 1
        for pk_col in ["platform", "market_id", "outcome_id", "day_utc"]:
            col = table.column(pk_col)
            assert col.null_count == 0, f"{pk_col} should have no nulls"

    def test_wallet_pnl_daily_no_null_primary_keys(self) -> None:
        """wallet_pnl_daily: all primary key fields are non-null."""
        ledger_rows = [
            {
                "wallet": "0xTEST",
                "qty_delta": 100.0,
                "price": 0.50,
                "fees_usd": 0.0,
                "realized_pnl_this_fill_usd": 0.0,
            },
        ]
        table = aggregate_pnl_for_day(ledger_rows, date(2024, 6, 15))

        # Verify primary key columns have no nulls
        assert table.num_rows == 1
        for pk_col in ["day_utc", "wallet"]:
            col = table.column(pk_col)
            assert col.null_count == 0, f"{pk_col} should have no nulls"


class TestPositionStateNoZeroQty:
    """Verify wallet_position_state has no rows with qty = 0.

    When querying open positions, only rows with qty != 0 should be returned.
    The positions_to_arrow function includes closed positions (qty=0) for
    ReplacingMergeTree collapse, but downstream queries filter them out.
    """

    def test_open_positions_have_nonzero_qty(self) -> None:
        """Open positions must have qty != 0."""
        pos = PositionState(
            wallet="0xTEST",
            platform="polymarket",
            market_id="MKT1",
            outcome_id="MKT1_0",
        )
        pos.apply_fill("buy", 100.0, 0.50, 0.0, _ts(0))

        # Open position has nonzero qty
        assert pos.qty != 0
        assert pos.qty == 100.0

    def test_closed_position_has_zero_qty(self) -> None:
        """Closed positions have qty = 0."""
        pos = PositionState(
            wallet="0xTEST",
            platform="polymarket",
            market_id="MKT1",
            outcome_id="MKT1_0",
        )
        pos.apply_fill("buy", 100.0, 0.50, 0.0, _ts(0))
        pos.apply_fill("sell", 100.0, 0.70, 0.0, _ts(1))

        # Closed position has zero qty
        assert pos.qty == 0

    def test_positions_to_arrow_includes_closed_for_merge(self) -> None:
        """positions_to_arrow includes closed positions for ReplacingMergeTree."""
        pos = PositionState(
            wallet="0xTEST",
            platform="polymarket",
            market_id="MKT1",
            outcome_id="MKT1_0",
        )
        pos.apply_fill("buy", 100.0, 0.50, 0.0, _ts(0))
        pos.apply_fill("sell", 100.0, 0.70, 0.0, _ts(1))

        positions = {("0xTEST", "polymarket", "MKT1", "MKT1_0"): pos}
        table = positions_to_arrow(positions)

        # Closed position is included (for ReplacingMergeTree collapse)
        assert table.num_rows == 1
        qty_values = table.column("qty").to_pylist()
        assert qty_values[0] == 0.0

    def test_only_open_positions_should_be_queried(self) -> None:
        """Demonstrate that downstream queries should filter qty != 0."""
        # This test documents the expected query pattern
        pos_open = PositionState(
            wallet="0xOPEN",
            platform="polymarket",
            market_id="MKT1",
            outcome_id="MKT1_0",
        )
        pos_open.apply_fill("buy", 100.0, 0.50, 0.0, _ts(0))

        pos_closed = PositionState(
            wallet="0xCLOSED",
            platform="polymarket",
            market_id="MKT2",
            outcome_id="MKT2_0",
        )
        pos_closed.apply_fill("buy", 50.0, 0.60, 0.0, _ts(0))
        pos_closed.apply_fill("sell", 50.0, 0.80, 0.0, _ts(1))

        positions = {
            ("0xOPEN", "polymarket", "MKT1", "MKT1_0"): pos_open,
            ("0xCLOSED", "polymarket", "MKT2", "MKT2_0"): pos_closed,
        }
        table = positions_to_arrow(positions)

        # Filter to open positions only (simulating downstream query)
        qty_col = table.column("qty")
        open_mask = pa.compute.not_equal(qty_col, 0)
        open_positions = table.filter(open_mask)

        assert open_positions.num_rows == 1
        assert open_positions.column("wallet").to_pylist()[0] == "0xOPEN"


class TestWalletPnlDailyNoZeroTradesCount:
    """Verify wallet_pnl_daily has no rows with trades_count = 0.

    wallet_pnl_daily is sparse output - only emits rows where trades_count > 0.
    """

    def test_pnl_aggregation_produces_nonzero_trades_count(self) -> None:
        """aggregate_pnl_for_day produces rows with trades_count > 0."""
        ledger_rows = [
            {
                "wallet": "0xTEST",
                "qty_delta": 100.0,
                "price": 0.50,
                "fees_usd": 0.0,
                "realized_pnl_this_fill_usd": 0.0,
            },
            {
                "wallet": "0xTEST",
                "qty_delta": 100.0,
                "price": 0.70,
                "fees_usd": 0.0,
                "realized_pnl_this_fill_usd": 20.0,
            },
        ]
        table = aggregate_pnl_for_day(ledger_rows, date(2024, 6, 15))

        assert table.num_rows == 1
        trades_count = table.column("trades_count").to_pylist()[0]
        assert trades_count > 0
        assert trades_count == 2

    def test_empty_ledger_produces_no_pnl_rows(self) -> None:
        """Empty ledger produces zero PnL rows (sparse output)."""
        table = aggregate_pnl_for_day([], date(2024, 6, 15))
        assert table.num_rows == 0

    def test_all_wallets_have_nonzero_trades_count(self) -> None:
        """All wallets in wallet_pnl_daily have trades_count > 0."""
        ledger_rows = [
            # Wallet A: 2 trades
            {
                "wallet": "0xAAA",
                "qty_delta": 100.0,
                "price": 0.50,
                "fees_usd": 0.0,
                "realized_pnl_this_fill_usd": 0.0,
            },
            {
                "wallet": "0xAAA",
                "qty_delta": 100.0,
                "price": 0.70,
                "fees_usd": 0.0,
                "realized_pnl_this_fill_usd": 20.0,
            },
            # Wallet B: 1 trade
            {
                "wallet": "0xBBB",
                "qty_delta": 50.0,
                "price": 0.60,
                "fees_usd": 0.0,
                "realized_pnl_this_fill_usd": 0.0,
            },
        ]
        table = aggregate_pnl_for_day(ledger_rows, date(2024, 6, 15))

        assert table.num_rows == 2
        trades_counts = table.column("trades_count").to_pylist()
        for tc in trades_counts:
            assert tc > 0, "trades_count must be > 0"


class TestMarketMarkDailyPriceBounds:
    """Verify market_mark_daily prices are within reasonable bounds.

    For prediction markets: 0 < price < 1 (probabilities).
    Edge cases: price can be 0 (resolved NO) or 1 (resolved YES) for resolution trades.
    """

    def test_mark_price_within_bounds(self) -> None:
        """mark_price should be within (0, 1) for prediction markets."""
        trades = [
            {
                "platform_market_id": "MKT1",
                "nonusdc_side": "MKT1_0",
                "price": 0.30,
                "usd_amount": 100.0,
                "event_ts": _ts(0),
                "maker": "0xMAKER",
                "taker": "0xTAKER",
            },
            {
                "platform_market_id": "MKT1",
                "nonusdc_side": "MKT1_0",
                "price": 0.50,
                "usd_amount": 200.0,
                "event_ts": _ts(1),
                "maker": "0xMAKER",
                "taker": "0xTAKER",
            },
            {
                "platform_market_id": "MKT1",
                "nonusdc_side": "MKT1_0",
                "price": 0.70,
                "usd_amount": 100.0,
                "event_ts": _ts(2),
                "maker": "0xMAKER",
                "taker": "0xTAKER",
            },
        ]
        table = compute_marks_for_day(trades, "polymarket", date(2024, 6, 15))

        mark_price = table.column("mark_price").to_pylist()[0]
        # VWAP = (0.30*100 + 0.50*200 + 0.70*100) / (100 + 200 + 100) = 200/400 = 0.50
        assert mark_price is not None
        assert 0 < mark_price < 1, "mark_price should be in (0, 1)"
        assert mark_price == pytest.approx(0.50)

    def test_last_trade_price_within_bounds(self) -> None:
        """last_trade_price should be within [0, 1]."""
        trades = [
            {
                "platform_market_id": "MKT1",
                "nonusdc_side": "MKT1_0",
                "price": 0.65,
                "usd_amount": 100.0,
                "event_ts": _ts(0),
                "maker": "0xMAKER",
                "taker": "0xTAKER",
            },
        ]
        table = compute_marks_for_day(trades, "polymarket", date(2024, 6, 15))

        last_trade_price = table.column("last_trade_price").to_pylist()[0]
        assert last_trade_price is not None
        assert 0 <= last_trade_price <= 1, "last_trade_price should be in [0, 1]"

    def test_price_at_zero_edge_case(self) -> None:
        """Price can be 0 for resolved NO outcomes."""
        trades = [
            {
                "platform_market_id": "MKT_RESOLVED",
                "nonusdc_side": "MKT_RESOLVED_NO",
                "price": 0.0,  # Resolved NO
                "usd_amount": 100.0,
                "event_ts": _ts(0),
                "maker": "0xMAKER",
                "taker": "0xTAKER",
            },
        ]
        table = compute_marks_for_day(trades, "polymarket", date(2024, 6, 15))

        mark_price = table.column("mark_price").to_pylist()[0]
        # Price 0 is valid for resolved NO
        assert mark_price == 0.0

    def test_price_at_one_edge_case(self) -> None:
        """Price can be 1 for resolved YES outcomes."""
        trades = [
            {
                "platform_market_id": "MKT_RESOLVED",
                "nonusdc_side": "MKT_RESOLVED_YES",
                "price": 1.0,  # Resolved YES
                "usd_amount": 100.0,
                "event_ts": _ts(0),
                "maker": "0xMAKER",
                "taker": "0xTAKER",
            },
        ]
        table = compute_marks_for_day(trades, "polymarket", date(2024, 6, 15))

        mark_price = table.column("mark_price").to_pylist()[0]
        # Price 1 is valid for resolved YES
        assert mark_price == 1.0

    def test_multiple_markets_all_within_bounds(self) -> None:
        """All market mark prices should be within valid bounds."""
        trades = [
            # Market 1: low probability
            {
                "platform_market_id": "MKT1",
                "nonusdc_side": "MKT1_0",
                "price": 0.10,
                "usd_amount": 100.0,
                "event_ts": _ts(0),
                "maker": "0xMAKER",
                "taker": "0xTAKER",
            },
            # Market 2: medium probability
            {
                "platform_market_id": "MKT2",
                "nonusdc_side": "MKT2_0",
                "price": 0.50,
                "usd_amount": 100.0,
                "event_ts": _ts(1),
                "maker": "0xMAKER",
                "taker": "0xTAKER",
            },
            # Market 3: high probability
            {
                "platform_market_id": "MKT3",
                "nonusdc_side": "MKT3_0",
                "price": 0.90,
                "usd_amount": 100.0,
                "event_ts": _ts(2),
                "maker": "0xMAKER",
                "taker": "0xTAKER",
            },
        ]
        table = compute_marks_for_day(trades, "polymarket", date(2024, 6, 15))

        assert table.num_rows == 3
        for price in table.column("mark_price").to_pylist():
            assert price is not None
            assert 0 <= price <= 1, f"mark_price {price} should be in [0, 1]"


class TestParquetSchemaConformance:
    """Verify all Gold PyArrow tables conform to their canonical schemas.

    Each Gold table has a canonical PyArrow schema defined in its module.
    Data produced by compute functions must match these schemas exactly.
    """

    def test_position_state_schema_conformance(self) -> None:
        """positions_to_arrow produces table conforming to POSITION_STATE_SCHEMA."""
        pos = PositionState(
            wallet="0xTEST",
            platform="polymarket",
            market_id="MKT1",
            outcome_id="MKT1_0",
        )
        pos.apply_fill("buy", 100.0, 0.50, 0.0, _ts(0))

        positions = {("0xTEST", "polymarket", "MKT1", "MKT1_0"): pos}
        table = positions_to_arrow(positions)

        # Schema should match exactly
        assert table.schema.equals(POSITION_STATE_SCHEMA)

    def test_position_state_empty_table_schema(self) -> None:
        """Empty positions_to_arrow produces empty table with correct schema."""
        table = positions_to_arrow({})
        assert table.num_rows == 0
        assert table.schema.equals(POSITION_STATE_SCHEMA)

    def test_ledger_schema_conformance(self) -> None:
        """LedgerWriter.to_arrow produces table conforming to LEDGER_SCHEMA."""
        fills = [
            _fill(ts=_ts(0), side="buy", qty_delta=100.0, price=0.50),
        ]
        writer, _ = build_ledger_for_day(fills, {})
        table = writer.to_arrow()

        assert table.schema.equals(LEDGER_SCHEMA)

    def test_ledger_empty_table_schema(self) -> None:
        """Empty LedgerWriter produces empty table with correct schema."""
        writer = LedgerWriter()
        table = writer.to_arrow()
        assert table.num_rows == 0
        assert table.schema.equals(LEDGER_SCHEMA)

    def test_market_mark_daily_schema_conformance(self) -> None:
        """compute_marks_for_day produces table conforming to MARKET_MARK_DAILY_SCHEMA."""
        trades = [
            {
                "platform_market_id": "MKT1",
                "nonusdc_side": "MKT1_0",
                "price": 0.50,
                "usd_amount": 100.0,
                "event_ts": _ts(0),
                "maker": "0xMAKER",
                "taker": "0xTAKER",
            },
        ]
        table = compute_marks_for_day(trades, "polymarket", date(2024, 6, 15))

        assert table.schema.equals(MARKET_MARK_DAILY_SCHEMA)

    def test_market_mark_daily_empty_table_schema(self) -> None:
        """Empty compute_marks_for_day produces empty table with correct schema."""
        table = compute_marks_for_day([], "polymarket", date(2024, 6, 15))
        assert table.num_rows == 0
        assert table.schema.equals(MARKET_MARK_DAILY_SCHEMA)

    def test_wallet_pnl_daily_schema_conformance(self) -> None:
        """aggregate_pnl_for_day produces table conforming to WALLET_PNL_DAILY_SCHEMA."""
        ledger_rows = [
            {
                "wallet": "0xTEST",
                "qty_delta": 100.0,
                "price": 0.50,
                "fees_usd": 0.0,
                "realized_pnl_this_fill_usd": 0.0,
            },
        ]
        table = aggregate_pnl_for_day(ledger_rows, date(2024, 6, 15))

        assert table.schema.equals(WALLET_PNL_DAILY_SCHEMA)

    def test_wallet_pnl_daily_empty_table_schema(self) -> None:
        """Empty aggregate_pnl_for_day produces empty table with correct schema."""
        table = aggregate_pnl_for_day([], date(2024, 6, 15))
        assert table.num_rows == 0
        assert table.schema.equals(WALLET_PNL_DAILY_SCHEMA)


class TestDataConsistencyConstraints:
    """Additional data quality constraints for Gold tables."""

    def test_position_cost_basis_consistency(self) -> None:
        """cost_basis_usd = abs(qty) * avg_cost for open positions."""
        pos = PositionState(
            wallet="0xTEST",
            platform="polymarket",
            market_id="MKT1",
            outcome_id="MKT1_0",
        )
        pos.apply_fill("buy", 100.0, 0.50, 0.0, _ts(0))

        # cost_basis = abs(qty) * avg_cost = 100 * 0.50 = 50
        expected_cost_basis = abs(pos.qty) * pos.avg_cost
        assert pos.cost_basis_usd == pytest.approx(expected_cost_basis)

    def test_position_avg_cost_positive_for_open(self) -> None:
        """avg_cost > 0 for open positions."""
        pos = PositionState(
            wallet="0xTEST",
            platform="polymarket",
            market_id="MKT1",
            outcome_id="MKT1_0",
        )
        pos.apply_fill("buy", 100.0, 0.50, 0.0, _ts(0))

        assert pos.qty != 0
        assert pos.avg_cost > 0

    def test_ledger_qty_delta_positive(self) -> None:
        """qty_delta > 0 in ledger (direction in side field)."""
        fills = [
            _fill(ts=_ts(0), side="buy", qty_delta=100.0, price=0.50),
            _fill(ts=_ts(1), side="sell", qty_delta=100.0, price=0.70),
        ]
        writer, _ = build_ledger_for_day(fills, {})

        for row in writer.rows:
            assert row.qty_delta > 0, "qty_delta must be positive"

    def test_ledger_price_in_bounds(self) -> None:
        """price in [0, 1] for prediction market fills."""
        fills = [
            _fill(ts=_ts(0), side="buy", qty_delta=100.0, price=0.00),  # Edge: 0
            _fill(ts=_ts(1), side="buy", qty_delta=100.0, price=0.50),  # Normal
            _fill(ts=_ts(2), side="sell", qty_delta=200.0, price=1.00),  # Edge: 1
        ]
        writer, _ = build_ledger_for_day(fills, {})

        for row in writer.rows:
            assert 0 <= row.price <= 1, f"price {row.price} must be in [0, 1]"

    def test_ledger_fees_non_negative(self) -> None:
        """fees_usd >= 0 in ledger."""
        fills = [
            _fill(ts=_ts(0), side="buy", qty_delta=100.0, price=0.50, fees_usd=0.0),
            _fill(ts=_ts(1), side="sell", qty_delta=100.0, price=0.70, fees_usd=1.50),
        ]
        writer, _ = build_ledger_for_day(fills, {})

        for row in writer.rows:
            assert row.fees_usd >= 0, "fees_usd must be non-negative"

    def test_market_marks_volume_non_negative(self) -> None:
        """volume_usd_24h >= 0."""
        trades = [
            {
                "platform_market_id": "MKT1",
                "nonusdc_side": "MKT1_0",
                "price": 0.50,
                "usd_amount": 100.0,
                "event_ts": _ts(0),
                "maker": "0xMAKER",
                "taker": "0xTAKER",
            },
        ]
        table = compute_marks_for_day(trades, "polymarket", date(2024, 6, 15))

        for volume in table.column("volume_usd_24h").to_pylist():
            assert volume >= 0, "volume_usd_24h must be non-negative"

    def test_market_marks_trades_count_positive_when_volume(self) -> None:
        """trades_count_24h > 0 when volume_usd_24h > 0."""
        trades = [
            {
                "platform_market_id": "MKT1",
                "nonusdc_side": "MKT1_0",
                "price": 0.50,
                "usd_amount": 100.0,
                "event_ts": _ts(0),
                "maker": "0xMAKER",
                "taker": "0xTAKER",
            },
        ]
        table = compute_marks_for_day(trades, "polymarket", date(2024, 6, 15))

        rows = table.to_pylist()
        for row in rows:
            if row["volume_usd_24h"] > 0:
                assert row["trades_count_24h"] > 0

    def test_pnl_wins_losses_sum(self) -> None:
        """wins + losses <= trades_count (breakevens fill the gap)."""
        fills = [
            _fill(ts=_ts(0), side="buy", qty_delta=100.0, price=0.50),  # No PnL
            _fill(ts=_ts(1), side="sell", qty_delta=50.0, price=0.70),  # Win
            _fill(ts=_ts(2), side="sell", qty_delta=50.0, price=0.30),  # Loss
        ]
        writer, _ = build_ledger_for_day(fills, {})

        ledger_rows = [
            {
                "wallet": r.wallet,
                "qty_delta": r.qty_delta,
                "price": r.price,
                "fees_usd": r.fees_usd,
                "realized_pnl_this_fill_usd": r.realized_pnl_this_fill_usd,
            }
            for r in writer.rows
        ]
        table = aggregate_pnl_for_day(ledger_rows, date(2024, 6, 15))
        row = table.to_pylist()[0]

        # wins + losses + breakevens = trades_count
        # Buy has 0 PnL (counted as breakeven)
        # First sell has positive PnL (win)
        # Second sell has negative PnL (loss)
        assert row["wins"] + row["losses"] <= row["trades_count"]
        breakevens = row["trades_count"] - row["wins"] - row["losses"]
        assert breakevens >= 0

    def test_pnl_volume_matches_sum_of_trades(self) -> None:
        """volume_usd equals sum of abs(qty_delta * price)."""
        fills = [
            _fill(ts=_ts(0), side="buy", qty_delta=100.0, price=0.50),
            _fill(ts=_ts(1), side="sell", qty_delta=100.0, price=0.70),
        ]
        writer, _ = build_ledger_for_day(fills, {})

        expected_volume = sum(abs(r.qty_delta * r.price) for r in writer.rows)

        ledger_rows = [
            {
                "wallet": r.wallet,
                "qty_delta": r.qty_delta,
                "price": r.price,
                "fees_usd": r.fees_usd,
                "realized_pnl_this_fill_usd": r.realized_pnl_this_fill_usd,
            }
            for r in writer.rows
        ]
        table = aggregate_pnl_for_day(ledger_rows, date(2024, 6, 15))
        row = table.to_pylist()[0]

        assert row["volume_usd"] == pytest.approx(expected_volume)
