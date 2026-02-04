"""Tests for the `gold daily-run` CLI command."""

from __future__ import annotations

from datetime import date
from unittest.mock import MagicMock, patch

from typer.testing import CliRunner

from prediction_data.cli.gold import app

runner = CliRunner()


class TestDailyRunCli:
    """Tests for `prediction-data gold daily-run`."""

    def test_help(self) -> None:
        result = runner.invoke(app, ["daily-run", "--help"])
        assert result.exit_code == 0
        assert "daily-run" in result.output.lower()
        assert "--dry-run" in result.output
        assert "--stop-on-error" in result.output

    @patch("prediction_data.cli.gold._emit_daily_run_metadata")
    @patch("prediction_data.cli.gold._run_daily_step")
    @patch("prediction_data.cli.gold.get_settings")
    def test_all_steps_succeed(
        self,
        mock_settings: MagicMock,
        mock_step: MagicMock,
        mock_metadata: MagicMock,
    ) -> None:
        mock_settings.return_value.gold_bucket = "test-gold"
        mock_step.return_value = 10

        result = runner.invoke(app, ["daily-run", "--dt", "2024-06-15", "--dry-run"])

        assert result.exit_code == 0
        # 4 steps, each returning 10 rows
        assert mock_step.call_count == 4
        assert "Steps succeeded: 4/4" in result.output
        assert "Total rows: 40" in result.output

        # Verify steps called in order.
        step_names = [call.args[0] for call in mock_step.call_args_list]
        assert step_names == [
            "load-dims",
            "process-trades",
            "compute-marks",
            "compute-wallet-metrics",
        ]

        # Verify date passed correctly.
        for call in mock_step.call_args_list:
            assert call.args[1] == date(2024, 6, 15)

    @patch("prediction_data.cli.gold._emit_daily_run_metadata")
    @patch("prediction_data.cli.gold._run_daily_step")
    @patch("prediction_data.cli.gold.get_settings")
    def test_fail_forward_continues_on_error(
        self,
        mock_settings: MagicMock,
        mock_step: MagicMock,
        mock_metadata: MagicMock,
    ) -> None:
        """Verify that failing step does not stop subsequent steps."""
        mock_settings.return_value.gold_bucket = "test-gold"

        call_count = 0

        def side_effect(step_name: str, *args: object, **kwargs: object) -> int:
            nonlocal call_count
            call_count += 1
            if step_name == "process-trades":
                raise NotImplementedError("not implemented yet")
            return 5

        mock_step.side_effect = side_effect

        result = runner.invoke(app, ["daily-run", "--dt", "2024-06-15", "--dry-run"])

        # Should exit 1 because of failure.
        assert result.exit_code == 1
        # But all 4 steps should be attempted.
        assert mock_step.call_count == 4
        assert "Steps succeeded: 3/4" in result.output
        assert "FAILED" in result.output
        assert "process-trades" in result.output

    @patch("prediction_data.cli.gold._emit_daily_run_metadata")
    @patch("prediction_data.cli.gold._run_daily_step")
    @patch("prediction_data.cli.gold.get_settings")
    def test_stop_on_error_halts(
        self,
        mock_settings: MagicMock,
        mock_step: MagicMock,
        mock_metadata: MagicMock,
    ) -> None:
        """Verify --stop-on-error halts on first failure."""
        mock_settings.return_value.gold_bucket = "test-gold"

        def side_effect(step_name: str, *args: object, **kwargs: object) -> int:
            if step_name == "process-trades":
                raise RuntimeError("CH down")
            return 5

        mock_step.side_effect = side_effect

        result = runner.invoke(
            app,
            ["daily-run", "--dt", "2024-06-15", "--dry-run", "--stop-on-error"],
        )

        assert result.exit_code == 1
        # Only 2 steps attempted: load-dims (success) and process-trades (fail).
        assert mock_step.call_count == 2
        assert "Halting due to --stop-on-error" in result.output

    @patch("prediction_data.cli.gold._emit_daily_run_metadata")
    @patch("prediction_data.cli.gold._run_daily_step")
    @patch("prediction_data.cli.gold.get_settings")
    def test_defaults_to_yesterday(
        self,
        mock_settings: MagicMock,
        mock_step: MagicMock,
        mock_metadata: MagicMock,
    ) -> None:
        """When no --dt, should default to yesterday UTC."""
        from datetime import UTC, datetime, timedelta

        mock_settings.return_value.gold_bucket = "test-gold"
        mock_step.return_value = 0

        result = runner.invoke(app, ["daily-run", "--dry-run"])

        assert result.exit_code == 0
        expected_date = datetime.now(UTC).date() - timedelta(days=1)
        # Verify the date appears in output.
        assert str(expected_date) in result.output
        # Verify the date was passed to the step function.
        for call in mock_step.call_args_list:
            assert call.args[1] == expected_date

    @patch("prediction_data.cli.gold._emit_daily_run_metadata")
    @patch("prediction_data.cli.gold._run_daily_step")
    @patch("prediction_data.cli.gold.get_settings")
    def test_metadata_called_on_success(
        self,
        mock_settings: MagicMock,
        mock_step: MagicMock,
        mock_metadata: MagicMock,
    ) -> None:
        mock_settings.return_value.gold_bucket = "test-gold"
        mock_step.return_value = 10

        result = runner.invoke(app, ["daily-run", "--dt", "2024-06-15", "--dry-run"])

        assert result.exit_code == 0
        mock_metadata.assert_called_once()
        call_kwargs = mock_metadata.call_args
        assert call_kwargs.kwargs["total_rows"] == 40
        assert call_kwargs.kwargs["has_failures"] is False

    @patch("prediction_data.cli.gold._emit_daily_run_metadata")
    @patch("prediction_data.cli.gold._run_daily_step")
    @patch("prediction_data.cli.gold.get_settings")
    def test_metadata_called_on_failure(
        self,
        mock_settings: MagicMock,
        mock_step: MagicMock,
        mock_metadata: MagicMock,
    ) -> None:
        mock_settings.return_value.gold_bucket = "test-gold"
        mock_step.side_effect = RuntimeError("boom")

        result = runner.invoke(app, ["daily-run", "--dt", "2024-06-15", "--dry-run"])

        assert result.exit_code == 1
        mock_metadata.assert_called_once()
        call_kwargs = mock_metadata.call_args
        assert call_kwargs.kwargs["has_failures"] is True


class TestRunDailyStep:
    """Unit tests for _run_daily_step."""

    @patch("prediction_data.gold.dimensions.load_dim_category", return_value=5)
    @patch("prediction_data.gold.dimensions.load_dim_event", return_value=10)
    @patch("prediction_data.gold.dimensions.load_dim_wallet", return_value=20)
    @patch("prediction_data.gold.dimensions.load_dim_outcome", return_value=15)
    @patch("prediction_data.gold.dimensions.load_dim_market", return_value=100)
    @patch("prediction_data.gold.dimensions.load_dim_platform", return_value=2)
    def test_load_dims_step(
        self,
        mock_platform: MagicMock,
        mock_market: MagicMock,
        mock_outcome: MagicMock,
        mock_wallet: MagicMock,
        mock_event: MagicMock,
        mock_category: MagicMock,
    ) -> None:
        from prediction_data.cli.gold import _run_daily_step

        rows = _run_daily_step(
            "load-dims", date(2024, 6, 15), gold_bucket="test-gold", dry_run=True
        )
        assert rows == 152  # 2 + 100 + 15 + 20 + 10 + 5
        mock_platform.assert_called_once_with(gold_bucket="test-gold", dry_run=True)
        mock_market.assert_called_once_with(gold_bucket="test-gold", dry_run=True)

    def test_process_trades_not_implemented(self) -> None:
        from prediction_data.cli.gold import _run_daily_step

        import pytest

        with pytest.raises(NotImplementedError, match="not yet implemented"):
            _run_daily_step(
                "process-trades", date(2024, 6, 15), gold_bucket="test-gold"
            )

    @patch("prediction_data.gold.market_marks.compute_market_marks", return_value=42)
    def test_compute_marks_step(self, mock_marks: MagicMock) -> None:
        from prediction_data.cli.gold import _run_daily_step

        rows = _run_daily_step(
            "compute-marks",
            date(2024, 6, 15),
            gold_bucket="test-gold",
            dry_run=True,
        )
        assert rows == 42
        mock_marks.assert_called_once_with(
            platform="polymarket",
            dt=date(2024, 6, 15),
            gold_bucket="test-gold",
            dry_run=True,
        )

    @patch(
        "prediction_data.gold.wallet_position_snapshot.compute_wallet_position_snapshot",
        return_value=5,
    )
    @patch("prediction_data.gold.wallet_mtm.compute_wallet_mtm", return_value=3)
    @patch("prediction_data.gold.wallet_pnl.compute_wallet_pnl", return_value=7)
    def test_compute_wallet_metrics_step(
        self,
        mock_pnl: MagicMock,
        mock_mtm: MagicMock,
        mock_snap: MagicMock,
    ) -> None:
        from prediction_data.cli.gold import _run_daily_step

        rows = _run_daily_step(
            "compute-wallet-metrics",
            date(2024, 6, 15),
            gold_bucket="test-gold",
            dry_run=True,
        )
        assert rows == 15  # 7 + 3 + 5
        mock_pnl.assert_called_once_with(
            dt=date(2024, 6, 15), gold_bucket="test-gold", dry_run=True
        )
        mock_mtm.assert_called_once_with(
            dt=date(2024, 6, 15), gold_bucket="test-gold", dry_run=True
        )
        mock_snap.assert_called_once_with(
            dt=date(2024, 6, 15), gold_bucket="test-gold", dry_run=True
        )

    def test_unknown_step_raises(self) -> None:
        from prediction_data.cli.gold import _run_daily_step

        import pytest

        with pytest.raises(ValueError, match="Unknown step"):
            _run_daily_step("bogus", date(2024, 6, 15))
