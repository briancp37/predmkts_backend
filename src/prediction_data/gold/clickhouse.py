"""ClickHouse connection factory for the Gold layer."""

from __future__ import annotations

import clickhouse_connect
from clickhouse_connect.driver.client import Client

from prediction_data.core.config import Settings, get_settings


def get_client(settings: Settings | None = None) -> Client:
    """Create a ClickHouse client from application settings.

    Args:
        settings: Optional settings override. Uses ``get_settings()`` when *None*.

    Returns:
        A connected ``clickhouse_connect`` client.
    """
    cfg = settings or get_settings()
    # Use secure connection for ports 443 or 8443 (ClickHouse Cloud)
    secure = cfg.clickhouse_port in (443, 8443)
    return clickhouse_connect.get_client(
        host=cfg.clickhouse_host,
        port=cfg.clickhouse_port,
        username=cfg.clickhouse_user,
        password=cfg.clickhouse_password,
        database=cfg.clickhouse_database,
        secure=secure,
    )


def ping(client: Client) -> bool:
    """Health-check the ClickHouse connection.

    Returns:
        *True* if the server responds to ``SELECT 1``.
    """
    try:
        result = client.query("SELECT 1")
        return result.first_row[0] == 1  # type: ignore[no-any-return]
    except Exception:
        return False
