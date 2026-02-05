#!/usr/bin/env python3
"""Verify Silver layer is fully operational.

This script checks:
1. All Silver EventBridge schedules exist and are correctly configured
2. Silver Iceberg tables exist in Glue Catalog
3. Data freshness for each Silver entity
4. Recent CloudWatch logs for errors

Run with: python scripts/verify_silver_operational.py
"""

import json
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


@dataclass
class ScheduleCheck:
    """Expected schedule configuration."""
    name: str
    expected_state: str  # ENABLED or DISABLED
    description: str


# Expected Silver schedules based on infrastructure/eventbridge-silver-schedules.yaml
EXPECTED_SCHEDULES = [
    ScheduleCheck(
        name="silver-polymarket-trades-prod",
        expected_state="ENABLED",
        description="Process Polymarket trades every 10 min",
    ),
    ScheduleCheck(
        name="silver-polymarket-markets-prod",
        expected_state="ENABLED",
        description="Process Polymarket markets every 30 min",
    ),
    ScheduleCheck(
        name="silver-polymarket-events-prod",
        expected_state="ENABLED",
        description="Process Polymarket events every 30 min",
    ),
    ScheduleCheck(
        name="silver-kalshi-trades-prod",
        expected_state="DISABLED",
        description="Kalshi trades (scaffolded, no Bronze data)",
    ),
    ScheduleCheck(
        name="silver-kalshi-markets-prod",
        expected_state="DISABLED",
        description="Kalshi markets (scaffolded, no Bronze data)",
    ),
    ScheduleCheck(
        name="silver-kalshi-events-prod",
        expected_state="DISABLED",
        description="Kalshi events (scaffolded, no Bronze data)",
    ),
    ScheduleCheck(
        name="silver-maintain-compact-prod",
        expected_state="ENABLED",
        description="Daily compaction at 04:00 UTC",
    ),
    ScheduleCheck(
        name="silver-maintain-full-prod",
        expected_state="ENABLED",
        description="Weekly full maintenance Sunday 04:00 UTC",
    ),
]

# Silver tables and max allowed staleness
SILVER_TABLES = [
    {"database": "silver_polymarket", "table": "trades", "max_stale_hours": 24},
    {"database": "silver_polymarket", "table": "markets", "max_stale_hours": 48},
    {"database": "silver_polymarket", "table": "events", "max_stale_hours": 48},
    # Kalshi tables are scaffolded but have no data
    {"database": "silver_kalshi", "table": "trades", "max_stale_hours": None},
    {"database": "silver_kalshi", "table": "markets", "max_stale_hours": None},
    {"database": "silver_kalshi", "table": "events", "max_stale_hours": None},
]


def run_aws_cmd(args: list[str]) -> tuple[int, str, str]:
    """Run an AWS CLI command and return (exit_code, stdout, stderr)."""
    result = subprocess.run(
        ["aws"] + args,
        capture_output=True,
        text=True,
    )
    return result.returncode, result.stdout, result.stderr


def run_cli_cmd(args: list[str]) -> tuple[int, str, str]:
    """Run a prediction-data CLI command and return (exit_code, stdout, stderr)."""
    result = subprocess.run(
        ["prediction-data"] + args,
        capture_output=True,
        text=True,
    )
    return result.returncode, result.stdout, result.stderr


def check_schedules() -> list[dict[str, Any]]:
    """Check that all expected Silver schedules exist with correct state."""
    results = []

    # Get all schedules in the Silver group
    code, stdout, stderr = run_aws_cmd([
        "scheduler", "list-schedules",
        "--group-name", "prediction-data-silver-prod",
        "--output", "json"
    ])

    if code != 0:
        return [{"check": "list_schedules", "status": "FAIL", "error": stderr}]

    schedules = json.loads(stdout).get("Schedules", [])
    schedule_map = {s["Name"]: s["State"] for s in schedules}

    for expected in EXPECTED_SCHEDULES:
        result = {
            "check": f"schedule_{expected.name}",
            "expected_name": expected.name,
            "description": expected.description,
            "expected_state": expected.expected_state,
        }

        if expected.name not in schedule_map:
            result["status"] = "FAIL"
            result["error"] = f"Schedule '{expected.name}' does not exist"
            results.append(result)
            continue

        actual_state = schedule_map[expected.name]
        result["actual_state"] = actual_state

        if actual_state != expected.expected_state:
            result["status"] = "WARN"
            result["warning"] = f"Expected {expected.expected_state}, got {actual_state}"
        else:
            result["status"] = "PASS"

        results.append(result)

    return results


def check_glue_tables() -> list[dict[str, Any]]:
    """Check that Silver tables exist in Glue Catalog."""
    results = []

    for table_info in SILVER_TABLES:
        db = table_info["database"]
        table = table_info["table"]
        result = {
            "check": f"glue_table_{db}.{table}",
            "database": db,
            "table": table,
        }

        code, stdout, stderr = run_aws_cmd([
            "glue", "get-table",
            "--database-name", db,
            "--name", table,
            "--output", "json"
        ])

        if code != 0:
            if "EntityNotFoundException" in stderr:
                result["status"] = "FAIL"
                result["error"] = f"Table {db}.{table} not found in Glue Catalog"
            else:
                result["status"] = "FAIL"
                result["error"] = f"Failed to query Glue: {stderr}"
        else:
            table_data = json.loads(stdout).get("Table", {})
            result["status"] = "PASS"
            result["location"] = table_data.get("StorageDescriptor", {}).get("Location", "unknown")

        results.append(result)

    return results


def check_data_freshness() -> list[dict[str, Any]]:
    """Check data freshness for Silver tables by examining S3 data."""
    results = []
    now = datetime.now(timezone.utc)
    bucket = "prediction-silver-prod"

    for table_info in SILVER_TABLES:
        db = table_info["database"]
        table = table_info["table"]
        max_stale = table_info["max_stale_hours"]

        result = {
            "check": f"freshness_{db}.{table}",
            "database": db,
            "table": table,
            "max_stale_hours": max_stale,
        }

        # Skip Kalshi tables (no data expected)
        if max_stale is None:
            result["status"] = "SKIP"
            result["note"] = "Kalshi table scaffolded only, no data expected"
            results.append(result)
            continue

        # List data files to find most recent partition
        prefix = f"silver/{db}.db/{table}/data/"
        code, stdout, stderr = run_aws_cmd([
            "s3", "ls", f"s3://{bucket}/{prefix}",
            "--recursive", "--output", "text"
        ])

        if code != 0 or not stdout.strip():
            result["status"] = "FAIL"
            result["error"] = "No data found in S3"
            result["latest_partition"] = None
            results.append(result)
            continue

        # Find most recent event_ts_day partition
        lines = stdout.strip().split("\n")
        partitions = set()
        for line in lines:
            if "event_ts_day=" in line:
                import re
                match = re.search(r"event_ts_day=(\d{4}-\d{2}-\d{2})", line)
                if match:
                    partitions.add(match.group(1))

        if partitions:
            latest_partition = max(partitions)
            result["latest_partition"] = latest_partition

            try:
                latest_date = datetime.strptime(latest_partition, "%Y-%m-%d").replace(tzinfo=timezone.utc)
                hours_stale = (now - latest_date).total_seconds() / 3600
                result["hours_stale"] = round(hours_stale, 1)

                if hours_stale > max_stale:
                    result["status"] = "FAIL"
                    result["error"] = f"Data is {hours_stale:.1f}h stale (max: {max_stale}h)"
                else:
                    result["status"] = "PASS"
            except ValueError:
                result["status"] = "FAIL"
                result["error"] = f"Could not parse partition date: {latest_partition}"
        else:
            result["status"] = "FAIL"
            result["error"] = "No date partitions found"
            result["latest_partition"] = None

        results.append(result)

    return results


def check_recent_errors() -> list[dict[str, Any]]:
    """Check CloudWatch logs for recent Silver errors."""
    results = []

    # Check for pyarrow import errors (known issue)
    code, stdout, stderr = run_aws_cmd([
        "logs", "filter-log-events",
        "--log-group-name", "/ecs/prediction-data-prod",
        "--filter-pattern", '"ModuleNotFoundError" "pyarrow"',
        "--start-time", str(int((datetime.now(timezone.utc) - timedelta(hours=24)).timestamp() * 1000)),
        "--limit", "5",
        "--query", "length(events)",
        "--output", "text"
    ])

    if code == 0:
        error_count = int(stdout.strip() or "0")
        if error_count > 0:
            results.append({
                "check": "pyarrow_import_errors",
                "status": "FAIL",
                "error": f"Found {error_count} pyarrow import errors in last 24h",
                "fix": "Run ./scripts/push_ecr.sh to rebuild Docker image with pyarrow",
            })
        else:
            results.append({
                "check": "pyarrow_import_errors",
                "status": "PASS",
            })

    # Check for general Silver processing errors
    code, stdout, stderr = run_aws_cmd([
        "logs", "filter-log-events",
        "--log-group-name", "/ecs/prediction-data-prod",
        "--filter-pattern", '"silver" "error"',
        "--start-time", str(int((datetime.now(timezone.utc) - timedelta(hours=24)).timestamp() * 1000)),
        "--limit", "5",
        "--query", "length(events)",
        "--output", "text"
    ])

    if code == 0:
        error_count = int(stdout.strip() or "0")
        if error_count > 0:
            results.append({
                "check": "silver_processing_errors",
                "status": "WARN",
                "warning": f"Found {error_count} Silver-related errors in last 24h",
            })
        else:
            results.append({
                "check": "silver_processing_errors",
                "status": "PASS",
            })

    # Check for successful Silver runs
    code, stdout, stderr = run_aws_cmd([
        "logs", "filter-log-events",
        "--log-group-name", "/ecs/prediction-data-prod",
        "--filter-pattern", '"Silver processing completed"',
        "--start-time", str(int((datetime.now(timezone.utc) - timedelta(hours=24)).timestamp() * 1000)),
        "--limit", "5",
        "--query", "length(events)",
        "--output", "text"
    ])

    if code == 0:
        success_count = int(stdout.strip() or "0")
        if success_count > 0:
            results.append({
                "check": "silver_successful_runs",
                "status": "PASS",
                "note": f"Found {success_count} successful Silver runs in last 24h",
            })
        else:
            results.append({
                "check": "silver_successful_runs",
                "status": "WARN",
                "warning": "No successful Silver runs found in last 24h",
            })

    return results


def print_results(title: str, results: list[dict[str, Any]]) -> int:
    """Print check results and return count of failures."""
    print(f"\n{'='*60}")
    print(f" {title}")
    print(f"{'='*60}")

    failures = 0
    warnings = 0

    for r in results:
        status = r.get("status", "UNKNOWN")
        check = r.get("check", "unknown")

        if status == "PASS":
            icon = "\u2705"
        elif status == "WARN":
            icon = "\u26a0\ufe0f"
            warnings += 1
        elif status == "SKIP":
            icon = "\u23ed\ufe0f"
        else:
            icon = "\u274c"
            failures += 1

        print(f"\n{icon} {check}: {status}")

        if "description" in r:
            print(f"   Description: {r['description']}")
        if "error" in r:
            print(f"   Error: {r['error']}")
        if "warning" in r:
            print(f"   Warning: {r['warning']}")
        if "note" in r:
            print(f"   Note: {r['note']}")
        if "latest_partition" in r:
            print(f"   Latest partition: {r['latest_partition']}")
        if "hours_stale" in r:
            print(f"   Hours stale: {r['hours_stale']}")
        if "expected_state" in r and "actual_state" in r:
            print(f"   State: {r['actual_state']} (expected: {r['expected_state']})")
        if "location" in r:
            print(f"   Location: {r['location']}")
        if "fix" in r:
            print(f"   Fix: {r['fix']}")

    return failures


def main() -> int:
    print("\n" + "="*60)
    print(" Silver Layer Operational Verification")
    print(" " + datetime.now().strftime("%Y-%m-%d %H:%M:%S UTC"))
    print("="*60)

    total_failures = 0

    # Check schedules
    schedule_results = check_schedules()
    total_failures += print_results("EventBridge Schedules", schedule_results)

    # Check Glue tables
    glue_results = check_glue_tables()
    total_failures += print_results("Glue Catalog Tables", glue_results)

    # Check data freshness
    freshness_results = check_data_freshness()
    total_failures += print_results("Data Freshness", freshness_results)

    # Check recent errors
    error_results = check_recent_errors()
    total_failures += print_results("CloudWatch Logs", error_results)

    # Summary
    print("\n" + "="*60)
    print(" SUMMARY")
    print("="*60)

    if total_failures == 0:
        print("\n\u2705 All checks passed! Silver layer is fully operational.")
        return 0
    else:
        print(f"\n\u274c {total_failures} check(s) failed. Silver layer needs attention.")
        print("\nCommon fixes:")
        print("  - pyarrow errors: Run ./scripts/push_ecr.sh to rebuild Docker image")
        print("  - Stale data: Check CloudWatch logs for processing errors")
        print("  - Missing schedules: Run ./scripts/deploy-silver.sh")
        return 1


if __name__ == "__main__":
    sys.exit(main())
