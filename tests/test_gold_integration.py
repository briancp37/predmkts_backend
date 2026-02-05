"""Integration Tests for Gold Layer Pipeline.

End-to-end integration tests for the full Gold pipeline, verifying correctness
of data flow through all components.

PRD Reference: plans/release/03_gold_level/sprint/09_validation_and_delivery/prd.json
Category: integration_tests
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from io import BytesIO
from typing import Any
from unittest.mock import MagicMock, patch

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from prediction_data.gold.accounting import PositionState
from prediction_data.gold.fill_splitter import Fill, trades_to_fills
from prediction_data.gold.ledger import (
    LEDGER_COLUMNS,
    LEDGER_SCHEMA,
    LedgerWriter,
    build_ledger_for_day,
)
from prediction_data.gold.market_marks import (
    MARKET_MARK_DAILY_COLUMNS,
    MARKET_MARK_DAILY_SCHEMA,
    compute_marks_for_day,
    compute_market_marks,
)
from prediction_data.gold.on_demand import (
    SNAPSHOT_COLUMNS,
    SNAPSHOT_SCHEMA,
    _replay_fills_to_snapshots,
    compute_wallet_snapshots,
)
from prediction_data.gold.position_state import (
    POSITION_STATE_COLUMNS,
    POSITION_STATE_SCHEMA,
    positions_to_arrow,
)
from prediction_data.gold.trade_processor import process_day
from prediction_data.gold.wallet_pnl import (
    WALLET_PNL_DAILY_COLUMNS,
    WALLET_PNL_DAILY_SCHEMA,
    aggregate_pnl_for_day,
    compute_wallet_pnl,
)


# =============================================================================
# TEST HELPERS
# =============================================================================


def _ts(minute: int = 0, day: int = 15) -> datetime:
    """Helper to create test timestamps."""
    return datetime(2024, 6, day, 12, minute, 0, tzinfo=UTC)


def _trade(
    *,
    ts: datetime | None = None,
    market_id: str = "cond_abc",
    maker: str = "0xMAKER",
    taker: str = "0xTAKER",
    nonusdc_side: str = "token1",
    maker_direction: str = "sell",
    taker_direction: str = "buy",
    price: float = 0.60,
    token_amount: float = 100.0,
    usd_amount: float = 60.0,
) -> dict[str, Any]:
    """Create a Silver trade dict."""
    return {
        "event_ts": ts or _ts(),
        "platform_market_id": market_id,
        "platform_trade_id": f"t_{id(ts)}",
        "maker": maker,
        "taker": taker,
        "nonusdc_side": nonusdc_side,
        "maker_direction": maker_direction,
        "taker_direction": taker_direction,
        "price": price,
        "token_amount": token_amount,
        "usd_amount": usd_amount,
        "transaction_hash": "0x123",
    }


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


def _mock_silver_catalog(trades: list[dict[str, Any]]) -> MagicMock:
    """Create a mock PyIceberg catalog that returns the given trades."""
    mock_catalog = MagicMock()
    mock_table = MagicMock()
    mock_scan = MagicMock()
    mock_arrow = MagicMock()

    mock_catalog.load_table.return_value = mock_table
    mock_table.scan.return_value = mock_scan
    mock_scan.to_arrow.return_value = mock_arrow
    mock_arrow.to_pylist.return_value = trades

    return mock_catalog


def _mock_s3_with_parquet(tables: dict[str, pa.Table]) -> MagicMock:
    """Create a mock S3 client that returns parquet data for given keys.

    Args:
        tables: Mapping of S3 key pattern to PyArrow table.
    """
    s3 = MagicMock()
    s3.exceptions.NoSuchKey = type("NoSuchKey", (Exception,), {})

    def get_object(Bucket: str, Key: str) -> dict[str, Any]:  # noqa: N803
        for pattern, table in tables.items():
            if pattern in Key:
                buf = BytesIO()
                pq.write_table(table, buf)
                buf.seek(0)
                return {"Body": BytesIO(buf.read())}
        raise s3.exceptions.NoSuchKey()

    s3.get_object.side_effect = get_object
    return s3


# =============================================================================
# INTEGRATION TEST 1: Silver trades → process-trades → ledger + position_state
# =============================================================================


class TestSilverToLedgerIntegration:
    """Integration test: Silver trades → process-trades → ledger + position_state."""

    def test_full_pipeline_single_trade(self) -> None:
        """A single Silver trade produces correct ledger and position state."""
        trade = _trade(
            ts=_ts(0),
            maker="0xSELLER",
            taker="0xBUYER",
            maker_direction="sell",
            taker_direction="buy",
            price=0.60,
            token_amount=100.0,
            market_id="mkt1",
            nonusdc_side="token1",
        )

        mock_catalog = _mock_silver_catalog([trade])

        with patch(
            "prediction_data.gold.trade_processor.read_position_states",
            return_value={},
        ):
            fills_count = process_day(
                dt=date(2024, 6, 15),
                catalog=mock_catalog,
                dry_run=True,
            )

        # 1 trade → 2 fills (maker + taker)
        assert fills_count == 2

    def test_full_pipeline_multiple_trades_preserves_order(self) -> None:
        """Multiple trades are processed in timestamp order."""
        trades = [
            _trade(ts=_ts(0), price=0.50, maker="0xA", taker="0xB"),
            _trade(ts=_ts(1), price=0.55, maker="0xB", taker="0xC"),
            _trade(ts=_ts(2), price=0.60, maker="0xC", taker="0xD"),
        ]

        # Convert through fill splitter
        fills = trades_to_fills(trades, platform="polymarket")

        # Verify timestamp ordering
        timestamps = [f.ts for f in fills]
        assert timestamps == sorted(timestamps)

        # Process through ledger
        writer, positions = build_ledger_for_day(fills, {})

        # 3 trades → 6 fills
        assert writer.count == 6

    def test_position_state_updated_correctly(self) -> None:
        """Position state reflects accumulated trades."""
        fills = [
            _fill(ts=_ts(0), wallet="0xA", side="buy", qty_delta=100, price=0.50),
            _fill(ts=_ts(1), wallet="0xA", side="buy", qty_delta=50, price=0.60),
        ]

        writer, positions = build_ledger_for_day(fills, {})

        # Should have one position for wallet 0xA
        assert len(positions) == 1
        pos = positions[("0xA", "polymarket", "MKT1", "MKT1_0")]

        # Verify weighted average cost: (100*0.50 + 50*0.60) / 150 = 80/150 = 0.5333...
        assert pos.qty == 150
        assert pos.avg_cost == pytest.approx((100 * 0.50 + 50 * 0.60) / 150)

    def test_ledger_contains_before_after_state(self) -> None:
        """Ledger rows contain correct before/after state snapshots."""
        fills = [
            _fill(ts=_ts(0), side="buy", qty_delta=100, price=0.50),
            _fill(ts=_ts(1), side="sell", qty_delta=50, price=0.70),
        ]

        writer, _ = build_ledger_for_day(fills, {})
        rows = writer.rows

        # First fill: open position
        assert rows[0].qty_before == 0
        assert rows[0].qty_after == 100
        assert rows[0].avg_cost_before == 0
        assert rows[0].avg_cost_after == pytest.approx(0.50)
        assert rows[0].realized_pnl_this_fill_usd == 0  # Opening - no PnL

        # Second fill: partial close
        assert rows[1].qty_before == 100
        assert rows[1].qty_after == 50
        assert rows[1].avg_cost_before == pytest.approx(0.50)
        # PnL: 50 * (0.70 - 0.50) = $10
        assert rows[1].realized_pnl_this_fill_usd == pytest.approx(10.0)

    def test_existing_positions_carry_forward(self) -> None:
        """Existing position state carries forward into new day processing."""
        existing_pos = PositionState(
            wallet="0xA",
            platform="polymarket",
            market_id="MKT1",
            outcome_id="MKT1_0",
            qty=100,
            avg_cost=0.40,
            cost_basis_usd=40.0,
            last_fill_ts=_ts(0, day=14),
            first_open_ts=_ts(0, day=14),
        )
        existing_positions = {
            ("0xA", "polymarket", "MKT1", "MKT1_0"): existing_pos,
        }

        # New sell on day 15
        fills = [
            _fill(ts=_ts(0), wallet="0xA", side="sell", qty_delta=100, price=0.70),
        ]

        writer, positions = build_ledger_for_day(fills, existing_positions)

        # Should have realized PnL from existing position
        # PnL: 100 * (0.70 - 0.40) = $30
        assert writer.rows[0].qty_before == 100
        assert writer.rows[0].avg_cost_before == pytest.approx(0.40)
        assert writer.rows[0].realized_pnl_this_fill_usd == pytest.approx(30.0)


# =============================================================================
# INTEGRATION TEST 2: Silver trades → compute-marks → market_mark_daily
# =============================================================================


class TestSilverToMarksIntegration:
    """Integration test: Silver trades → compute-marks → market_mark_daily."""

    def test_vwap_computation_accuracy(self) -> None:
        """VWAP is computed correctly from multiple trades."""
        trades = [
            _trade(ts=_ts(0), price=0.50, usd_amount=50, token_amount=100),
            _trade(ts=_ts(1), price=0.60, usd_amount=60, token_amount=100),
            _trade(ts=_ts(2), price=0.70, usd_amount=140, token_amount=200),
        ]

        mark_table = compute_marks_for_day(trades, "polymarket", date(2024, 6, 15))
        assert mark_table.num_rows == 1

        row = mark_table.to_pylist()[0]
        # VWAP = (50*50 + 60*60 + 140*70) / (50 + 60 + 140)
        #      = (2500 + 3600 + 9800) / 250 = 15900/250 = 63.6
        # Wait, that's wrong. VWAP = sum(price * amount) / sum(amount)
        # = (0.50*50 + 0.60*60 + 0.70*140) / (50+60+140)
        # = (25 + 36 + 98) / 250 = 159/250 = 0.636
        assert row["mark_price"] == pytest.approx(0.636)

    def test_last_trade_price_is_latest(self) -> None:
        """Last trade price reflects the most recent trade."""
        trades = [
            _trade(ts=_ts(0), price=0.50),
            _trade(ts=_ts(1), price=0.60),
            _trade(ts=_ts(2), price=0.75),  # Latest
        ]

        mark_table = compute_marks_for_day(trades, "polymarket", date(2024, 6, 15))
        row = mark_table.to_pylist()[0]

        assert row["last_trade_price"] == pytest.approx(0.75)

    def test_volume_aggregation(self) -> None:
        """24h volume aggregates correctly."""
        trades = [
            _trade(ts=_ts(0), usd_amount=100),
            _trade(ts=_ts(1), usd_amount=200),
            _trade(ts=_ts(2), usd_amount=150),
        ]

        mark_table = compute_marks_for_day(trades, "polymarket", date(2024, 6, 15))
        row = mark_table.to_pylist()[0]

        assert row["volume_usd_24h"] == pytest.approx(450)
        assert row["trades_count_24h"] == 3

    def test_active_wallets_count(self) -> None:
        """Active wallets count is distinct maker + taker."""
        trades = [
            _trade(ts=_ts(0), maker="0xA", taker="0xB"),
            _trade(ts=_ts(1), maker="0xA", taker="0xC"),  # A repeats
            _trade(ts=_ts(2), maker="0xD", taker="0xB"),  # B repeats
        ]

        mark_table = compute_marks_for_day(trades, "polymarket", date(2024, 6, 15))
        row = mark_table.to_pylist()[0]

        # Distinct wallets: A, B, C, D = 4
        assert row["active_wallets_24h"] == 4

    def test_multiple_markets_computed_separately(self) -> None:
        """Each market/outcome gets its own row."""
        trades = [
            _trade(ts=_ts(0), market_id="mkt1", nonusdc_side="token1", price=0.50),
            _trade(ts=_ts(1), market_id="mkt1", nonusdc_side="token2", price=0.60),
            _trade(ts=_ts(2), market_id="mkt2", nonusdc_side="tokenA", price=0.70),
        ]

        mark_table = compute_marks_for_day(trades, "polymarket", date(2024, 6, 15))

        # 3 distinct (market_id, outcome_id) combinations
        assert mark_table.num_rows == 3

        rows = {(r["market_id"], r["outcome_id"]): r for r in mark_table.to_pylist()}
        assert ("mkt1", "token1") in rows
        assert ("mkt1", "token2") in rows
        assert ("mkt2", "tokenA") in rows

    def test_schema_conformance(self) -> None:
        """Output conforms to MARKET_MARK_DAILY_SCHEMA."""
        trades = [_trade(ts=_ts(0))]
        mark_table = compute_marks_for_day(trades, "polymarket", date(2024, 6, 15))

        # Check all expected columns present
        for col in MARKET_MARK_DAILY_COLUMNS:
            assert col in mark_table.column_names


# =============================================================================
# INTEGRATION TEST 3: full daily-run → all Gold tables populated
# =============================================================================


class TestDailyRunIntegration:
    """Integration test: full daily-run → all Gold tables populated → verify."""

    def test_daily_run_all_steps_execute(self) -> None:
        """daily-run executes all steps in sequence."""
        from prediction_data.cli.gold import _run_daily_step

        steps_executed = []

        with patch(
            "prediction_data.gold.dimensions.load_dim_platform", return_value=2
        ), patch(
            "prediction_data.gold.dimensions.load_dim_market", return_value=100
        ), patch(
            "prediction_data.gold.dimensions.load_dim_outcome", return_value=200
        ), patch(
            "prediction_data.gold.dimensions.load_dim_wallet", return_value=50
        ), patch(
            "prediction_data.gold.dimensions.load_dim_event", return_value=30
        ), patch(
            "prediction_data.gold.dimensions.load_dim_category", return_value=10
        ):
            rows = _run_daily_step(
                "load-dims", date(2024, 6, 15), gold_bucket="test", dry_run=True
            )
            steps_executed.append(("load-dims", rows))
            # Sum of all dimension loads
            assert rows == 392

        with patch(
            "prediction_data.gold.trade_processor.process_day", return_value=1000
        ):
            rows = _run_daily_step(
                "process-trades", date(2024, 6, 15), gold_bucket="test", dry_run=True
            )
            steps_executed.append(("process-trades", rows))
            assert rows == 1000

        with patch(
            "prediction_data.gold.market_marks.compute_market_marks", return_value=50
        ):
            rows = _run_daily_step(
                "compute-marks", date(2024, 6, 15), gold_bucket="test", dry_run=True
            )
            steps_executed.append(("compute-marks", rows))
            assert rows == 50

        with patch(
            "prediction_data.gold.wallet_pnl.compute_wallet_pnl", return_value=100
        ), patch(
            "prediction_data.gold.wallet_mtm.compute_wallet_mtm", return_value=20
        ), patch(
            "prediction_data.gold.wallet_position_snapshot.compute_wallet_position_snapshot",
            return_value=25,
        ):
            rows = _run_daily_step(
                "compute-wallet-metrics",
                date(2024, 6, 15),
                gold_bucket="test",
                dry_run=True,
            )
            steps_executed.append(("compute-wallet-metrics", rows))
            assert rows == 145

        assert len(steps_executed) == 4

    def test_ledger_to_pnl_flow(self) -> None:
        """Ledger data flows correctly to wallet_pnl_daily aggregation."""
        # Create a sequence of fills
        fills = [
            _fill(ts=_ts(0), wallet="0xA", side="buy", qty_delta=100, price=0.50),
            _fill(ts=_ts(1), wallet="0xA", side="sell", qty_delta=100, price=0.70),
            _fill(ts=_ts(2), wallet="0xB", side="buy", qty_delta=50, price=0.60),
            _fill(ts=_ts(3), wallet="0xB", side="sell", qty_delta=50, price=0.55),
        ]

        writer, _ = build_ledger_for_day(fills, {})

        # Convert to wallet_pnl input
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

        pnl_table = aggregate_pnl_for_day(ledger_rows, date(2024, 6, 15))
        pnl_by_wallet = {r["wallet"]: r for r in pnl_table.to_pylist()}

        # Wallet A: PnL = 100 * (0.70 - 0.50) = $20
        assert pnl_by_wallet["0xA"]["realized_pnl_usd"] == pytest.approx(20.0)
        assert pnl_by_wallet["0xA"]["wins"] == 1
        assert pnl_by_wallet["0xA"]["losses"] == 0

        # Wallet B: PnL = 50 * (0.55 - 0.60) = -$2.50
        assert pnl_by_wallet["0xB"]["realized_pnl_usd"] == pytest.approx(-2.50)
        assert pnl_by_wallet["0xB"]["wins"] == 0
        assert pnl_by_wallet["0xB"]["losses"] == 1


# =============================================================================
# INTEGRATION TEST 4: ch-load with lookback → only recent partitions in CH
# =============================================================================


class TestChLoadLookbackIntegration:
    """Integration test: ch-load with lookback → only recent partitions in CH."""

    def test_lookback_filters_old_partitions(self) -> None:
        """ch-load only loads partitions within lookback window."""
        from prediction_data.gold.ch_loader import load_gold_table_to_clickhouse

        today = date.today()
        old_day = today - timedelta(days=100)
        recent_day = today - timedelta(days=5)

        # Create mock parquet data
        mock_recent_table = pa.table(
            {col: [] for col in MARKET_MARK_DAILY_COLUMNS},
            schema=MARKET_MARK_DAILY_SCHEMA,
        )

        loaded_days: list[str] = []

        def mock_get_object(Bucket: str, Key: str) -> dict[str, Any]:  # noqa: N803
            # Extract day from key like "gold/market_mark_daily/day=2024-06-15/..."
            if f"day={recent_day}" in Key:
                loaded_days.append(str(recent_day))
                buf = BytesIO()
                pq.write_table(mock_recent_table, buf)
                buf.seek(0)
                return {"Body": BytesIO(buf.read())}
            raise MagicMock().exceptions.NoSuchKey()

        mock_s3 = MagicMock()
        mock_s3.exceptions.NoSuchKey = type("NoSuchKey", (Exception,), {})
        mock_s3.get_object.side_effect = mock_get_object

        mock_ch = MagicMock()

        # Load with 90-day lookback (should include recent_day, exclude old_day)
        load_gold_table_to_clickhouse(
            table_name="market_mark_daily",
            gold_bucket="test-bucket",
            lookback_days=90,
            s3_client=mock_s3,
            clickhouse_client=mock_ch,
        )

        # Verify only recent partition was attempted
        # (old_day at 100 days ago is outside 90-day window)
        assert str(old_day) not in loaded_days


# =============================================================================
# INTEGRATION TEST 5: on-demand compute-snapshot → S3 cached + CH loaded
# =============================================================================


class TestOnDemandSnapshotIntegration:
    """Integration test: on-demand compute-snapshot → S3 cached + CH loaded."""

    def test_snapshot_reconstruction_from_ledger(self) -> None:
        """Snapshots are correctly reconstructed from ledger fills."""
        wallet = "0xTEST"
        dates = [date(2024, 6, 15), date(2024, 6, 16)]

        # Initial position: None
        initial_positions: dict[tuple[str, str, str], dict[str, Any]] = {}

        # Fills: buy on day 1, sell partial on day 2
        fills = [
            {
                "ts": _ts(0, day=15),
                "platform": "polymarket",
                "market_id": "MKT1",
                "outcome_id": "MKT1_0",
                "side": "buy",
                "qty_delta": 100,
                "price": 0.50,
                "fees_usd": 0,
                "qty_after": 100,
                "avg_cost_after": 0.50,
            },
            {
                "ts": _ts(0, day=16),
                "platform": "polymarket",
                "market_id": "MKT1",
                "outcome_id": "MKT1_0",
                "side": "sell",
                "qty_delta": 50,
                "price": 0.70,
                "fees_usd": 0,
                "qty_after": 50,
                "avg_cost_after": 0.50,
            },
        ]

        # Market marks
        marks = {
            (date(2024, 6, 15), "polymarket", "MKT1", "MKT1_0"): 0.55,
            (date(2024, 6, 16), "polymarket", "MKT1", "MKT1_0"): 0.70,
        }

        snapshot_table = _replay_fills_to_snapshots(
            wallet, dates, initial_positions, fills, marks
        )

        rows = snapshot_table.to_pylist()

        # Day 15: qty=100, mark=0.55, position_value=55, unrealized_pnl=5
        day15_rows = [r for r in rows if r["day_utc"] == date(2024, 6, 15)]
        assert len(day15_rows) == 1
        assert day15_rows[0]["qty"] == 100
        assert day15_rows[0]["mark_price"] == pytest.approx(0.55)
        assert day15_rows[0]["position_value_usd"] == pytest.approx(55.0)
        # unrealized = 100 * (0.55 - 0.50) = 5
        assert day15_rows[0]["unrealized_pnl_usd"] == pytest.approx(5.0)

        # Day 16: qty=50 (after partial sell), mark=0.70
        day16_rows = [r for r in rows if r["day_utc"] == date(2024, 6, 16)]
        assert len(day16_rows) == 1
        assert day16_rows[0]["qty"] == 50
        assert day16_rows[0]["mark_price"] == pytest.approx(0.70)
        # unrealized = 50 * (0.70 - 0.50) = 10
        assert day16_rows[0]["unrealized_pnl_usd"] == pytest.approx(10.0)

    def test_snapshot_schema_conformance(self) -> None:
        """Snapshot output conforms to SNAPSHOT_SCHEMA."""
        wallet = "0xTEST"
        dates = [date(2024, 6, 15)]
        initial_positions: dict[tuple[str, str, str], dict[str, Any]] = {}
        fills: list[dict[str, Any]] = []
        marks: dict[tuple[date, str, str, str], float] = {}

        snapshot_table = _replay_fills_to_snapshots(
            wallet, dates, initial_positions, fills, marks
        )

        for col in SNAPSHOT_COLUMNS:
            assert col in snapshot_table.column_names


# =============================================================================
# ADDITIONAL INTEGRATION TESTS: SCHEMA VERIFICATION
# =============================================================================


class TestSchemaConsistency:
    """Verify schema consistency across all Gold outputs."""

    def test_ledger_schema_consistency(self) -> None:
        """Ledger writer produces Arrow table with correct schema."""
        fills = [_fill()]
        writer, _ = build_ledger_for_day(fills, {})
        arrow_table = writer.to_arrow()

        assert arrow_table.schema.equals(LEDGER_SCHEMA)

    def test_position_state_schema_consistency(self) -> None:
        """Position state produces Arrow table with correct schema."""
        positions = {
            ("0xA", "polymarket", "MKT1", "MKT1_0"): PositionState(
                wallet="0xA",
                platform="polymarket",
                market_id="MKT1",
                outcome_id="MKT1_0",
                qty=100,
                avg_cost=0.50,
                cost_basis_usd=50.0,
                last_fill_ts=_ts(),
                first_open_ts=_ts(),
            ),
        }
        arrow_table = positions_to_arrow(positions)

        assert arrow_table.schema.equals(POSITION_STATE_SCHEMA)

    def test_marks_schema_consistency(self) -> None:
        """Market marks produces Arrow table with correct schema."""
        trades = [_trade()]
        mark_table = compute_marks_for_day(trades, "polymarket", date(2024, 6, 15))

        assert mark_table.schema.equals(MARKET_MARK_DAILY_SCHEMA)

    def test_pnl_schema_consistency(self) -> None:
        """Wallet PnL produces Arrow table with correct schema."""
        ledger_rows = [
            {
                "wallet": "0xA",
                "qty_delta": 100,
                "price": 0.50,
                "fees_usd": 0,
                "realized_pnl_this_fill_usd": 10.0,
            }
        ]
        pnl_table = aggregate_pnl_for_day(ledger_rows, date(2024, 6, 15))

        assert pnl_table.schema.equals(WALLET_PNL_DAILY_SCHEMA)


# =============================================================================
# END-TO-END PIPELINE VERIFICATION
# =============================================================================


class TestEndToEndPipeline:
    """End-to-end pipeline verification with realistic data flow."""

    def test_complete_trading_day_flow(self) -> None:
        """Simulate a complete trading day through all Gold components."""
        # Step 1: Create Silver trades
        trades = [
            # Trade 1: A sells to B
            _trade(
                ts=_ts(0),
                maker="0xA",
                taker="0xB",
                maker_direction="sell",
                taker_direction="buy",
                price=0.50,
                token_amount=100,
                usd_amount=50,
                market_id="mkt1",
                nonusdc_side="token1",
            ),
            # Trade 2: B sells partial to C
            _trade(
                ts=_ts(1),
                maker="0xB",
                taker="0xC",
                maker_direction="sell",
                taker_direction="buy",
                price=0.60,
                token_amount=50,
                usd_amount=30,
                market_id="mkt1",
                nonusdc_side="token1",
            ),
            # Trade 3: Different market
            _trade(
                ts=_ts(2),
                maker="0xD",
                taker="0xE",
                maker_direction="sell",
                taker_direction="buy",
                price=0.70,
                token_amount=200,
                usd_amount=140,
                market_id="mkt2",
                nonusdc_side="token1",  # Must be token1 or token2
            ),
        ]

        # Step 2: Process through fill splitter
        fills = trades_to_fills(trades, platform="polymarket")
        assert len(fills) == 6  # 3 trades × 2 sides

        # Step 3: Build ledger
        writer, positions = build_ledger_for_day(fills, {})
        assert writer.count == 6

        # Step 4: Compute market marks
        mark_table = compute_marks_for_day(trades, "polymarket", date(2024, 6, 15))
        marks_by_key = {
            (r["market_id"], r["outcome_id"]): r for r in mark_table.to_pylist()
        }

        # With < 3 trades, falls back to last trade price instead of VWAP
        # mkt1/token1: 2 trades, last trade price = 0.60
        assert marks_by_key[("mkt1", "token1")]["mark_price"] == pytest.approx(0.60)
        # mkt2/token1: 1 trade, last trade price = 0.70
        assert marks_by_key[("mkt2", "token1")]["mark_price"] == pytest.approx(0.70)

        # Step 5: Aggregate PnL
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
        pnl_table = aggregate_pnl_for_day(ledger_rows, date(2024, 6, 15))

        # Verify we have PnL rows for all active wallets
        pnl_wallets = {r["wallet"] for r in pnl_table.to_pylist()}
        assert "0xA" in pnl_wallets
        assert "0xB" in pnl_wallets

        # Step 6: Verify position state
        # B should have 50 tokens remaining (bought 100, sold 50)
        # Note: fill_splitter creates outcome_id as "{market_id}_{0|1}" from nonusdc_side
        b_pos = positions.get(("0xB", "polymarket", "mkt1", "mkt1_0"))
        assert b_pos is not None
        assert b_pos.qty == 50

    def test_multi_day_position_carryover(self) -> None:
        """Position state carries correctly across multiple days."""
        # Day 1: Buy position
        day1_fills = [
            _fill(
                ts=_ts(0, day=15),
                wallet="0xA",
                side="buy",
                qty_delta=100,
                price=0.50,
            )
        ]
        writer1, positions = build_ledger_for_day(day1_fills, {})

        assert positions[("0xA", "polymarket", "MKT1", "MKT1_0")].qty == 100
        assert positions[("0xA", "polymarket", "MKT1", "MKT1_0")].avg_cost == pytest.approx(0.50)

        # Day 2: Add to position at different price
        day2_fills = [
            _fill(
                ts=_ts(0, day=16),
                wallet="0xA",
                side="buy",
                qty_delta=50,
                price=0.60,
            )
        ]
        writer2, positions = build_ledger_for_day(day2_fills, positions)

        # New avg_cost: (100*0.50 + 50*0.60) / 150 = 80/150 ≈ 0.5333
        assert positions[("0xA", "polymarket", "MKT1", "MKT1_0")].qty == 150
        assert positions[("0xA", "polymarket", "MKT1", "MKT1_0")].avg_cost == pytest.approx(
            (100 * 0.50 + 50 * 0.60) / 150
        )

        # Day 3: Close position
        day3_fills = [
            _fill(
                ts=_ts(0, day=17),
                wallet="0xA",
                side="sell",
                qty_delta=150,
                price=0.70,
            )
        ]
        writer3, positions = build_ledger_for_day(day3_fills, positions)

        # Position should be closed
        assert positions[("0xA", "polymarket", "MKT1", "MKT1_0")].qty == 0

        # Realized PnL: 150 * (0.70 - 0.5333) = 150 * 0.1667 ≈ $25
        expected_pnl = 150 * (0.70 - (100 * 0.50 + 50 * 0.60) / 150)
        assert writer3.rows[0].realized_pnl_this_fill_usd == pytest.approx(expected_pnl)
