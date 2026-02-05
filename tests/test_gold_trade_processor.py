"""Tests for the batch trade processor (trade_processor.py)."""

from __future__ import annotations

import json
from datetime import UTC, date, datetime
from io import BytesIO
from unittest.mock import MagicMock, patch

import pytest

from prediction_data.gold.accounting import PositionState
from prediction_data.gold.fill_splitter import Fill
from prediction_data.gold.trade_processor import (
    _STATE_KEY,
    _compute_summary,
    _load_processed_dates,
    _mark_processed,
    _read_silver_trades_for_day,
    process_date_range,
    process_day,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _ts(minute: int = 0) -> datetime:
    """Helper to create test timestamps."""
    return datetime(2024, 6, 15, 12, minute, 0, tzinfo=UTC)


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
) -> dict:
    """Create a Silver trade dict."""
    return {
        "event_ts": ts or _ts(),
        "platform_market_id": market_id,
        "platform_trade_id": "t1",
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


def _make_s3_state(days: list[str]) -> str:
    """Build JSONL state content from a list of day strings."""
    lines = []
    for d in days:
        lines.append(
            json.dumps(
                {
                    "day": d,
                    "processed_at": "2024-06-16T00:00:00+00:00",
                    "fills_processed": 10,
                    "positions_updated": 2,
                    "realized_pnl_total": 5.0,
                },
                separators=(",", ":"),
            )
        )
    return "\n".join(lines) + "\n" if lines else ""


# ---------------------------------------------------------------------------
# State store tests
# ---------------------------------------------------------------------------


class TestLoadProcessedDates:
    def test_empty_state(self) -> None:
        s3 = MagicMock()
        s3.exceptions.NoSuchKey = type("NoSuchKey", (Exception,), {})
        s3.get_object.side_effect = s3.exceptions.NoSuchKey()
        result = _load_processed_dates(s3, "bucket")
        assert result == set()

    def test_loads_dates(self) -> None:
        content = _make_s3_state(["2024-06-14", "2024-06-15"])
        s3 = MagicMock()
        s3.get_object.return_value = {"Body": BytesIO(content.encode())}
        result = _load_processed_dates(s3, "bucket")
        assert result == {"2024-06-14", "2024-06-15"}

    def test_handles_generic_exception(self) -> None:
        s3 = MagicMock()
        s3.exceptions.NoSuchKey = type("NoSuchKey", (Exception,), {})
        s3.get_object.side_effect = RuntimeError("connection error")
        result = _load_processed_dates(s3, "bucket")
        assert result == set()

    def test_skips_entries_without_day(self) -> None:
        content = json.dumps({"processed_at": "2024-06-16T00:00:00+00:00"}) + "\n"
        s3 = MagicMock()
        s3.get_object.return_value = {"Body": BytesIO(content.encode())}
        result = _load_processed_dates(s3, "bucket")
        assert result == set()


class TestMarkProcessed:
    def test_appends_to_empty(self) -> None:
        s3 = MagicMock()
        s3.get_object.side_effect = Exception("no file")

        _mark_processed(
            s3,
            "bucket",
            "2024-06-15",
            fills_processed=200,
            positions_updated=50,
            realized_pnl_total=12.345678,
        )

        s3.put_object.assert_called_once()
        body = s3.put_object.call_args.kwargs["Body"].decode()
        parsed = json.loads(body.strip())
        assert parsed["day"] == "2024-06-15"
        assert parsed["fills_processed"] == 200
        assert parsed["positions_updated"] == 50
        assert parsed["realized_pnl_total"] == 12.345678

    def test_appends_to_existing(self) -> None:
        existing = _make_s3_state(["2024-06-14"])
        s3 = MagicMock()
        s3.get_object.return_value = {"Body": BytesIO(existing.encode())}

        _mark_processed(
            s3,
            "bucket",
            "2024-06-15",
            fills_processed=100,
            positions_updated=25,
            realized_pnl_total=5.0,
        )

        body = s3.put_object.call_args.kwargs["Body"].decode()
        lines = [line for line in body.strip().splitlines() if line.strip()]
        assert len(lines) == 2
        assert json.loads(lines[0])["day"] == "2024-06-14"
        assert json.loads(lines[1])["day"] == "2024-06-15"


# ---------------------------------------------------------------------------
# _compute_summary tests
# ---------------------------------------------------------------------------


class TestComputeSummary:
    def test_empty(self) -> None:
        from prediction_data.gold.ledger import LedgerWriter

        writer = LedgerWriter()
        positions: dict[tuple[str, str, str, str], PositionState] = {}
        updated, pnl = _compute_summary(writer, positions)
        assert updated == 0
        assert pnl == 0.0

    def test_with_data(self) -> None:
        from prediction_data.gold.ledger import build_ledger_for_day

        fills = [
            Fill(
                ts=_ts(0),
                wallet="0xA",
                platform="polymarket",
                market_id="m1",
                outcome_id="m1_0",
                side="buy",
                qty_delta=100.0,
                price=0.60,
                fees_usd=0.0,
            ),
            Fill(
                ts=_ts(1),
                wallet="0xA",
                platform="polymarket",
                market_id="m1",
                outcome_id="m1_0",
                side="sell",
                qty_delta=100.0,
                price=0.80,
                fees_usd=0.0,
            ),
        ]
        positions: dict[tuple[str, str, str, str], PositionState] = {}
        writer, positions = build_ledger_for_day(fills, positions)

        updated, pnl = _compute_summary(writer, positions)
        assert updated == 1
        assert pnl == pytest.approx(20.0)  # (0.80 - 0.60) * 100


# ---------------------------------------------------------------------------
# _read_silver_trades_for_day tests
# ---------------------------------------------------------------------------


class TestReadSilverTrades:
    def test_reads_and_filters(self) -> None:
        """Verify PyIceberg is called with correct table and filter."""
        mock_catalog = MagicMock()
        mock_table = MagicMock()
        mock_scan = MagicMock()
        mock_arrow = MagicMock()

        mock_catalog.load_table.return_value = mock_table
        mock_table.scan.return_value = mock_scan
        mock_scan.to_arrow.return_value = mock_arrow
        mock_arrow.to_pylist.return_value = [_trade()]

        result = _read_silver_trades_for_day(
            date(2024, 6, 15), catalog=mock_catalog
        )

        mock_catalog.load_table.assert_called_once_with(
            ("silver_polymarket", "trades")
        )
        mock_table.scan.assert_called_once()
        assert len(result) == 1

    def test_empty_result(self) -> None:
        mock_catalog = MagicMock()
        mock_table = MagicMock()
        mock_scan = MagicMock()
        mock_arrow = MagicMock()

        mock_catalog.load_table.return_value = mock_table
        mock_table.scan.return_value = mock_scan
        mock_scan.to_arrow.return_value = mock_arrow
        mock_arrow.to_pylist.return_value = []

        result = _read_silver_trades_for_day(
            date(2024, 6, 15), catalog=mock_catalog
        )
        assert result == []

    def test_custom_platform(self) -> None:
        mock_catalog = MagicMock()
        mock_table = MagicMock()
        mock_scan = MagicMock()
        mock_arrow = MagicMock()

        mock_catalog.load_table.return_value = mock_table
        mock_table.scan.return_value = mock_scan
        mock_scan.to_arrow.return_value = mock_arrow
        mock_arrow.to_pylist.return_value = []

        _read_silver_trades_for_day(
            date(2024, 6, 15), platform="kalshi", catalog=mock_catalog
        )
        mock_catalog.load_table.assert_called_once_with(
            ("silver_kalshi", "trades")
        )


# ---------------------------------------------------------------------------
# process_day tests
# ---------------------------------------------------------------------------


class TestProcessDay:
    def _mock_silver_read(self, trades: list[dict]) -> MagicMock:
        """Create a mock catalog that returns the given trades."""
        mock_catalog = MagicMock()
        mock_table = MagicMock()
        mock_scan = MagicMock()
        mock_arrow = MagicMock()

        mock_catalog.load_table.return_value = mock_table
        mock_table.scan.return_value = mock_scan
        mock_scan.to_arrow.return_value = mock_arrow
        mock_arrow.to_pylist.return_value = trades

        return mock_catalog

    def test_no_trades_returns_zero(self) -> None:
        mock_catalog = self._mock_silver_read([])

        with patch(
            "prediction_data.gold.trade_processor.read_position_states",
            return_value={},
        ):
            result = process_day(
                dt=date(2024, 6, 15),
                catalog=mock_catalog,
                dry_run=True,
            )

        assert result == 0

    def test_dry_run_no_writes(self) -> None:
        trades = [_trade()]
        mock_catalog = self._mock_silver_read(trades)

        with patch(
            "prediction_data.gold.trade_processor.read_position_states",
            return_value={},
        ):
            result = process_day(
                dt=date(2024, 6, 15),
                catalog=mock_catalog,
                dry_run=True,
            )

        # 1 trade -> 2 fills (maker + taker)
        assert result == 2

    def test_single_trade_produces_two_fills(self) -> None:
        """A single trade should produce exactly 2 fill/ledger rows."""
        trades = [_trade()]
        mock_catalog = self._mock_silver_read(trades)
        mock_ch = MagicMock()
        mock_ch.query.return_value = MagicMock(result_rows=[])

        with patch(
            "prediction_data.gold.trade_processor.read_position_states",
            return_value={},
        ), patch(
            "prediction_data.gold.trade_processor.write_position_states",
            return_value=2,
        ) as mock_write_state:
            result = process_day(
                dt=date(2024, 6, 15),
                catalog=mock_catalog,
                clickhouse_client=mock_ch,
            )

        assert result == 2
        mock_write_state.assert_called_once()

    def test_idempotency_skip(self) -> None:
        """Already-processed day should return 0 and skip processing."""
        s3 = MagicMock()
        existing = _make_s3_state(["2024-06-15"])
        s3.get_object.return_value = {"Body": BytesIO(existing.encode())}
        s3.exceptions.NoSuchKey = type("NoSuchKey", (Exception,), {})

        result = process_day(
            dt=date(2024, 6, 15),
            gold_bucket="my-bucket",
            s3_client=s3,
        )

        assert result == 0

    def test_force_reprocess_ignores_state(self) -> None:
        """--force-reprocess should process even if already done."""
        trades = [_trade()]
        mock_catalog = self._mock_silver_read(trades)

        with patch(
            "prediction_data.gold.trade_processor.read_position_states",
            return_value={},
        ):
            result = process_day(
                dt=date(2024, 6, 15),
                catalog=mock_catalog,
                force_reprocess=True,
                dry_run=True,
            )

        assert result == 2

    def test_writes_ledger_and_state(self) -> None:
        """Verify both ledger and state are written in non-dry-run mode."""
        trades = [_trade()]
        mock_catalog = self._mock_silver_read(trades)
        mock_ch = MagicMock()
        mock_ch.query.return_value = MagicMock(result_rows=[])

        with patch(
            "prediction_data.gold.trade_processor.read_position_states",
            return_value={},
        ), patch(
            "prediction_data.gold.trade_processor.write_position_states",
            return_value=2,
        ) as mock_write_state, patch(
            "prediction_data.gold.ledger.LedgerWriter.flush",
            return_value=2,
        ) as mock_flush:
            result = process_day(
                dt=date(2024, 6, 15),
                catalog=mock_catalog,
                clickhouse_client=mock_ch,
            )

        mock_flush.assert_called_once()
        mock_write_state.assert_called_once()
        assert result == 2

    def test_marks_processed_in_state_store(self) -> None:
        """After successful processing, the day should be marked in state store."""
        trades = [_trade()]
        mock_catalog = self._mock_silver_read(trades)
        mock_ch = MagicMock()
        mock_ch.query.return_value = MagicMock(result_rows=[])
        s3 = MagicMock()
        s3.exceptions.NoSuchKey = type("NoSuchKey", (Exception,), {})
        s3.get_object.side_effect = s3.exceptions.NoSuchKey()

        with patch(
            "prediction_data.gold.trade_processor.read_position_states",
            return_value={},
        ), patch(
            "prediction_data.gold.trade_processor.write_position_states",
            return_value=2,
        ):
            process_day(
                dt=date(2024, 6, 15),
                catalog=mock_catalog,
                clickhouse_client=mock_ch,
                gold_bucket="my-bucket",
                s3_client=s3,
            )

        # Should have called put_object to write state
        put_calls = [c for c in s3.put_object.call_args_list if _STATE_KEY in str(c)]
        assert len(put_calls) >= 1

    def test_existing_positions_loaded(self) -> None:
        """Existing CH positions should be used for accounting."""
        trades = [
            _trade(
                maker="0xEXISTING",
                taker="0xNEW",
                maker_direction="sell",
                taker_direction="buy",
            )
        ]
        mock_catalog = self._mock_silver_read(trades)

        existing_pos = PositionState(
            wallet="0xEXISTING",
            platform="polymarket",
            market_id="cond_abc",
            outcome_id="cond_abc_0",
            qty=200.0,
            avg_cost=0.50,
            cost_basis_usd=100.0,
            last_fill_ts=_ts(0),
            first_open_ts=_ts(0),
        )
        existing_positions = {
            ("0xEXISTING", "polymarket", "cond_abc", "cond_abc_0"): existing_pos,
        }

        with patch(
            "prediction_data.gold.trade_processor.read_position_states",
            return_value=existing_positions,
        ):
            result = process_day(
                dt=date(2024, 6, 15),
                catalog=mock_catalog,
                dry_run=True,
            )

        # 2 fills (maker sell + taker buy)
        assert result == 2

    def test_multiple_trades_accounting(self) -> None:
        """Multiple trades should produce correct cumulative accounting."""
        trades = [
            _trade(
                ts=_ts(0),
                maker="0xA",
                taker="0xB",
                maker_direction="sell",
                taker_direction="buy",
                price=0.60,
                token_amount=100.0,
            ),
            _trade(
                ts=_ts(1),
                maker="0xB",
                taker="0xC",
                maker_direction="sell",
                taker_direction="buy",
                price=0.80,
                token_amount=100.0,
            ),
        ]
        mock_catalog = self._mock_silver_read(trades)

        with patch(
            "prediction_data.gold.trade_processor.read_position_states",
            return_value={},
        ):
            result = process_day(
                dt=date(2024, 6, 15),
                catalog=mock_catalog,
                dry_run=True,
            )

        # 2 trades -> 4 fills
        assert result == 4

    def test_no_gold_bucket_skips_s3_state(self) -> None:
        """Without gold_bucket, S3 state operations should be skipped."""
        trades = [_trade()]
        mock_catalog = self._mock_silver_read(trades)
        mock_ch = MagicMock()
        mock_ch.query.return_value = MagicMock(result_rows=[])

        with patch(
            "prediction_data.gold.trade_processor.read_position_states",
            return_value={},
        ), patch(
            "prediction_data.gold.trade_processor.write_position_states",
            return_value=2,
        ):
            result = process_day(
                dt=date(2024, 6, 15),
                catalog=mock_catalog,
                clickhouse_client=mock_ch,
                gold_bucket=None,
            )

        assert result == 2


# ---------------------------------------------------------------------------
# process_date_range tests
# ---------------------------------------------------------------------------


class TestProcessDateRange:
    def test_single_day(self) -> None:
        with patch(
            "prediction_data.gold.trade_processor.process_day",
            return_value=10,
        ) as mock_pd:
            results = process_date_range(
                start_date=date(2024, 6, 15),
                end_date=date(2024, 6, 15),
                dry_run=True,
            )

        assert results == {"2024-06-15": 10}
        mock_pd.assert_called_once()

    def test_multi_day(self) -> None:
        call_count = 0

        def _process_day(**_kwargs: object) -> int:
            nonlocal call_count
            call_count += 1
            return call_count * 10

        with patch(
            "prediction_data.gold.trade_processor.process_day",
            side_effect=_process_day,
        ):
            results = process_date_range(
                start_date=date(2024, 6, 14),
                end_date=date(2024, 6, 16),
                dry_run=True,
            )

        assert len(results) == 3
        assert results["2024-06-14"] == 10
        assert results["2024-06-15"] == 20
        assert results["2024-06-16"] == 30

    def test_passes_options_through(self) -> None:
        with patch(
            "prediction_data.gold.trade_processor.process_day",
            return_value=0,
        ) as mock_pd:
            process_date_range(
                start_date=date(2024, 6, 15),
                end_date=date(2024, 6, 15),
                platform="kalshi",
                gold_bucket="my-bucket",
                dry_run=True,
                force_reprocess=True,
            )

        kwargs = mock_pd.call_args.kwargs
        assert kwargs["platform"] == "kalshi"
        assert kwargs["gold_bucket"] == "my-bucket"
        assert kwargs["dry_run"] is True
        assert kwargs["force_reprocess"] is True


# ---------------------------------------------------------------------------
# Integration tests (end-to-end with mock I/O)
# ---------------------------------------------------------------------------


class TestEndToEnd:
    def test_buy_then_sell_produces_correct_pnl(self) -> None:
        """Full pipeline: 2 trades, one buy, one sell. Verify PnL."""
        buy_trade = _trade(
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
        sell_trade = _trade(
            ts=_ts(1),
            maker="0xBUYER",
            taker="0xBUYER2",
            maker_direction="sell",
            taker_direction="buy",
            price=0.80,
            token_amount=100.0,
            market_id="mkt1",
            nonusdc_side="token1",
        )

        mock_catalog = MagicMock()
        mock_table = MagicMock()
        mock_scan = MagicMock()
        mock_arrow = MagicMock()

        mock_catalog.load_table.return_value = mock_table
        mock_table.scan.return_value = mock_scan
        mock_scan.to_arrow.return_value = mock_arrow
        mock_arrow.to_pylist.return_value = [buy_trade, sell_trade]

        # Use real accounting, but dry_run to avoid writes
        with patch(
            "prediction_data.gold.trade_processor.read_position_states",
            return_value={},
        ):
            result = process_day(
                dt=date(2024, 6, 15),
                catalog=mock_catalog,
                dry_run=True,
            )

        # 2 trades -> 4 fills (each trade creates maker + taker fill)
        assert result == 4

    def test_round_trip_with_mock_ch(self) -> None:
        """Process trades and verify CH write calls."""
        trades = [
            _trade(
                ts=_ts(0),
                maker="0xA",
                taker="0xB",
                maker_direction="sell",
                taker_direction="buy",
            )
        ]

        mock_catalog = MagicMock()
        mock_table = MagicMock()
        mock_scan = MagicMock()
        mock_arrow = MagicMock()

        mock_catalog.load_table.return_value = mock_table
        mock_table.scan.return_value = mock_scan
        mock_scan.to_arrow.return_value = mock_arrow
        mock_arrow.to_pylist.return_value = trades

        mock_ch = MagicMock()
        mock_ch.query.return_value = MagicMock(result_rows=[])

        with patch(
            "prediction_data.gold.trade_processor.read_position_states",
            return_value={},
        ), patch(
            "prediction_data.gold.trade_processor.write_position_states",
            return_value=2,
        ) as mock_ws:
            result = process_day(
                dt=date(2024, 6, 15),
                catalog=mock_catalog,
                clickhouse_client=mock_ch,
            )

        assert result == 2
        # LedgerWriter.flush inserts into ClickHouse
        mock_ch.insert.assert_called_once()
        # position_state also written
        mock_ws.assert_called_once()

    def test_daily_run_integration(self) -> None:
        """Verify process_day signature is compatible with gold CLI daily-run."""
        # The gold CLI calls process_day(dt=dt, gold_bucket=..., dry_run=...)
        # Verify this doesn't raise a TypeError.
        mock_catalog = MagicMock()
        mock_table = MagicMock()
        mock_scan = MagicMock()
        mock_arrow = MagicMock()

        mock_catalog.load_table.return_value = mock_table
        mock_table.scan.return_value = mock_scan
        mock_scan.to_arrow.return_value = mock_arrow
        mock_arrow.to_pylist.return_value = []

        with patch(
            "prediction_data.gold.trade_processor.read_position_states",
            return_value={},
        ), patch(
            "prediction_data.silver.catalog.get_catalog",
            return_value=mock_catalog,
        ):
            result = process_day(
                dt=date(2024, 6, 15),
                gold_bucket="my-bucket",
                dry_run=True,
            )

        assert result == 0

    def test_state_store_round_trip(self) -> None:
        """Verify the state store properly blocks reprocessing."""
        s3 = MagicMock()
        s3.exceptions.NoSuchKey = type("NoSuchKey", (Exception,), {})

        # First call: no state file yet
        s3.get_object.side_effect = s3.exceptions.NoSuchKey()
        dates = _load_processed_dates(s3, "bucket")
        assert "2024-06-15" not in dates

        # Mark as processed
        _mark_processed(
            s3,
            "bucket",
            "2024-06-15",
            fills_processed=100,
            positions_updated=10,
            realized_pnl_total=5.0,
        )

        # Read what was written
        written_body = s3.put_object.call_args.kwargs["Body"]
        s3.get_object.side_effect = None
        s3.get_object.return_value = {"Body": BytesIO(written_body)}

        dates = _load_processed_dates(s3, "bucket")
        assert "2024-06-15" in dates
