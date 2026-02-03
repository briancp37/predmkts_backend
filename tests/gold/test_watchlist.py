"""Tests for Gold watchlist module."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock, call

import pytest

from prediction_data.gold.watchlist import (
    TABLE,
    add_wallet,
    list_wallets,
    remove_wallet,
)


class TestAddWallet:
    def test_inserts_active_row(self, mock_clickhouse_client: MagicMock) -> None:
        add_wallet("0xabc", clickhouse_client=mock_clickhouse_client)
        mock_clickhouse_client.insert.assert_called_once()
        args, kwargs = mock_clickhouse_client.insert.call_args
        assert args[0] == TABLE
        row = kwargs["data"][0]
        assert row[0] == "0xabc"
        # added_at is a datetime
        assert isinstance(row[1], datetime)
        # notes default empty
        assert row[2] == ""
        # active True
        assert row[3] is True

    def test_inserts_with_notes(self, mock_clickhouse_client: MagicMock) -> None:
        add_wallet("0xdef", notes="big trader", clickhouse_client=mock_clickhouse_client)
        row = mock_clickhouse_client.insert.call_args.kwargs["data"][0]
        assert row[2] == "big trader"


class TestRemoveWallet:
    def test_inserts_inactive_row(self, mock_clickhouse_client: MagicMock) -> None:
        remove_wallet("0xabc", clickhouse_client=mock_clickhouse_client)
        mock_clickhouse_client.insert.assert_called_once()
        row = mock_clickhouse_client.insert.call_args.kwargs["data"][0]
        assert row[0] == "0xabc"
        assert row[3] is False


class TestListWallets:
    def _make_query_result(self, rows: list) -> MagicMock:
        result = MagicMock()
        result.result_rows = rows
        return result

    def test_active_only_query(self, mock_clickhouse_client: MagicMock) -> None:
        mock_clickhouse_client.query.return_value = self._make_query_result([])
        list_wallets(active_only=True, clickhouse_client=mock_clickhouse_client)
        query = mock_clickhouse_client.query.call_args[0][0]
        assert "FINAL" in query
        assert "WHERE active = true" in query

    def test_all_wallets_query(self, mock_clickhouse_client: MagicMock) -> None:
        mock_clickhouse_client.query.return_value = self._make_query_result([])
        list_wallets(active_only=False, clickhouse_client=mock_clickhouse_client)
        query = mock_clickhouse_client.query.call_args[0][0]
        assert "WHERE active = true" not in query

    def test_returns_dicts(self, mock_clickhouse_client: MagicMock) -> None:
        now = datetime.now(timezone.utc)
        mock_clickhouse_client.query.return_value = self._make_query_result(
            [["0xabc", now, "test", True]]
        )
        result = list_wallets(clickhouse_client=mock_clickhouse_client)
        assert len(result) == 1
        assert result[0]["wallet_address"] == "0xabc"
        assert result[0]["added_at"] == now
        assert result[0]["notes"] == "test"
        assert result[0]["active"] is True

    def test_empty_result(self, mock_clickhouse_client: MagicMock) -> None:
        mock_clickhouse_client.query.return_value = self._make_query_result([])
        result = list_wallets(clickhouse_client=mock_clickhouse_client)
        assert result == []


class TestWatchlistCLI:
    def test_add_command(self) -> None:
        from typer.testing import CliRunner

        from prediction_data.cli.main import app as cli_app

        runner = CliRunner()
        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(
                "prediction_data.gold.watchlist.get_client",
                lambda: MagicMock(),
            )
            result = runner.invoke(cli_app, ["gold", "watchlist", "add", "0xabc"])
        assert result.exit_code == 0
        assert "Added 0xabc" in result.output

    def test_remove_command(self) -> None:
        from typer.testing import CliRunner

        from prediction_data.cli.main import app as cli_app

        runner = CliRunner()
        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(
                "prediction_data.gold.watchlist.get_client",
                lambda: MagicMock(),
            )
            result = runner.invoke(cli_app, ["gold", "watchlist", "remove", "0xabc"])
        assert result.exit_code == 0
        assert "Removed 0xabc" in result.output

    def test_list_command_empty(self) -> None:
        from typer.testing import CliRunner

        from prediction_data.cli.main import app as cli_app

        runner = CliRunner()
        mock_ch = MagicMock()
        query_result = MagicMock()
        query_result.result_rows = []
        mock_ch.query.return_value = query_result

        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(
                "prediction_data.gold.watchlist.get_client",
                lambda: mock_ch,
            )
            result = runner.invoke(cli_app, ["gold", "watchlist", "list"])
        assert result.exit_code == 0
        assert "No wallets" in result.output

    def test_list_command_with_wallets(self) -> None:
        from typer.testing import CliRunner

        from prediction_data.cli.main import app as cli_app

        runner = CliRunner()
        mock_ch = MagicMock()
        now = datetime.now(timezone.utc)
        query_result = MagicMock()
        query_result.result_rows = [["0xabc", now, "whale", True]]
        mock_ch.query.return_value = query_result

        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(
                "prediction_data.gold.watchlist.get_client",
                lambda: mock_ch,
            )
            result = runner.invoke(cli_app, ["gold", "watchlist", "list"])
        assert result.exit_code == 0
        assert "0xabc" in result.output
        assert "active" in result.output
