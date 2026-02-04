"""Tests for ECS concurrency guard.

Validates that the concurrency guard correctly:
- Returns False when not running in ECS (no metadata URI)
- Returns False when no other tasks are running
- Returns True when a matching concurrent task is detected
- Returns False when sibling tasks have non-matching commands
- Returns False on API errors (fail-open)
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from prediction_data.core.ecs_guard import should_skip_concurrent

OWN_TASK_ARN = "arn:aws:ecs:us-east-1:123456789:task/my-cluster/own-task-id"
SIBLING_TASK_ARN = "arn:aws:ecs:us-east-1:123456789:task/my-cluster/sibling-task-id"
CLUSTER_ARN = "arn:aws:ecs:us-east-1:123456789:cluster/my-cluster"
FAMILY = "prediction-data"
METADATA_URI = "http://169.254.170.2/v4/abc123"


def _make_task_metadata() -> dict[str, str]:
    return {
        "TaskARN": OWN_TASK_ARN,
        "Cluster": CLUSTER_ARN,
        "Family": FAMILY,
    }


def _make_describe_response(
    tasks: list[dict[str, Any]],
) -> dict[str, list[dict[str, Any]]]:
    return {"tasks": tasks}


def _make_task_with_command(
    task_arn: str, command: list[str]
) -> dict[str, Any]:
    return {
        "taskArn": task_arn,
        "overrides": {
            "containerOverrides": [
                {"command": command},
            ],
        },
    }


def _make_httpx_response(data: dict[str, Any]) -> MagicMock:
    """Create a mock httpx.Response (sync methods: json, raise_for_status)."""
    resp = MagicMock()
    resp.json.return_value = data
    resp.raise_for_status.return_value = None
    return resp


def _make_async_http_client(response: MagicMock) -> MagicMock:
    """Create a mock httpx.AsyncClient that returns the given response on GET."""
    http = AsyncMock()
    http.get.return_value = response
    # AsyncClient is used as `async with httpx.AsyncClient() as http:`
    # The constructor returns an object whose __aenter__ yields the client.
    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=http)
    ctx.__aexit__ = AsyncMock(return_value=False)
    return ctx


@pytest.mark.asyncio
async def test_not_in_ecs_returns_false() -> None:
    """When ECS_CONTAINER_METADATA_URI_V4 is not set, returns False."""
    with patch.dict("os.environ", {}, clear=True):
        result = await should_skip_concurrent("order_filled")
    assert result is False


@pytest.mark.asyncio
async def test_no_sibling_tasks_returns_false() -> None:
    """When the only running task is our own, returns False."""
    mock_response = _make_httpx_response(_make_task_metadata())
    mock_ctx = _make_async_http_client(mock_response)

    mock_ecs = MagicMock()
    mock_ecs.list_tasks.return_value = {"taskArns": [OWN_TASK_ARN]}

    with (
        patch.dict("os.environ", {"ECS_CONTAINER_METADATA_URI_V4": METADATA_URI}),
        patch("prediction_data.core.ecs_guard.httpx.AsyncClient", return_value=mock_ctx),
        patch("prediction_data.core.ecs_guard.boto3.client", return_value=mock_ecs),
    ):
        result = await should_skip_concurrent("order_filled")

    assert result is False
    mock_ecs.list_tasks.assert_called_once_with(
        cluster=CLUSTER_ARN, family=FAMILY, desiredStatus="RUNNING"
    )
    mock_ecs.describe_tasks.assert_not_called()


@pytest.mark.asyncio
async def test_matching_concurrent_task_returns_true() -> None:
    """When a sibling task has a matching command, returns True."""
    mock_response = _make_httpx_response(_make_task_metadata())
    mock_ctx = _make_async_http_client(mock_response)

    sibling_task = _make_task_with_command(
        SIBLING_TASK_ARN,
        ["backfill", "catchup", "--platform", "polymarket", "--entity", "order_filled", "--skip-if-concurrent"],
    )

    mock_ecs = MagicMock()
    mock_ecs.list_tasks.return_value = {"taskArns": [OWN_TASK_ARN, SIBLING_TASK_ARN]}
    mock_ecs.describe_tasks.return_value = _make_describe_response([sibling_task])

    with (
        patch.dict("os.environ", {"ECS_CONTAINER_METADATA_URI_V4": METADATA_URI}),
        patch("prediction_data.core.ecs_guard.httpx.AsyncClient", return_value=mock_ctx),
        patch("prediction_data.core.ecs_guard.boto3.client", return_value=mock_ecs),
    ):
        result = await should_skip_concurrent("order_filled")

    assert result is True
    mock_ecs.describe_tasks.assert_called_once_with(
        cluster=CLUSTER_ARN, tasks=[SIBLING_TASK_ARN]
    )


@pytest.mark.asyncio
async def test_non_matching_sibling_returns_false() -> None:
    """When sibling tasks have commands that don't match the filter, returns False."""
    mock_response = _make_httpx_response(_make_task_metadata())
    mock_ctx = _make_async_http_client(mock_response)

    sibling_task = _make_task_with_command(
        SIBLING_TASK_ARN,
        ["backfill", "catchup", "--platform", "kalshi", "--entity", "trades"],
    )

    mock_ecs = MagicMock()
    mock_ecs.list_tasks.return_value = {"taskArns": [OWN_TASK_ARN, SIBLING_TASK_ARN]}
    mock_ecs.describe_tasks.return_value = _make_describe_response([sibling_task])

    with (
        patch.dict("os.environ", {"ECS_CONTAINER_METADATA_URI_V4": METADATA_URI}),
        patch("prediction_data.core.ecs_guard.httpx.AsyncClient", return_value=mock_ctx),
        patch("prediction_data.core.ecs_guard.boto3.client", return_value=mock_ecs),
    ):
        result = await should_skip_concurrent("order_filled")

    assert result is False


@pytest.mark.asyncio
async def test_api_error_returns_false() -> None:
    """When the ECS API fails, returns False (fail-open)."""
    mock_response = _make_httpx_response(_make_task_metadata())
    mock_ctx = _make_async_http_client(mock_response)

    mock_ecs = MagicMock()
    mock_ecs.list_tasks.side_effect = Exception("ECS API error")

    with (
        patch.dict("os.environ", {"ECS_CONTAINER_METADATA_URI_V4": METADATA_URI}),
        patch("prediction_data.core.ecs_guard.httpx.AsyncClient", return_value=mock_ctx),
        patch("prediction_data.core.ecs_guard.boto3.client", return_value=mock_ecs),
    ):
        result = await should_skip_concurrent("order_filled")

    assert result is False


@pytest.mark.asyncio
async def test_metadata_endpoint_error_returns_false() -> None:
    """When the metadata endpoint fails, returns False (fail-open)."""
    mock_response = MagicMock()
    mock_response.raise_for_status.side_effect = Exception("metadata endpoint error")

    mock_ctx = _make_async_http_client(mock_response)

    with (
        patch.dict("os.environ", {"ECS_CONTAINER_METADATA_URI_V4": METADATA_URI}),
        patch("prediction_data.core.ecs_guard.httpx.AsyncClient", return_value=mock_ctx),
    ):
        result = await should_skip_concurrent("order_filled")

    assert result is False
