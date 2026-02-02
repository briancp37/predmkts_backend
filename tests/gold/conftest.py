"""Shared fixtures for Gold layer tests."""

from __future__ import annotations

from unittest.mock import MagicMock

import pyarrow as pa
import pytest

from prediction_data.core.config import Settings


@pytest.fixture()
def mock_clickhouse_client() -> MagicMock:
    """A mock ClickHouse client suitable for unit tests.

    The mock responds to ``query("SELECT 1")`` like a real client.
    """
    client = MagicMock()
    client.query.return_value.first_row = [1]
    return client


@pytest.fixture()
def gold_settings() -> Settings:
    """Settings pre-configured for Gold layer tests."""
    return Settings(
        bronze_bucket="test-bronze",
        gold_bucket="test-gold",
        clickhouse_host="localhost",
        clickhouse_port=8123,
        clickhouse_user="default",
        clickhouse_password="",
        clickhouse_database="test_prediction_gold",
    )


@pytest.fixture()
def mock_s3_gold() -> MagicMock:
    """A mock boto3 S3 client for Gold bucket operations.

    Pre-wired with an empty paginator (no existing partition files).
    """
    s3 = MagicMock()
    paginator = MagicMock()
    paginator.paginate.return_value = [{"Contents": []}]
    s3.get_paginator.return_value = paginator
    return s3


@pytest.fixture()
def sample_arrow_table() -> pa.Table:
    """A small Arrow table for write tests."""
    return pa.table({"id": [1, 2, 3], "value": ["a", "b", "c"]})
