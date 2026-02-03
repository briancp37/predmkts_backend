"""Tests for the `gold compute-marks` CLI command."""

from __future__ import annotations

from datetime import date
from unittest.mock import patch

from typer.testing import CliRunner

from prediction_data.cli.gold import app

runner = CliRunner()


class TestComputeMarksCli:
    """Tests for `prediction-data gold compute-marks`."""

    def test_single_date_dry_run(self) -> None:
        with patch(
            "prediction_data.gold.market_marks.compute_market_marks", return_value=42
        ) as mock_compute:
            result = runner.invoke(app, ["compute-marks", "--dt", "2024-06-15", "--dry-run"])

        assert result.exit_code == 0
        assert "42 rows" in result.output
        assert "dry-run" in result.output
        mock_compute.assert_called_once_with(
            platform="polymarket",
            dt=date(2024, 6, 15),
            gold_bucket=None,
            dry_run=True,
        )

    def test_date_range(self) -> None:
        with patch(
            "prediction_data.gold.market_marks.compute_market_marks", return_value=10
        ) as mock_compute:
            result = runner.invoke(
                app,
                [
                    "compute-marks",
                    "--start-date", "2024-06-01",
                    "--end-date", "2024-06-03",
                    "--dry-run",
                ],
            )

        assert result.exit_code == 0
        assert mock_compute.call_count == 3
        assert "30 rows across 3 day(s)" in result.output

    def test_dt_and_range_conflict(self) -> None:
        result = runner.invoke(
            app,
            ["compute-marks", "--dt", "2024-06-01", "--start-date", "2024-06-01", "--end-date", "2024-06-02"],
        )
        assert result.exit_code == 1
        assert "cannot be combined" in result.output

    def test_no_dates_provided(self) -> None:
        result = runner.invoke(app, ["compute-marks"])
        assert result.exit_code == 1
        assert "provide --dt" in result.output

    def test_start_after_end(self) -> None:
        result = runner.invoke(
            app,
            ["compute-marks", "--start-date", "2024-06-10", "--end-date", "2024-06-01"],
        )
        assert result.exit_code == 1
        assert "must be <=" in result.output

    def test_partial_failure_reports_errors(self) -> None:
        call_count = 0

        def mock_compute(**kwargs):  # type: ignore[no-untyped-def]
            nonlocal call_count
            call_count += 1
            if call_count == 2:
                raise RuntimeError("Silver table missing")
            return 5

        with patch("prediction_data.gold.market_marks.compute_market_marks", side_effect=mock_compute):
            result = runner.invoke(
                app,
                [
                    "compute-marks",
                    "--start-date", "2024-06-01",
                    "--end-date", "2024-06-03",
                    "--dry-run",
                ],
            )

        assert result.exit_code == 1
        assert "FAILED" in result.output
        assert "1 day(s) failed" in result.output

    def test_custom_platform(self) -> None:
        with patch(
            "prediction_data.gold.market_marks.compute_market_marks", return_value=5
        ) as mock_compute:
            result = runner.invoke(
                app, ["compute-marks", "--dt", "2024-06-15", "--platform", "kalshi", "--dry-run"]
            )

        assert result.exit_code == 0
        mock_compute.assert_called_once_with(
            platform="kalshi",
            dt=date(2024, 6, 15),
            gold_bucket=None,
            dry_run=True,
        )


class TestLoadMarksChCli:
    """Tests for `prediction-data gold load-marks-ch`."""

    def test_dry_run(self) -> None:
        with patch("prediction_data.cli.gold.get_settings") as mock_settings:
            mock_settings.return_value.gold_bucket = "my-bucket"
            result = runner.invoke(app, ["load-marks-ch", "--dry-run"])
        assert result.exit_code == 0
        assert "dry-run" in result.output

    def test_no_gold_bucket_errors(self) -> None:
        with patch("prediction_data.cli.gold.get_settings") as mock_settings:
            mock_settings.return_value.gold_bucket = ""
            result = runner.invoke(app, ["load-marks-ch"])
        assert result.exit_code == 1
        assert "GOLD_BUCKET" in result.output

    def test_custom_lookback(self) -> None:
        with patch(
            "prediction_data.gold.market_marks.load_marks_to_clickhouse_from_s3",
            return_value=100,
        ) as mock_load:
            with patch("prediction_data.cli.gold.get_settings") as mock_settings:
                mock_settings.return_value.gold_bucket = "my-bucket"
                result = runner.invoke(app, ["load-marks-ch", "--lookback-days", "30"])

        assert result.exit_code == 0
        assert "100 rows" in result.output
        mock_load.assert_called_once_with(
            gold_bucket="my-bucket",
            lookback_days=30,
        )
