"""Tests for the unified compute-wallet-metrics CLI command and integration test."""

from __future__ import annotations

from datetime import date
from unittest.mock import MagicMock, patch

from typer.testing import CliRunner

from prediction_data.gold.wallet_mtm import compute_mtm_for_day
from prediction_data.gold.wallet_pnl import aggregate_pnl_for_day
from prediction_data.gold.wallet_position_snapshot import compute_snapshot_for_day

runner = CliRunner()


# ---------------------------------------------------------------------------
# CLI tests for compute-wallet-metrics
# ---------------------------------------------------------------------------


class TestComputeWalletMetricsCli:
    def test_cli_help(self) -> None:
        from prediction_data.cli.gold import app

        result = runner.invoke(app, ["compute-wallet-metrics", "--help"])
        assert result.exit_code == 0
        assert "wallet metrics" in result.output.lower()

    def test_cli_requires_date(self) -> None:
        from prediction_data.cli.gold import app

        result = runner.invoke(app, ["compute-wallet-metrics"])
        assert result.exit_code == 1

    def test_cli_dt_conflicts_with_range(self) -> None:
        from prediction_data.cli.gold import app

        result = runner.invoke(
            app,
            [
                "compute-wallet-metrics",
                "--dt", "2024-06-15",
                "--start-date", "2024-06-01",
                "--end-date", "2024-06-30",
            ],
        )
        assert result.exit_code == 1

    @patch("prediction_data.cli.gold.get_settings")
    @patch("prediction_data.gold.wallet_position_snapshot.compute_wallet_position_snapshot")
    @patch("prediction_data.gold.wallet_mtm.compute_wallet_mtm")
    @patch("prediction_data.gold.wallet_pnl.compute_wallet_pnl")
    def test_cli_single_date_dry_run(
        self,
        mock_pnl: MagicMock,
        mock_mtm: MagicMock,
        mock_snap: MagicMock,
        mock_settings: MagicMock,
    ) -> None:
        from prediction_data.cli.gold import app

        mock_settings.return_value.gold_bucket = "test-gold"
        mock_pnl.return_value = 3
        mock_mtm.return_value = 2
        mock_snap.return_value = 5

        result = runner.invoke(
            app, ["compute-wallet-metrics", "--dt", "2024-06-15", "--dry-run"]
        )
        assert result.exit_code == 0
        assert "pnl=3" in result.output
        assert "mtm=2" in result.output
        assert "snapshots=5" in result.output
        mock_pnl.assert_called_once()
        mock_mtm.assert_called_once()
        mock_snap.assert_called_once()

    @patch("prediction_data.cli.gold.get_settings")
    @patch("prediction_data.gold.wallet_position_snapshot.compute_wallet_position_snapshot")
    @patch("prediction_data.gold.wallet_mtm.compute_wallet_mtm")
    @patch("prediction_data.gold.wallet_pnl.compute_wallet_pnl")
    def test_cli_date_range(
        self,
        mock_pnl: MagicMock,
        mock_mtm: MagicMock,
        mock_snap: MagicMock,
        mock_settings: MagicMock,
    ) -> None:
        from prediction_data.cli.gold import app

        mock_settings.return_value.gold_bucket = "test-gold"
        mock_pnl.return_value = 1
        mock_mtm.return_value = 1
        mock_snap.return_value = 1

        result = runner.invoke(
            app,
            [
                "compute-wallet-metrics",
                "--start-date", "2024-06-15",
                "--end-date", "2024-06-16",
                "--dry-run",
            ],
        )
        assert result.exit_code == 0
        # 2 days
        assert "2 day(s)" in result.output
        assert mock_pnl.call_count == 2
        assert mock_mtm.call_count == 2
        assert mock_snap.call_count == 2

    @patch("prediction_data.cli.gold.get_settings")
    @patch("prediction_data.gold.wallet_position_snapshot.compute_wallet_position_snapshot")
    @patch("prediction_data.gold.wallet_mtm.compute_wallet_mtm")
    @patch("prediction_data.gold.wallet_pnl.compute_wallet_pnl")
    def test_cli_partial_failure_reports_errors(
        self,
        mock_pnl: MagicMock,
        mock_mtm: MagicMock,
        mock_snap: MagicMock,
        mock_settings: MagicMock,
    ) -> None:
        from prediction_data.cli.gold import app

        mock_settings.return_value.gold_bucket = "test-gold"
        mock_pnl.return_value = 3
        mock_mtm.side_effect = RuntimeError("CH down")
        mock_snap.return_value = 0

        result = runner.invoke(
            app, ["compute-wallet-metrics", "--dt", "2024-06-15", "--dry-run"]
        )
        assert result.exit_code == 1
        assert "FAILED" in result.output


# ---------------------------------------------------------------------------
# Integration test: ledger → pnl + mtm + snapshots (pure functions)
# ---------------------------------------------------------------------------


class TestWalletMetricsIntegration:
    """End-to-end test using the pure aggregation functions.

    Simulates: a wallet has 2 fills (buy then sell) on the same day.
    Verifies PnL, MTM, and snapshot outputs are consistent.
    """

    def test_full_pipeline_single_day(self) -> None:
        dt = date(2024, 6, 15)
        wallet = "0xINTEGRATION"

        # --- Simulate ledger rows (as if from wallet_position_ledger) ---
        ledger_rows = [
            {
                "wallet": wallet,
                "qty_delta": 100.0,
                "price": 0.50,
                "fees_usd": 0.10,
                "realized_pnl_this_fill_usd": 0.0,  # buy, no realized PnL
            },
            {
                "wallet": wallet,
                "qty_delta": -60.0,
                "price": 0.70,
                "fees_usd": 0.05,
                "realized_pnl_this_fill_usd": 12.0,  # sell at profit
            },
        ]

        # --- PnL aggregation ---
        pnl_table = aggregate_pnl_for_day(ledger_rows, dt)
        assert pnl_table.num_rows == 1
        pnl_row = pnl_table.to_pylist()[0]
        assert pnl_row["wallet"] == wallet
        assert pnl_row["trades_count"] == 2
        assert abs(pnl_row["realized_pnl_usd"] - 12.0) < 1e-9
        assert abs(pnl_row["fees_usd"] - 0.15) < 1e-9
        # volume = |100*0.50| + |-60*0.70| = 50 + 42 = 92
        assert abs(pnl_row["volume_usd"] - 92.0) < 1e-9
        assert pnl_row["wins"] == 1  # the sell with +12 realized
        assert pnl_row["losses"] == 0

        # --- Positions after fills: 40 shares remaining at avg_cost ~0.50 ---
        positions = [
            {
                "wallet": wallet,
                "platform": "polymarket",
                "market_id": "mkt_abc",
                "outcome_id": "tok_yes",
                "qty": 40.0,
                "avg_cost": 0.50,
            },
        ]
        marks = {("polymarket", "mkt_abc", "tok_yes"): 0.65}

        # --- MTM ---
        mtm_table = compute_mtm_for_day(positions, marks, dt)
        assert mtm_table.num_rows == 1
        mtm_row = mtm_table.to_pylist()[0]
        assert mtm_row["wallet"] == wallet
        assert abs(mtm_row["equity_usd"] - 26.0) < 1e-9  # 40 * 0.65
        assert abs(mtm_row["unrealized_pnl_usd"] - 6.0) < 1e-9  # 40*(0.65-0.50)
        assert abs(mtm_row["exposure_gross_usd"] - 26.0) < 1e-9
        assert abs(mtm_row["exposure_net_usd"] - 26.0) < 1e-9
        assert mtm_row["positions_count"] == 1
        assert mtm_row["missing_marks_count"] == 0

        # --- Position snapshot ---
        snap_table = compute_snapshot_for_day(positions, marks, dt)
        assert snap_table.num_rows == 1
        snap_row = snap_table.to_pylist()[0]
        assert snap_row["wallet"] == wallet
        assert snap_row["platform"] == "polymarket"
        assert snap_row["market_id"] == "mkt_abc"
        assert snap_row["qty"] == 40.0
        assert abs(snap_row["mark_price"] - 0.65) < 1e-9
        assert abs(snap_row["position_value_usd"] - 26.0) < 1e-9
        assert abs(snap_row["unrealized_pnl_usd"] - 6.0) < 1e-9

        # --- Cross-table consistency ---
        # MTM equity should match snapshot position_value_usd (single position)
        assert abs(mtm_row["equity_usd"] - snap_row["position_value_usd"]) < 1e-9
        assert abs(mtm_row["unrealized_pnl_usd"] - snap_row["unrealized_pnl_usd"]) < 1e-9

    def test_multi_wallet_multi_position(self) -> None:
        """Two wallets, one with two positions — verifies grouping."""
        dt = date(2024, 6, 15)

        # Wallet A: 2 fills on 2 different positions
        # Wallet B: 1 fill
        ledger_rows = [
            {"wallet": "0xA", "qty_delta": 50.0, "price": 0.40, "fees_usd": 0.01, "realized_pnl_this_fill_usd": 0.0},
            {"wallet": "0xA", "qty_delta": 30.0, "price": 0.60, "fees_usd": 0.02, "realized_pnl_this_fill_usd": 5.0},
            {"wallet": "0xB", "qty_delta": 20.0, "price": 0.55, "fees_usd": 0.01, "realized_pnl_this_fill_usd": -2.0},
        ]

        pnl = aggregate_pnl_for_day(ledger_rows, dt)
        assert pnl.num_rows == 2
        by_wallet = {r["wallet"]: r for r in pnl.to_pylist()}
        assert by_wallet["0xA"]["trades_count"] == 2
        assert by_wallet["0xB"]["trades_count"] == 1
        assert by_wallet["0xB"]["losses"] == 1

        # Positions for MTM/snapshot
        positions = [
            {"wallet": "0xA", "platform": "polymarket", "market_id": "m1", "outcome_id": "t1", "qty": 50.0, "avg_cost": 0.40},
            {"wallet": "0xA", "platform": "polymarket", "market_id": "m2", "outcome_id": "t2", "qty": 30.0, "avg_cost": 0.60},
            {"wallet": "0xB", "platform": "polymarket", "market_id": "m3", "outcome_id": "t3", "qty": 20.0, "avg_cost": 0.55},
        ]
        marks = {
            ("polymarket", "m1", "t1"): 0.45,
            ("polymarket", "m2", "t2"): 0.70,
            ("polymarket", "m3", "t3"): 0.50,
        }

        mtm = compute_mtm_for_day(positions, marks, dt)
        assert mtm.num_rows == 2

        snap = compute_snapshot_for_day(positions, marks, dt)
        assert snap.num_rows == 3  # 2 positions for A + 1 for B

        # Verify MTM aggregation matches sum of snapshot values per wallet
        mtm_by_wallet = {r["wallet"]: r for r in mtm.to_pylist()}
        snap_by_wallet: dict[str, float] = {}
        for r in snap.to_pylist():
            snap_by_wallet[r["wallet"]] = snap_by_wallet.get(r["wallet"], 0.0) + r["position_value_usd"]

        for w in ("0xA", "0xB"):
            assert abs(mtm_by_wallet[w]["equity_usd"] - snap_by_wallet[w]) < 1e-9
