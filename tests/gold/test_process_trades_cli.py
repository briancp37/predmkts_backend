"""Tests for the `gold process-trades` CLI command."""

from __future__ import annotations

from datetime import date
from unittest.mock import patch

from typer.testing import CliRunner

from prediction_data.cli.gold import app

runner = CliRunner()


class TestProcessTradesCli:
    """Tests for `prediction-data gold process-trades`."""

    def test_help(self) -> None:
        result = runner.invoke(app, ["process-trades", "--help"])
        assert result.exit_code == 0
        assert "--dt" in result.output
        assert "--start-date" in result.output
        assert "--end-date" in result.output
        assert "--force-reprocess" in result.output
        assert "--dry-run" in result.output

    def test_single_date_dry_run(self) -> None:
        with patch(
            "prediction_data.gold.trade_processor.process_day", return_value=50
        ) as mock_process:
            result = runner.invoke(
                app, ["process-trades", "--dt", "2024-06-15", "--dry-run"]
            )

        assert result.exit_code == 0
        assert "50 fills processed" in result.output
        assert "dry-run" in result.output
        assert "Total: 50 fills across 1 day(s)" in result.output
        mock_process.assert_called_once_with(
            dt=date(2024, 6, 15),
            gold_bucket=None,
            dry_run=True,
            force_reprocess=False,
        )

    def test_single_date_force_reprocess(self) -> None:
        with patch(
            "prediction_data.gold.trade_processor.process_day", return_value=100
        ) as mock_process:
            result = runner.invoke(
                app,
                ["process-trades", "--dt", "2024-06-15", "--force-reprocess", "--dry-run"],
            )

        assert result.exit_code == 0
        assert "force-reprocess" in result.output
        mock_process.assert_called_once_with(
            dt=date(2024, 6, 15),
            gold_bucket=None,
            dry_run=True,
            force_reprocess=True,
        )

    def test_date_range(self) -> None:
        with patch(
            "prediction_data.gold.trade_processor.process_date_range",
            return_value={"2024-06-01": 20, "2024-06-02": 30, "2024-06-03": 10},
        ) as mock_range:
            result = runner.invoke(
                app,
                [
                    "process-trades",
                    "--start-date", "2024-06-01",
                    "--end-date", "2024-06-03",
                    "--dry-run",
                ],
            )

        assert result.exit_code == 0
        assert "Total: 60 fills across 3 day(s)" in result.output
        assert "2024-06-01: 20 fills" in result.output
        assert "2024-06-02: 30 fills" in result.output
        assert "2024-06-03: 10 fills" in result.output
        mock_range.assert_called_once_with(
            start_date=date(2024, 6, 1),
            end_date=date(2024, 6, 3),
            gold_bucket=None,
            dry_run=True,
            force_reprocess=False,
        )

    def test_date_range_force_reprocess(self) -> None:
        with patch(
            "prediction_data.gold.trade_processor.process_date_range",
            return_value={"2024-06-01": 15},
        ) as mock_range:
            result = runner.invoke(
                app,
                [
                    "process-trades",
                    "--start-date", "2024-06-01",
                    "--end-date", "2024-06-01",
                    "--force-reprocess",
                    "--dry-run",
                ],
            )

        assert result.exit_code == 0
        mock_range.assert_called_once_with(
            start_date=date(2024, 6, 1),
            end_date=date(2024, 6, 1),
            gold_bucket=None,
            dry_run=True,
            force_reprocess=True,
        )

    def test_dt_and_range_conflict(self) -> None:
        result = runner.invoke(
            app,
            [
                "process-trades",
                "--dt", "2024-06-01",
                "--start-date", "2024-06-01",
                "--end-date", "2024-06-02",
            ],
        )
        assert result.exit_code == 1
        assert "cannot be combined" in result.output

    def test_no_dates_provided(self) -> None:
        result = runner.invoke(app, ["process-trades"])
        assert result.exit_code == 1
        assert "provide --dt" in result.output

    def test_start_after_end(self) -> None:
        result = runner.invoke(
            app,
            [
                "process-trades",
                "--start-date", "2024-06-10",
                "--end-date", "2024-06-01",
            ],
        )
        assert result.exit_code == 1
        assert "must be <=" in result.output

    def test_single_date_with_gold_bucket(self) -> None:
        with patch("prediction_data.cli.gold.get_settings") as mock_settings:
            mock_settings.return_value.gold_bucket = "my-gold-bucket"
            with patch(
                "prediction_data.gold.trade_processor.process_day", return_value=200
            ) as mock_process:
                result = runner.invoke(
                    app, ["process-trades", "--dt", "2024-06-15", "--dry-run"]
                )

        assert result.exit_code == 0
        mock_process.assert_called_once_with(
            dt=date(2024, 6, 15),
            gold_bucket="my-gold-bucket",
            dry_run=True,
            force_reprocess=False,
        )

    def test_date_range_with_gold_bucket(self) -> None:
        with patch("prediction_data.cli.gold.get_settings") as mock_settings:
            mock_settings.return_value.gold_bucket = "my-gold-bucket"
            with patch(
                "prediction_data.gold.trade_processor.process_date_range",
                return_value={"2024-06-01": 10},
            ) as mock_range:
                result = runner.invoke(
                    app,
                    [
                        "process-trades",
                        "--start-date", "2024-06-01",
                        "--end-date", "2024-06-01",
                        "--dry-run",
                    ],
                )

        assert result.exit_code == 0
        mock_range.assert_called_once_with(
            start_date=date(2024, 6, 1),
            end_date=date(2024, 6, 1),
            gold_bucket="my-gold-bucket",
            dry_run=True,
            force_reprocess=False,
        )

    def test_zero_fills_single_date(self) -> None:
        with patch(
            "prediction_data.gold.trade_processor.process_day", return_value=0
        ):
            result = runner.invoke(
                app, ["process-trades", "--dt", "2024-06-15", "--dry-run"]
            )

        assert result.exit_code == 0
        assert "0 fills processed" in result.output
        assert "Total: 0 fills across 1 day(s)" in result.output
