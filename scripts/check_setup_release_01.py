#!/usr/bin/env python3
"""Verify Bronze MVP setup and runtime health.

Checks two categories:
1. Infrastructure Setup - S3, IAM, ECS, EventBridge, CloudWatch, ECR
2. Runtime Verification - ECR image, ECS task success rate, data freshness

Run this script to verify Release 01 completion criteria.
"""

import json
import os
import sys
import shutil
import subprocess
from pathlib import Path

PASS = "\033[92m✔\033[0m"
FAIL = "\033[91m✘\033[0m"
WARN = "\033[93m⚠\033[0m"

failures = 0
warnings = 0


def check(label: str, ok: bool, required: bool = True, hint: str = "") -> None:
    global failures, warnings
    if ok:
        print(f"  {PASS} {label}")
    elif required:
        failures += 1
        msg = f"  {FAIL} {label}"
        if hint:
            msg += f"  -> {hint}"
        print(msg)
    else:
        warnings += 1
        msg = f"  {WARN} {label} (optional)"
        if hint:
            msg += f"  -> {hint}"
        print(msg)


def load_dotenv_file() -> dict[str, str]:
    """Minimal .env parser (no dependency needed)."""
    env_path = Path(__file__).resolve().parent.parent / ".env"
    vals: dict[str, str] = {}
    if not env_path.exists():
        return vals
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" in line:
            k, v = line.split("=", 1)
            vals[k.strip()] = v.strip()
    return vals


def run_aws(args: list[str], timeout: int = 15) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["aws"] + args,
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def main() -> None:
    print("\n=== Prediction Data Pipeline: Bronze MVP Verification ===\n")
    print("=== Infrastructure Setup ===\n")

    dotenv = load_dotenv_file()

    def getvar(name: str) -> str:
        return os.environ.get(name, dotenv.get(name, ""))

    # ── Python ──
    print("[Python]")
    vi = sys.version_info
    check("Python 3.11+", vi >= (3, 11), hint=f"Found {vi.major}.{vi.minor}")

    # ── Package ──
    print("\n[Package]")
    try:
        import prediction_data  # noqa: F401
        check("prediction-data package installed", True)
    except ImportError:
        check("prediction-data package installed", False, hint="Run: pip install -e '.[dev]'")

    cli_path = shutil.which("prediction-data")
    check("prediction-data CLI on PATH", cli_path is not None, hint="pip install -e '.[dev]'")

    # ── .env ──
    print("\n[Environment Variables]")
    env_file = Path(__file__).resolve().parent.parent / ".env"
    check(".env file exists", env_file.exists(), hint="cp .env.example .env")

    bronze = getvar("BRONZE_BUCKET")
    check(
        "BRONZE_BUCKET is set",
        bool(bronze) and bronze != "your-bronze-bucket-name",
        hint="Set a real S3 bucket name in .env",
    )

    region = getvar("AWS_REGION") or "us-east-1"
    check(f"AWS_REGION = {region}", True)

    # ── AWS credentials ──
    print("\n[AWS Credentials]")
    has_aws_cli = shutil.which("aws") is not None
    if not has_aws_cli:
        check("AWS CLI installed", False, hint="Install aws-cli v2")
    else:
        try:
            result = run_aws(["sts", "get-caller-identity", "--output", "json"])
            has_creds = result.returncode == 0
            if has_creds:
                identity = json.loads(result.stdout)
                acct = identity.get("Account", "?")
                check(f"AWS credentials valid (account: {acct})", True)
            else:
                check("AWS credentials valid", False, hint="Run: aws configure")
        except Exception:
            check("AWS credentials valid", False, hint="Run: aws configure")

    # ── S3 bucket ──
    print("\n[S3 Bronze Bucket]")
    bucket_ok = False
    if bronze and bronze != "your-bronze-bucket-name" and has_aws_cli:
        try:
            result = run_aws(["s3api", "head-bucket", "--bucket", bronze])
            bucket_ok = result.returncode == 0
            check(f"S3 bucket '{bronze}' exists", bucket_ok, hint="Deploy s3-bronze-bucket.yaml stack")
        except Exception:
            check(f"S3 bucket '{bronze}' reachable", False)

        if bucket_ok:
            try:
                result = run_aws(["s3api", "get-bucket-versioning", "--bucket", bronze, "--query", "Status", "--output", "text"])
                versioning = result.stdout.strip()
                check(
                    f"S3 bucket versioning enabled (Status={versioning})",
                    versioning == "Enabled",
                    hint="aws s3api put-bucket-versioning --bucket BUCKET --versioning-configuration Status=Enabled",
                )
            except Exception:
                check("S3 bucket versioning check", False)
    else:
        check("S3 bucket check", False, hint="Set BRONZE_BUCKET first")

    # ── Kalshi ──
    print("\n[Kalshi API]")
    kalshi_key = getvar("KALSHI_API_KEY_ID")
    check("KALSHI_API_KEY_ID set", bool(kalshi_key) and kalshi_key != "kalshi-api-key", required=False, hint="Set in .env if you need Kalshi data")

    kalshi_pem = getvar("KALSHI_PRIVATE_KEY_PATH")
    if kalshi_pem and kalshi_pem != "kalshi-private-key-path":
        pem_exists = Path(kalshi_pem).expanduser().exists()
        check(f"Private key file exists ({kalshi_pem})", pem_exists, required=False, hint="Check path")
    else:
        check("KALSHI_PRIVATE_KEY_PATH set", False, required=False, hint="Set in .env if you need Kalshi data")

    # ── Docker ──
    print("\n[Docker]")
    docker_path = shutil.which("docker")
    check("Docker installed", docker_path is not None, hint="Install Docker Desktop or docker engine")

    dockerfile = Path(__file__).resolve().parent.parent / "Dockerfile"
    check("Dockerfile exists", dockerfile.exists(), hint="Dockerfile should be in project root")

    # ── ECR Repository ──
    print("\n[ECR Repository]")
    if has_aws_cli:
        try:
            result = run_aws([
                "ecr", "describe-repositories",
                "--repository-names", "prediction-data",
                "--region", region,
                "--query", "repositories[0].repositoryUri",
                "--output", "text",
            ])
            ecr_ok = result.returncode == 0 and result.stdout.strip() not in ("", "None")
            repo_uri = result.stdout.strip() if ecr_ok else ""
            check(
                f"ECR repository exists ({repo_uri})" if ecr_ok else "ECR repository 'prediction-data' exists",
                ecr_ok,
                hint="aws ecr create-repository --repository-name prediction-data",
            )
        except Exception:
            check("ECR repository check", False)
    else:
        check("ECR repository check", False, hint="Install AWS CLI first")

    # ── CloudFormation Stacks ──
    print("\n[CloudFormation Stacks]")
    expected_stacks = [
        ("prediction-bronze-bucket", "s3-bronze-bucket.yaml"),
        ("prediction-data-iam-roles", "iam-ecs-roles.yaml"),
        ("prediction-data-ecs", "ecs-cluster.yaml"),
        ("prediction-data-schedules", "eventbridge-schedules.yaml"),
        ("prediction-data-monitoring", "cloudwatch-monitoring.yaml"),
    ]
    if has_aws_cli:
        for stack_name, template_file in expected_stacks:
            try:
                result = run_aws([
                    "cloudformation", "describe-stacks",
                    "--stack-name", stack_name,
                    "--query", "Stacks[0].StackStatus",
                    "--output", "text",
                    "--region", region,
                ])
                stack_status = result.stdout.strip() if result.returncode == 0 else ""
                ok = stack_status in (
                    "CREATE_COMPLETE", "UPDATE_COMPLETE", "UPDATE_ROLLBACK_COMPLETE",
                    "IMPORT_COMPLETE",
                )
                label = f"Stack '{stack_name}' deployed ({stack_status})" if ok else f"Stack '{stack_name}' deployed"
                check(label, ok, hint=f"Deploy infrastructure/{template_file}")
            except Exception:
                check(f"Stack '{stack_name}' check", False)
    else:
        check("CloudFormation stack checks", False, hint="Install AWS CLI first")

    # ── ECS Cluster ──
    print("\n[ECS Cluster]")
    if has_aws_cli:
        try:
            result = run_aws([
                "ecs", "describe-clusters",
                "--clusters", "prediction-data-prod",
                "--query", "clusters[0].status",
                "--output", "text",
                "--region", region,
            ])
            ecs_status = result.stdout.strip() if result.returncode == 0 else ""
            check(
                f"ECS cluster 'prediction-data-prod' active ({ecs_status})",
                ecs_status == "ACTIVE",
                hint="Deploy ecs-cluster.yaml stack",
            )
        except Exception:
            check("ECS cluster check", False)
    else:
        check("ECS cluster check", False, hint="Install AWS CLI first")

    # ── EventBridge Schedules ──
    print("\n[EventBridge Schedules]")
    expected_schedules = [
        "polymarket-order-filled-prod",
        "kalshi-trades-prod",
        "polymarket-markets-prod",
        "kalshi-markets-prod",
        "polymarket-events-prod",
        "kalshi-events-prod",
    ]
    if has_aws_cli:
        try:
            result = run_aws([
                "scheduler", "list-schedules",
                "--group-name", "prediction-data-prod",
                "--query", "Schedules[].{Name:Name,State:State}",
                "--output", "json",
                "--region", region,
            ])
            if result.returncode == 0:
                schedules = json.loads(result.stdout) if result.stdout.strip() else []
                schedule_names = {s.get("Name", "") for s in schedules}
                check(
                    f"EventBridge schedules found ({len(schedules)} of {len(expected_schedules)} expected)",
                    len(schedules) >= len(expected_schedules),
                    hint=f"Deploy eventbridge-schedules.yaml stack (expect {len(expected_schedules)} schedules)",
                )
                for expected_name in expected_schedules:
                    found = expected_name in schedule_names
                    if found:
                        sched = next(s for s in schedules if s.get("Name") == expected_name)
                        state = sched.get("State", "?")
                        check(f"  Schedule '{expected_name}' state={state}", state == "ENABLED")
                    else:
                        check(f"  Schedule '{expected_name}' exists", False, hint="Deploy eventbridge-schedules.yaml")
                # Warn about old polymarket-trades schedule if still present
                if "polymarket-trades-prod" in schedule_names:
                    check(
                        "  Old 'polymarket-trades-prod' schedule removed",
                        False,
                        hint="Delete the old polymarket-trades schedule; it has been replaced by polymarket-order-filled",
                    )
            else:
                check("EventBridge schedules check", False)
        except Exception:
            check("EventBridge schedules check", False)
    else:
        check("EventBridge schedules check", False, hint="Install AWS CLI first")

    # ── SNS Alert Subscription ──
    print("\n[CloudWatch Monitoring]")
    if has_aws_cli:
        try:
            # Find SNS topic
            result = run_aws([
                "sns", "list-topics",
                "--query", "Topics[?contains(TopicArn, 'prediction-data')].TopicArn",
                "--output", "json",
                "--region", region,
            ])
            if result.returncode == 0:
                topics = json.loads(result.stdout) if result.stdout.strip() else []
                check(f"SNS alert topic exists ({len(topics)} topic(s))", len(topics) > 0, hint="Deploy cloudwatch-monitoring.yaml")

                # Check for confirmed subscriptions
                if topics:
                    sub_result = run_aws([
                        "sns", "list-subscriptions-by-topic",
                        "--topic-arn", topics[0],
                        "--query", "Subscriptions[?Protocol=='email'].SubscriptionArn",
                        "--output", "json",
                        "--region", region,
                    ])
                    if sub_result.returncode == 0:
                        subs = json.loads(sub_result.stdout) if sub_result.stdout.strip() else []
                        confirmed = [s for s in subs if s != "PendingConfirmation"]
                        check(
                            f"SNS email subscription confirmed ({len(confirmed)} confirmed)",
                            len(confirmed) > 0,
                            hint="Check your email inbox and confirm the SNS subscription",
                        )
            else:
                check("SNS topic check", False)
        except Exception:
            check("SNS topic check", False)
    else:
        check("SNS/monitoring check", False, hint="Install AWS CLI first")

    # ── Infrastructure templates exist locally ──
    print("\n[Infrastructure Templates]")
    infra_dir = Path(__file__).resolve().parent.parent / "infrastructure"
    for _, template_file in expected_stacks:
        path = infra_dir / template_file
        check(f"Template {template_file} exists", path.exists(), hint=f"Missing infrastructure/{template_file}")

    # ══════════════════════════════════════════════════════════════════════════
    # RUNTIME CHECKS - Verify scheduled runs are actually working
    # ══════════════════════════════════════════════════════════════════════════

    print("\n" + "=" * 55)
    print("=== Runtime Verification (Scheduled Runs) ===\n")

    # ── ECR Image ──
    print("[ECR Image]")
    ecr_image_ok = False
    if has_aws_cli:
        try:
            result = run_aws([
                "ecr", "describe-images",
                "--repository-name", "prediction-data",
                "--query", "imageDetails[?imageTags[?contains(@, 'latest')]].{Tags:imageTags,PushedAt:imagePushedAt}",
                "--output", "json",
                "--region", region,
            ])
            if result.returncode == 0:
                images = json.loads(result.stdout) if result.stdout.strip() else []
                if images:
                    pushed_at = images[0].get("PushedAt", "unknown")
                    check(f"Docker image 'latest' exists (pushed: {pushed_at})", True)
                    ecr_image_ok = True
                else:
                    check(
                        "Docker image 'latest' exists in ECR",
                        False,
                        hint="docker build -t prediction-data . && docker tag prediction-data:latest <ECR_URI>:latest && docker push <ECR_URI>:latest",
                    )
            else:
                check("ECR image check", False)
        except Exception:
            check("ECR image check", False)
    else:
        check("ECR image check", False, hint="Install AWS CLI first")

    # ── Recent ECS Task Runs ──
    print("\n[Recent ECS Task Runs]")
    if has_aws_cli:
        try:
            # Get recent stopped tasks
            result = run_aws([
                "ecs", "list-tasks",
                "--cluster", "prediction-data-prod",
                "--desired-status", "STOPPED",
                "--query", "taskArns[-20:]",
                "--output", "json",
                "--region", region,
            ])
            if result.returncode == 0:
                task_arns = json.loads(result.stdout) if result.stdout.strip() else []
                if not task_arns:
                    check("Recent ECS tasks found", False, required=False, hint="No task history yet - schedules may not have triggered")
                else:
                    # Describe tasks to get status
                    result = run_aws([
                        "ecs", "describe-tasks",
                        "--cluster", "prediction-data-prod",
                        "--tasks", *task_arns,
                        "--query", "tasks[].{StopCode:stopCode,ExitCode:containers[0].exitCode,StoppedAt:stoppedAt}",
                        "--output", "json",
                        "--region", region,
                    ], timeout=30)
                    if result.returncode == 0:
                        tasks = json.loads(result.stdout) if result.stdout.strip() else []
                        total = len(tasks)
                        succeeded = sum(1 for t in tasks if t.get("ExitCode") == 0)
                        failed_to_start = sum(1 for t in tasks if t.get("StopCode") == "TaskFailedToStart")
                        failed_exit = sum(1 for t in tasks if t.get("ExitCode") not in (None, 0))

                        check(f"Recent tasks found ({total} tasks)", total > 0)

                        if failed_to_start > 0:
                            check(
                                f"Tasks starting successfully ({failed_to_start}/{total} failed to start)",
                                False,
                                hint="Check ECR image exists and IAM permissions",
                            )
                        else:
                            check(f"Tasks starting successfully ({total}/{total})", True)

                        if succeeded > 0:
                            success_rate = (succeeded / total) * 100
                            check(
                                f"Task success rate ({succeeded}/{total} = {success_rate:.0f}%)",
                                success_rate >= 80,
                                hint="Check CloudWatch logs for errors",
                            )
                        elif failed_to_start == total:
                            check("Task success rate", False, hint="All tasks failed to start - push Docker image to ECR first")
                        else:
                            check(
                                f"Task success rate (0/{total} succeeded)",
                                False,
                                hint="Check CloudWatch logs: aws logs tail /ecs/prediction-data --since 1h",
                            )
            else:
                check("ECS task history check", False)
        except Exception as e:
            check(f"ECS task history check ({e})", False)
    else:
        check("ECS task history check", False, hint="Install AWS CLI first")

    # ── Data Freshness ──
    print("\n[Data Freshness]")
    if has_aws_cli and bronze and bucket_ok:
        from datetime import datetime, timedelta

        today = datetime.utcnow().strftime("%Y-%m-%d")
        yesterday = (datetime.utcnow() - timedelta(days=1)).strftime("%Y-%m-%d")

        entities_to_check = [
            ("polymarket", "markets"),
            ("polymarket", "events"),
            ("polymarket", "order_filled"),
            ("kalshi", "markets"),
            ("kalshi", "events"),
            ("kalshi", "trades"),
        ]

        for platform, entity in entities_to_check:
            # Check for data from today or yesterday
            found_date = None
            for check_date in [today, yesterday]:
                prefix = f"bronze/{platform}/{entity}/dt={check_date}/"
                result = run_aws([
                    "s3api", "list-objects-v2",
                    "--bucket", bronze,
                    "--prefix", prefix,
                    "--max-items", "1",
                    "--query", "Contents[0].Key",
                    "--output", "text",
                ])
                if result.returncode == 0 and result.stdout.strip() not in ("", "None"):
                    found_date = check_date
                    break

            if found_date:
                check(f"{platform}/{entity} has recent data (dt={found_date})", True)
            else:
                check(
                    f"{platform}/{entity} has recent data",
                    False,
                    required=False,
                    hint=f"No data for {yesterday} or {today}",
                )
    else:
        check("Data freshness check", False, required=False, hint="S3 bucket not accessible")

    # ── Summary ──
    print("\n" + "=" * 55)
    print("=== Summary ===\n")
    if failures == 0 and warnings == 0:
        print(f"{PASS} All checks passed! Bronze MVP is fully operational.")
        print("    Release 01 exit criteria met - ready for sign-off and v1.0.0-bronze tag.")
    elif failures == 0:
        print(f"{PASS} All required checks passed ({warnings} optional warning(s))")
        print("    Pipeline is operational. Review warnings if needed.")
    else:
        print(f"{FAIL} {failures} required check(s) failed, {warnings} warning(s)")
        print("    Fix failures before Release 01 can be completed.")
    print()
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
