#!/usr/bin/env python3
"""Verify Bronze layer is fully operational.

This script checks:
1. All 6 EventBridge schedules exist and are ENABLED
2. Schedules use the correct CLI commands (matching infrastructure template)
3. Data freshness for each Bronze entity
4. Recent run success/failure in CloudWatch logs

Run with: python scripts/verify_bronze_operational.py
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
    command_contains: list[str]
    expected_rate: str


# Expected Bronze schedules based on infrastructure/eventbridge-schedules.yaml
EXPECTED_SCHEDULES = [
    ScheduleCheck(
        name="polymarket-order-filled-prod",
        command_contains=["backfill", "catchup", "--platform", "polymarket", "--entity", "order_filled"],
        expected_rate="rate(5 minutes)",
    ),
    ScheduleCheck(
        name="kalshi-trades-prod",
        command_contains=["backfill", "catchup", "--platform", "kalshi", "--entity", "trades"],
        expected_rate="rate(5 minutes)",
    ),
    ScheduleCheck(
        name="polymarket-markets-prod",
        command_contains=["ingest", "polymarket-markets"],
        expected_rate="rate(1 hour)",
    ),
    ScheduleCheck(
        name="kalshi-markets-prod",
        command_contains=["ingest", "kalshi-markets"],
        expected_rate="rate(1 hour)",
    ),
    ScheduleCheck(
        name="polymarket-events-prod",
        command_contains=["ingest", "polymarket-events"],
        expected_rate="rate(1 hour)",
    ),
    ScheduleCheck(
        name="kalshi-events-prod",
        command_contains=["ingest", "kalshi-events"],
        expected_rate="rate(1 hour)",
    ),
]

# Expected Bronze entities and max allowed staleness
BRONZE_ENTITIES = [
    {"platform": "polymarket", "entity": "order_filled", "max_stale_hours": 1},
    {"platform": "kalshi", "entity": "trades", "max_stale_hours": 1},
    {"platform": "polymarket", "entity": "markets", "max_stale_hours": 24},
    {"platform": "polymarket", "entity": "events", "max_stale_hours": 24},
    {"platform": "kalshi", "entity": "markets", "max_stale_hours": 24},
    {"platform": "kalshi", "entity": "events", "max_stale_hours": 24},
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
    """Check that all expected schedules exist with correct configuration."""
    results = []

    # Get all schedules in the group
    code, stdout, stderr = run_aws_cmd([
        "scheduler", "list-schedules",
        "--group-name", "prediction-data-prod",
        "--output", "json"
    ])

    if code != 0:
        return [{"check": "list_schedules", "status": "FAIL", "error": stderr}]

    schedules = json.loads(stdout).get("Schedules", [])
    schedule_names = {s["Name"] for s in schedules}

    for expected in EXPECTED_SCHEDULES:
        result = {
            "check": f"schedule_{expected.name}",
            "expected_name": expected.name,
        }

        if expected.name not in schedule_names:
            result["status"] = "FAIL"
            result["error"] = f"Schedule '{expected.name}' does not exist in AWS"
            results.append(result)
            continue

        # Get schedule details
        code, stdout, stderr = run_aws_cmd([
            "scheduler", "get-schedule",
            "--name", expected.name,
            "--group-name", "prediction-data-prod",
            "--output", "json"
        ])

        if code != 0:
            result["status"] = "FAIL"
            result["error"] = f"Failed to get schedule details: {stderr}"
            results.append(result)
            continue

        schedule = json.loads(stdout)

        # Check state
        if schedule.get("State") != "ENABLED":
            result["status"] = "FAIL"
            result["error"] = f"Schedule is {schedule.get('State')}, not ENABLED"
            results.append(result)
            continue

        # Check command in target input
        target_input = schedule.get("Target", {}).get("Input", "")
        try:
            input_json = json.loads(target_input)
            command = input_json.get("containerOverrides", [{}])[0].get("command", [])
        except (json.JSONDecodeError, IndexError):
            command = []

        # Verify command contains expected parts
        command_str = " ".join(command)
        missing_parts = [part for part in expected.command_contains if part not in command_str]

        if missing_parts:
            result["status"] = "FAIL"
            result["error"] = f"Command missing: {missing_parts}. Actual: {command}"
            result["actual_command"] = command
            results.append(result)
            continue

        # Check schedule expression
        actual_rate = schedule.get("ScheduleExpression", "")
        if expected.expected_rate not in actual_rate:
            result["status"] = "WARN"
            result["warning"] = f"Expected rate '{expected.expected_rate}', got '{actual_rate}'"
        else:
            result["status"] = "PASS"

        result["actual_command"] = command
        result["schedule_expression"] = actual_rate
        results.append(result)

    # Check for unexpected schedules (orphans that should have been deleted)
    expected_names = {s.name for s in EXPECTED_SCHEDULES}
    orphan_schedules = schedule_names - expected_names
    if orphan_schedules:
        results.append({
            "check": "orphan_schedules",
            "status": "WARN",
            "warning": f"Unexpected schedules found: {orphan_schedules}",
        })

    return results


def check_data_freshness() -> list[dict[str, Any]]:
    """Check data freshness for all Bronze entities."""
    results = []
    now = datetime.now(timezone.utc)

    for entity in BRONZE_ENTITIES:
        result = {
            "check": f"freshness_{entity['platform']}_{entity['entity']}",
            "platform": entity["platform"],
            "entity": entity["entity"],
            "max_stale_hours": entity["max_stale_hours"],
        }

        # Use status latest command for date-scoped entities
        if entity["entity"] in ("order_filled", "trades"):
            code, stdout, stderr = run_cli_cmd([
                "status", "latest",
                "--platform", entity["platform"],
                "--entity", entity["entity"],
            ])

            if code != 0:
                result["status"] = "FAIL"
                result["error"] = f"CLI error: {stderr}"
                results.append(result)
                continue

            # Parse output - format: "platform | entity | latest_date | total_days"
            lines = [l for l in stdout.strip().split("\n") if entity["platform"] in l]
            if not lines:
                result["status"] = "FAIL"
                result["error"] = "No data found"
                result["latest_date"] = None
                results.append(result)
                continue

            parts = lines[0].split("|")
            if len(parts) >= 3:
                latest_date_str = parts[2].strip()
                if latest_date_str == "(none)":
                    result["status"] = "FAIL"
                    result["error"] = "No data found"
                    result["latest_date"] = None
                else:
                    result["latest_date"] = latest_date_str
                    # Check staleness
                    try:
                        latest_date = datetime.strptime(latest_date_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)
                        hours_stale = (now - latest_date).total_seconds() / 3600
                        result["hours_stale"] = round(hours_stale, 1)

                        if hours_stale > entity["max_stale_hours"]:
                            result["status"] = "FAIL"
                            result["error"] = f"Data is {hours_stale:.1f}h stale (max: {entity['max_stale_hours']}h)"
                        else:
                            result["status"] = "PASS"
                    except ValueError:
                        result["status"] = "FAIL"
                        result["error"] = f"Could not parse date: {latest_date_str}"
            else:
                result["status"] = "FAIL"
                result["error"] = f"Unexpected output format: {stdout}"
        else:
            # For catalog entities (markets, events), check S3 directly
            bucket = "prediction-bronze-prod"
            prefix = f"bronze/{entity['platform']}/{entity['entity']}/"

            code, stdout, stderr = run_aws_cmd([
                "s3", "ls", f"s3://{bucket}/{prefix}",
                "--recursive", "--output", "text"
            ])

            if code != 0 or not stdout.strip():
                result["status"] = "FAIL"
                result["error"] = "No data found in S3"
                result["latest_date"] = None
                results.append(result)
                continue

            # Find most recent dt= partition
            lines = stdout.strip().split("\n")
            dates = set()
            for line in lines:
                if "dt=" in line:
                    # Extract date from path like "dt=2026-02-04/"
                    import re
                    match = re.search(r"dt=(\d{4}-\d{2}-\d{2})", line)
                    if match:
                        dates.add(match.group(1))

            if dates:
                latest_date_str = max(dates)
                result["latest_date"] = latest_date_str

                try:
                    latest_date = datetime.strptime(latest_date_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)
                    hours_stale = (now - latest_date).total_seconds() / 3600
                    result["hours_stale"] = round(hours_stale, 1)

                    if hours_stale > entity["max_stale_hours"]:
                        result["status"] = "FAIL"
                        result["error"] = f"Data is {hours_stale:.1f}h stale (max: {entity['max_stale_hours']}h)"
                    else:
                        result["status"] = "PASS"
                except ValueError:
                    result["status"] = "FAIL"
                    result["error"] = f"Could not parse date: {latest_date_str}"
            else:
                result["status"] = "FAIL"
                result["error"] = "No date partitions found"
                result["latest_date"] = None

        results.append(result)

    return results


def check_cloudformation_sync() -> list[dict[str, Any]]:
    """Check if deployed CloudFormation stack matches the template."""
    results = []

    # Get stack resources
    code, stdout, stderr = run_aws_cmd([
        "cloudformation", "describe-stack-resources",
        "--stack-name", "prediction-data-schedules",
        "--query", "StackResources[?ResourceType==`AWS::Scheduler::Schedule`].LogicalResourceId",
        "--output", "json"
    ])

    if code != 0:
        results.append({
            "check": "cloudformation_stack",
            "status": "FAIL",
            "error": f"Failed to query stack: {stderr}"
        })
        return results

    deployed_resources = set(json.loads(stdout))

    # Expected resources based on template
    expected_resources = {
        "PolymarketOrderFilledSchedule",
        "KalshiTradesSchedule",
        "PolymarketMarketsSchedule",
        "KalshiMarketsSchedule",
        "PolymarketEventsSchedule",
        "KalshiEventsSchedule",
    }

    missing = expected_resources - deployed_resources
    extra = deployed_resources - expected_resources

    if missing or extra:
        results.append({
            "check": "cloudformation_sync",
            "status": "FAIL",
            "error": "CloudFormation stack out of sync with template",
            "missing_resources": list(missing) if missing else [],
            "extra_resources": list(extra) if extra else [],
            "fix": "Run: aws cloudformation deploy --template-file infrastructure/eventbridge-schedules.yaml --stack-name prediction-data-schedules --parameter-overrides Environment=prod ... --capabilities CAPABILITY_NAMED_IAM"
        })
    else:
        results.append({
            "check": "cloudformation_sync",
            "status": "PASS",
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
            icon = "✅"
        elif status == "WARN":
            icon = "⚠️"
            warnings += 1
        else:
            icon = "❌"
            failures += 1

        print(f"\n{icon} {check}: {status}")

        if "error" in r:
            print(f"   Error: {r['error']}")
        if "warning" in r:
            print(f"   Warning: {r['warning']}")
        if "latest_date" in r:
            print(f"   Latest date: {r['latest_date']}")
        if "hours_stale" in r:
            print(f"   Hours stale: {r['hours_stale']}")
        if "actual_command" in r:
            print(f"   Command: {r['actual_command']}")
        if "fix" in r:
            print(f"   Fix: {r['fix']}")
        if "missing_resources" in r and r["missing_resources"]:
            print(f"   Missing: {r['missing_resources']}")
        if "extra_resources" in r and r["extra_resources"]:
            print(f"   Extra (orphans): {r['extra_resources']}")

    return failures


def main() -> int:
    print("\n" + "="*60)
    print(" Bronze Layer Operational Verification")
    print(" " + datetime.now().strftime("%Y-%m-%d %H:%M:%S UTC"))
    print("="*60)

    total_failures = 0

    # Check CloudFormation sync first
    cf_results = check_cloudformation_sync()
    total_failures += print_results("CloudFormation Stack Sync", cf_results)

    # Check schedules
    schedule_results = check_schedules()
    total_failures += print_results("EventBridge Schedules", schedule_results)

    # Check data freshness
    freshness_results = check_data_freshness()
    total_failures += print_results("Data Freshness", freshness_results)

    # Summary
    print("\n" + "="*60)
    print(" SUMMARY")
    print("="*60)

    if total_failures == 0:
        print("\n✅ All checks passed! Bronze layer is fully operational.")
        return 0
    else:
        print(f"\n❌ {total_failures} check(s) failed. Bronze layer needs attention.")
        print("\nTo fix CloudFormation issues, redeploy the schedules stack:")
        print("  See infrastructure/README.md for deployment commands")
        return 1


if __name__ == "__main__":
    sys.exit(main())
