#!/usr/bin/env python3
"""Verify Silver Lakehouse setup and runtime health.

Checks two categories:
1. Infrastructure Setup - S3 Silver bucket, Glue Catalog, IAM, Iceberg tables
2. Runtime Verification - Table data, processing state, quality checks

Run this script to verify Release 02 completion criteria.
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
    print("\n=== Prediction Data Pipeline: Silver Lakehouse Verification ===\n")
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

    # ── PyIceberg ──
    print("\n[PyIceberg]")
    try:
        import pyiceberg  # noqa: F401
        check("PyIceberg installed", True)
    except ImportError:
        check("PyIceberg installed", False, hint="pip install -e '.[dev]' includes pyiceberg")

    try:
        from pyiceberg.catalog.glue import GlueCatalog  # noqa: F401
        check("PyIceberg Glue extras installed", True)
    except ImportError:
        check("PyIceberg Glue extras installed", False, hint="pip install pyiceberg[glue]")

    # ── .env ──
    print("\n[Environment Variables]")
    env_file = Path(__file__).resolve().parent.parent / ".env"
    check(".env file exists", env_file.exists(), hint="cp .env.example .env")

    bronze = getvar("BRONZE_BUCKET")
    check(
        "BRONZE_BUCKET is set",
        bool(bronze) and bronze != "your-bronze-bucket-name",
        hint="Set a real S3 bucket name in .env (needed for Bronze manifests)",
    )

    silver = getvar("SILVER_BUCKET")
    check(
        "SILVER_BUCKET is set",
        bool(silver) and silver != "your-silver-bucket-name",
        hint="Set a real S3 bucket name in .env for Silver Iceberg storage",
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

    # ── S3 Silver bucket ──
    print("\n[S3 Silver Bucket]")
    silver_bucket_ok = False
    if silver and silver != "your-silver-bucket-name" and has_aws_cli:
        try:
            result = run_aws(["s3api", "head-bucket", "--bucket", silver])
            silver_bucket_ok = result.returncode == 0
            check(
                f"S3 bucket '{silver}' exists",
                silver_bucket_ok,
                hint="Deploy infrastructure/s3-silver-bucket.yaml stack",
            )
        except Exception:
            check(f"S3 bucket '{silver}' reachable", False)

        if silver_bucket_ok:
            try:
                result = run_aws([
                    "s3api", "get-bucket-versioning",
                    "--bucket", silver,
                    "--query", "Status",
                    "--output", "text",
                ])
                versioning = result.stdout.strip()
                check(
                    f"S3 bucket versioning enabled (Status={versioning})",
                    versioning == "Enabled",
                    hint="Versioning required for Iceberg - enable in CloudFormation",
                )
            except Exception:
                check("S3 bucket versioning check", False)
    else:
        check("S3 Silver bucket check", False, hint="Set SILVER_BUCKET first")

    # ── CloudFormation Stack ──
    print("\n[CloudFormation Stack]")
    if has_aws_cli:
        try:
            result = run_aws([
                "cloudformation", "describe-stacks",
                "--stack-name", "prediction-silver-bucket",
                "--query", "Stacks[0].StackStatus",
                "--output", "text",
                "--region", region,
            ])
            stack_status = result.stdout.strip() if result.returncode == 0 else ""
            ok = stack_status in (
                "CREATE_COMPLETE", "UPDATE_COMPLETE", "UPDATE_ROLLBACK_COMPLETE",
                "IMPORT_COMPLETE",
            )
            label = (
                f"Stack 'prediction-silver-bucket' deployed ({stack_status})"
                if ok else "Stack 'prediction-silver-bucket' deployed"
            )
            check(label, ok, hint="Deploy infrastructure/s3-silver-bucket.yaml")
        except Exception:
            check("Stack 'prediction-silver-bucket' check", False)
    else:
        check("CloudFormation stack check", False, hint="Install AWS CLI first")

    # ── Glue Catalog ──
    print("\n[AWS Glue Catalog]")
    namespaces_ok = []

    if has_aws_cli:
        # Check for silver_polymarket and silver_kalshi namespaces (databases)
        # Note: Implementation uses per-platform namespaces, not a single prediction_silver db
        for ns in ["silver_polymarket", "silver_kalshi"]:
            try:
                result = run_aws([
                    "glue", "get-database",
                    "--name", ns,
                    "--region", region,
                    "--output", "json",
                ])
                ns_ok = result.returncode == 0
                if ns_ok:
                    namespaces_ok.append(ns)
                check(
                    f"Glue namespace '{ns}' exists",
                    ns_ok,
                    hint="Run: prediction-data silver init-tables",
                )
            except Exception:
                check(f"Glue namespace '{ns}' check", False)
    else:
        check("Glue Catalog checks", False, hint="Install AWS CLI first")

    # ── Iceberg Tables ──
    print("\n[Iceberg Tables]")
    expected_tables = [
        ("silver_polymarket", "trades"),
        ("silver_polymarket", "markets"),
        ("silver_polymarket", "events"),
        ("silver_kalshi", "trades"),
        ("silver_kalshi", "markets"),
        ("silver_kalshi", "events"),
    ]

    tables_found = []
    if has_aws_cli:
        for namespace, table_name in expected_tables:
            try:
                result = run_aws([
                    "glue", "get-table",
                    "--database-name", namespace,
                    "--name", table_name,
                    "--region", region,
                    "--output", "json",
                ])
                table_ok = result.returncode == 0
                if table_ok:
                    tables_found.append((namespace, table_name))
                    # Check if it's an Iceberg table
                    table_data = json.loads(result.stdout)
                    table_type = (
                        table_data.get("Table", {})
                        .get("Parameters", {})
                        .get("table_type", "")
                    )
                    is_iceberg = table_type.lower() == "iceberg"
                    check(
                        f"Table '{namespace}.{table_name}' exists (Iceberg={is_iceberg})",
                        is_iceberg,
                        hint="Table exists but is not Iceberg format" if not is_iceberg else "",
                    )
                else:
                    check(
                        f"Table '{namespace}.{table_name}' exists",
                        False,
                        hint="Run: prediction-data silver init-tables",
                    )
            except Exception:
                check(f"Table '{namespace}.{table_name}' check", False)
    else:
        check("Iceberg table checks", False, hint="Install AWS CLI first")

    # ── Silver Module Structure ──
    print("\n[Silver Module Structure]")
    silver_root = Path(__file__).resolve().parent.parent / "src" / "prediction_data" / "silver"
    expected_modules = [
        "__init__.py",
        "catalog.py",
        "tables.py",
        "processor.py",
        "quality.py",
        "maintenance.py",
        "normalize.py",
        "dedup.py",
        "writer.py",
        "state.py",
        "discovery.py",
        "reader.py",
    ]
    for mod in expected_modules:
        path = silver_root / mod
        check(f"silver/{mod} exists", path.exists(), hint=f"Missing {path}")

    # ══════════════════════════════════════════════════════════════════════════
    # RUNTIME CHECKS - Verify Silver layer is actually working
    # ══════════════════════════════════════════════════════════════════════════

    print("\n" + "=" * 55)
    print("=== Runtime Verification (Silver Layer) ===\n")

    # ── PyIceberg Catalog Connection ──
    print("[Catalog Connection]")
    catalog_ok = False
    if silver and silver != "your-silver-bucket-name":
        try:
            from prediction_data.silver.catalog import load_catalog
            catalog = load_catalog()
            catalog_ok = True
            check("PyIceberg can connect to Glue Catalog", True)

            # List namespaces
            try:
                nss = catalog.list_namespaces()
                ns_names = [".".join(ns) for ns in nss]
                silver_nss = [n for n in ns_names if n.startswith("silver_")]
                check(
                    f"Catalog lists Silver namespaces ({len(silver_nss)} found)",
                    len(silver_nss) >= 2,
                    hint=f"Found: {silver_nss}",
                )
            except Exception as e:
                check(f"List namespaces ({e})", False)
        except Exception as e:
            check(f"PyIceberg Catalog connection ({e})", False)
    else:
        check("Catalog connection", False, hint="Set SILVER_BUCKET first")

    # ── Silver Table Data ──
    print("\n[Silver Table Data]")
    if catalog_ok:
        polymarket_tables = [
            ("silver_polymarket", "trades"),
            ("silver_polymarket", "markets"),
            ("silver_polymarket", "events"),
        ]
        for namespace, table_name in polymarket_tables:
            try:
                table = catalog.load_table((namespace, table_name))
                # Get snapshot count
                snapshots = list(table.metadata.snapshots)
                snapshot_count = len(snapshots)

                if snapshot_count > 0:
                    # Get row count from latest snapshot
                    latest = table.current_snapshot()
                    if latest and latest.summary:
                        row_count = int(latest.summary.get("total-records", 0))
                        check(
                            f"{namespace}.{table_name}: {row_count:,} rows, {snapshot_count} snapshots",
                            row_count > 0,
                            required=False,
                            hint="No data in table yet",
                        )
                    else:
                        check(
                            f"{namespace}.{table_name}: {snapshot_count} snapshots",
                            True,
                            required=False,
                        )
                else:
                    check(
                        f"{namespace}.{table_name} has data",
                        False,
                        required=False,
                        hint="No snapshots - run silver processing first",
                    )
            except Exception as e:
                check(f"{namespace}.{table_name} data check ({e})", False, required=False)

        # Kalshi tables are scaffolds - just check they exist
        for namespace, table_name in [
            ("silver_kalshi", "trades"),
            ("silver_kalshi", "markets"),
            ("silver_kalshi", "events"),
        ]:
            try:
                table = catalog.load_table((namespace, table_name))
                check(f"{namespace}.{table_name} scaffold exists", True)
            except Exception:
                check(
                    f"{namespace}.{table_name} scaffold exists",
                    False,
                    required=False,
                    hint="Run: prediction-data silver init-tables",
                )
    else:
        check("Silver table data checks", False, required=False, hint="Catalog not connected")

    # ── Processing State Store ──
    print("\n[Processing State Store]")
    if silver and has_aws_cli:
        state_prefix = f"s3://{silver}/silver/_state/"
        try:
            result = run_aws([
                "s3", "ls", state_prefix,
            ])
            # State store might be empty initially, that's ok
            state_ok = result.returncode == 0
            check(
                "Silver state store path accessible",
                state_ok,
                required=False,
                hint=f"Check {state_prefix} is writable",
            )
        except Exception:
            check("Silver state store check", False, required=False)
    else:
        check("Processing state store check", False, required=False)

    # ── Silver CLI Commands ──
    print("\n[Silver CLI Commands]")
    if cli_path:
        cli_commands = [
            (["prediction-data", "silver", "--help"], "silver --help"),
            (["prediction-data", "silver", "init-tables", "--help"], "silver init-tables --help"),
            (["prediction-data", "silver", "process", "--help"], "silver process --help"),
            (["prediction-data", "silver", "compact", "--help"], "silver compact --help"),
            (["prediction-data", "silver", "maintain", "--help"], "silver maintain --help"),
        ]
        for cmd, label in cli_commands:
            try:
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
                check(f"CLI: {label}", result.returncode == 0)
            except Exception:
                check(f"CLI: {label}", False)
    else:
        check("Silver CLI commands", False, hint="Install prediction-data first")

    # ── Quality Check Framework ──
    print("\n[Quality Check Framework]")
    try:
        from prediction_data.silver.quality import (
            NonNullCheck,
            UniquenessCheck,
            TimestampRangeCheck,
        )
        check("Quality check classes importable", True)
    except ImportError as e:
        check(f"Quality check classes importable ({e})", False)

    # ── Maintenance Operations ──
    print("\n[Maintenance Operations]")
    try:
        from prediction_data.silver.maintenance import (
            compact_table,
            expire_snapshots,
            remove_orphans,
        )
        check("Maintenance functions importable", True)
    except ImportError as e:
        check(f"Maintenance functions importable ({e})", False)

    # ── Bronze Data Availability (for Silver processing) ──
    print("\n[Bronze Data Availability]")
    if bronze and has_aws_cli:
        from datetime import datetime, timedelta

        today = datetime.utcnow().strftime("%Y-%m-%d")
        yesterday = (datetime.utcnow() - timedelta(days=1)).strftime("%Y-%m-%d")

        bronze_entities = [
            ("polymarket", "order_filled"),  # Source for Silver trades
            ("polymarket", "markets"),
            ("polymarket", "events"),
        ]

        for platform, entity in bronze_entities:
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
                check(f"Bronze {platform}/{entity} has recent data (dt={found_date})", True)
            else:
                check(
                    f"Bronze {platform}/{entity} has recent data",
                    False,
                    required=False,
                    hint=f"No Bronze data for {yesterday} or {today}",
                )
    else:
        check("Bronze data availability", False, required=False, hint="BRONZE_BUCKET not set")

    # ── Summary ──
    print("\n" + "=" * 55)
    print("=== Summary ===\n")
    if failures == 0 and warnings == 0:
        print(f"{PASS} All checks passed! Silver Lakehouse is fully operational.")
        print("    Release 02 exit criteria met - ready for sign-off and v2.0.0-silver tag.")
    elif failures == 0:
        print(f"{PASS} All required checks passed ({warnings} optional warning(s))")
        print("    Silver layer is operational. Review warnings if needed.")
    else:
        print(f"{FAIL} {failures} required check(s) failed, {warnings} warning(s)")
        print("    Fix failures before Release 02 can be completed.")
    print()
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
