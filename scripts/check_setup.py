#!/usr/bin/env python3
"""Verify that all human-managed setup for Bronze MVP (Sprints 1-6) is in place."""

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
    print("\n=== Prediction Data Pipeline: Setup Check (Bronze MVP) ===\n")

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
                check(
                    f"EventBridge schedules found ({len(schedules)} schedules)",
                    len(schedules) >= 4,
                    hint="Deploy eventbridge-schedules.yaml stack (expect 6 schedules)",
                )
                for sched in schedules:
                    name = sched.get("Name", "?")
                    state = sched.get("State", "?")
                    check(f"  Schedule '{name}' state={state}", state == "ENABLED")
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

    # ── Summary ──
    print("\n" + "=" * 55)
    if failures == 0 and warnings == 0:
        print(f"{PASS} All checks passed! Pipeline is fully set up.")
    elif failures == 0:
        print(f"{PASS} All required checks passed ({warnings} optional warning(s))")
    else:
        print(f"{FAIL} {failures} required check(s) failed, {warnings} warning(s)")
    print()
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
