"""ECS-based concurrency guard for scheduled tasks.

Detects whether another ECS task with the same command is already running,
allowing scheduled tasks to skip execution and prevent overlapping runs.
"""

from __future__ import annotations

import os
from typing import Any

import boto3
import httpx

from prediction_data.core.logging import get_logger

logger = get_logger(__name__)


async def should_skip_concurrent(command_filter: str) -> bool:
    """Check if another ECS task with the same command is already running.

    Reads ECS task metadata to identify the current task, then queries the
    ECS API for other running tasks in the same family. If any sibling task's
    command override contains ``command_filter``, returns True (skip).

    When not running in ECS (local dev), returns False immediately.
    On any API error, logs a warning and returns False (proceed rather than block).

    Args:
        command_filter: String to search for in sibling task command overrides
            (e.g. "order_filled").

    Returns:
        True if a concurrent task with matching command is detected (caller
        should skip). False otherwise.
    """
    metadata_uri = os.environ.get("ECS_CONTAINER_METADATA_URI_V4")
    if not metadata_uri:
        logger.debug("Not running in ECS (no metadata URI), skipping concurrency check")
        return False

    try:
        return await _check_concurrent_tasks(metadata_uri, command_filter)
    except Exception:
        logger.warning(
            "ECS concurrency check failed, proceeding anyway",
            exc_info=True,
        )
        return False


async def _check_concurrent_tasks(
    metadata_uri: str, command_filter: str
) -> bool:
    """Query ECS metadata and API to detect concurrent tasks.

    Args:
        metadata_uri: The ECS container metadata URI (v4).
        command_filter: String to match in sibling task commands.

    Returns:
        True if a sibling task with matching command is running.
    """
    # Fetch own task metadata
    async with httpx.AsyncClient() as http:
        resp = await http.get(f"{metadata_uri}/task")
        resp.raise_for_status()
        task_meta = resp.json()

    own_task_arn: str = task_meta["TaskARN"]
    cluster_arn: str = task_meta["Cluster"]
    family: str = task_meta["Family"]

    logger.debug(
        "ECS concurrency check",
        own_task_arn=own_task_arn,
        cluster=cluster_arn,
        family=family,
        command_filter=command_filter,
    )

    # List running tasks in the same family
    ecs: Any = boto3.client("ecs")
    list_resp = ecs.list_tasks(
        cluster=cluster_arn, family=family, desiredStatus="RUNNING"
    )
    task_arns: list[str] = list_resp.get("taskArns", [])

    # Filter out own task
    sibling_arns = [arn for arn in task_arns if arn != own_task_arn]
    if not sibling_arns:
        logger.debug("No sibling tasks running")
        return False

    # Describe sibling tasks and check command overrides
    desc_resp = ecs.describe_tasks(cluster=cluster_arn, tasks=sibling_arns)
    for task in desc_resp.get("tasks", []):
        for override in task.get("overrides", {}).get("containerOverrides", []):
            command: list[str] = override.get("command", [])
            if any(command_filter in arg for arg in command):
                logger.info(
                    "Concurrent task detected, should skip",
                    concurrent_task_arn=task["taskArn"],
                    concurrent_command=command,
                )
                return True

    logger.debug("No concurrent tasks with matching command found")
    return False
