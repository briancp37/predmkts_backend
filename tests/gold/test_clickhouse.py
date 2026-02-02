"""Unit tests for the Gold ClickHouse connection factory."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from prediction_data.core.config import Settings
from prediction_data.gold.clickhouse import get_client, ping


class TestGetClient:
    """Tests for ``get_client``."""

    @patch("prediction_data.gold.clickhouse.clickhouse_connect")
    def test_uses_settings(self, mock_cc: MagicMock) -> None:
        settings = Settings(
            bronze_bucket="b",
            clickhouse_host="ch-host",
            clickhouse_port=9000,
            clickhouse_user="admin",
            clickhouse_password="secret",
            clickhouse_database="mydb",
        )
        get_client(settings)
        mock_cc.get_client.assert_called_once_with(
            host="ch-host",
            port=9000,
            username="admin",
            password="secret",
            database="mydb",
        )

    @patch("prediction_data.gold.clickhouse.clickhouse_connect")
    def test_defaults(self, mock_cc: MagicMock) -> None:
        settings = Settings(bronze_bucket="b")
        get_client(settings)
        mock_cc.get_client.assert_called_once_with(
            host="localhost",
            port=8123,
            username="default",
            password="",
            database="prediction_gold",
        )


class TestPing:
    """Tests for ``ping``."""

    def test_ping_success(self) -> None:
        client = MagicMock()
        client.query.return_value.first_row = [1]
        assert ping(client) is True
        client.query.assert_called_once_with("SELECT 1")

    def test_ping_failure(self) -> None:
        client = MagicMock()
        client.query.side_effect = ConnectionError("refused")
        assert ping(client) is False
