#!/usr/bin/env python3
"""
Trades/Order Filled Data Pipeline Diagnostics

This script traces the entire journey of trades data through:
1. External API (Polymarket Goldsky Subgraph - OrderFilledEvents)
2. Bronze Layer (S3 raw JSONL - order_filled)
3. Silver Layer (Iceberg tables - trades)
4. Gold Layer (ClickHouse - position accounting, marks, PnL)
5. EventBridge Schedules

It checks data freshness, row counts, and identifies issues at each level.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone
from typing import Any

import boto3
import structlog

# Configure logging for clean console output
structlog.configure(
    processors=[
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.dev.ConsoleRenderer(colors=True),
    ],
    wrapper_class=structlog.make_filtering_bound_logger(0),
    context_class=dict,
    logger_factory=structlog.PrintLoggerFactory(),
)

logger = structlog.get_logger()


# =============================================================================
# Console Output Helpers
# =============================================================================

def print_header(title: str) -> None:
    """Print a section header."""
    width = 80
    print("\n" + "=" * width)
    print(f"  {title}")
    print("=" * width)


def print_subheader(title: str) -> None:
    """Print a subsection header."""
    print(f"\n--- {title} ---")


def print_status(label: str, status: str, details: str = "") -> None:
    """Print a status line with color coding."""
    status_colors = {
        "OK": "\033[92m",      # Green
        "WARN": "\033[93m",    # Yellow
        "ERROR": "\033[91m",   # Red
        "INFO": "\033[94m",    # Blue
    }
    reset = "\033[0m"
    color = status_colors.get(status, "")
    status_str = f"[{color}{status}{reset}]"
    if details:
        print(f"  {status_str} {label}: {details}")
    else:
        print(f"  {status_str} {label}")


def print_explanation(text: str) -> None:
    """Print an explanation in italics."""
    print(f"\n  \033[3m{text}\033[0m\n")


def format_age(dt: datetime) -> str:
    """Format a datetime as a human-readable age."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    now = datetime.now(timezone.utc)
    delta = now - dt

    if delta.total_seconds() < 60:
        return f"{int(delta.total_seconds())}s ago"
    elif delta.total_seconds() < 3600:
        return f"{int(delta.total_seconds() / 60)}m ago"
    elif delta.total_seconds() < 86400:
        return f"{delta.total_seconds() / 3600:.1f}h ago"
    else:
        return f"{delta.days}d ago"


def format_number(n: int | float) -> str:
    """Format a number with K/M suffixes for readability."""
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}M"
    elif n >= 1_000:
        return f"{n / 1_000:.1f}K"
    else:
        return f"{n:,}"


# =============================================================================
# Diagnostic Checks
# =============================================================================

class TradesDiagnostics:
    """Comprehensive diagnostics for the trades/order_filled data pipeline."""

    def __init__(self) -> None:
        self.s3 = boto3.client("s3")
        self.issues: list[str] = []
        self.warnings: list[str] = []

    def run_all(self) -> None:
        """Run all diagnostic checks."""
        print_header("TRADES/ORDER FILLED DATA PIPELINE DIAGNOSTICS")
        print(f"  Run time: {datetime.now(timezone.utc).isoformat()}")
        print(f"  Platform: polymarket")
        print(f"  Entity: order_filled -> trades")

        # Load settings
        from prediction_data.core.config import get_settings
        self.settings = get_settings()

        # Run checks for each layer
        self.check_external_api()
        self.check_bronze_layer()
        self.check_silver_layer()
        self.check_gold_layer()
        self.check_schedules()

        # Print summary
        self.print_summary()

    def check_external_api(self) -> None:
        """Check connectivity to Polymarket Goldsky Subgraph."""
        print_header("1. EXTERNAL API (Polymarket Goldsky Subgraph)")
        print_explanation(
            "Order filled events originate from the Polymarket Goldsky Subgraph.\n"
            "  Endpoint: api.goldsky.com/.../orderbook-subgraph/prod/gn\n"
            "  This is a GraphQL API with no hard rate limit (use page_delay).\n"
            "  Events contain: maker, taker, amounts, fees, transaction hashes."
        )

        import httpx

        goldsky_url = (
            "https://api.goldsky.com/api/public/"
            "project_cl6mb8i9h0003e201j6li0diw/subgraphs/orderbook-subgraph/prod/gn"
        )

        # Query for recent events (last hour)
        now_ts = int(datetime.now(timezone.utc).timestamp())
        hour_ago_ts = now_ts - 3600

        query = """
        {
            orderFilledEvents(
                first: 5
                orderBy: timestamp
                orderDirection: desc
                where: { timestamp_gte: %d }
            ) {
                id
                transactionHash
                timestamp
                maker
                taker
                makerAssetId
                takerAssetId
                makerAmountFilled
                takerAmountFilled
                fee
            }
        }
        """ % hour_ago_ts

        try:
            resp = httpx.post(
                goldsky_url,
                json={"query": query},
                timeout=30,
            )

            if resp.status_code == 200:
                data = resp.json()

                if "errors" in data:
                    print_status("API Response", "ERROR", f"GraphQL errors: {data['errors']}")
                    self.issues.append(f"Goldsky API returned GraphQL errors")
                    return

                events = data.get("data", {}).get("orderFilledEvents", [])
                print_status("API Connectivity", "OK", "Goldsky subgraph is reachable")
                print_status("Recent Events (1h)", "INFO", f"{len(events)} events found")

                if events:
                    latest = events[0]
                    latest_ts = datetime.fromtimestamp(int(latest["timestamp"]), tz=timezone.utc)
                    age = format_age(latest_ts)

                    print_status("Latest Event", "INFO", f"{age}")
                    print_status("Sample Tx Hash", "INFO", latest.get("transactionHash", "N/A")[:20] + "...")

                    # Check schema
                    required_fields = ["id", "timestamp", "maker", "taker", "makerAmountFilled"]
                    missing = [f for f in required_fields if f not in latest]
                    if missing:
                        print_status("Schema Check", "WARN", f"Missing fields: {missing}")
                        self.warnings.append(f"Goldsky response missing fields: {missing}")
                    else:
                        print_status("Schema Check", "OK", "All required fields present")

                    # Calculate approximate volume from sample
                    total_volume = sum(
                        int(e.get("makerAmountFilled", 0)) / 1e6
                        for e in events
                    )
                    print_status("Sample Volume", "INFO", f"${total_volume:,.2f} USDC ({len(events)} events)")
                else:
                    print_status("Recent Activity", "WARN", "No events in last hour")
                    self.warnings.append("No order filled events in the last hour")
            else:
                print_status("API Connectivity", "ERROR", f"HTTP {resp.status_code}")
                self.issues.append(f"Goldsky API returned HTTP {resp.status_code}")

        except Exception as e:
            print_status("API Connectivity", "ERROR", str(e))
            self.issues.append(f"Cannot reach Goldsky API: {e}")

    def check_bronze_layer(self) -> None:
        """Check Bronze layer data in S3."""
        print_header("2. BRONZE LAYER (S3 Raw Data - order_filled)")
        print_explanation(
            "Bronze layer stores raw order filled events as JSONL.gz files in S3.\n"
            "  Path: s3://{bucket}/bronze/polymarket/order_filled/dt=YYYY-MM-DD/\n"
            "  Expected volume: 50K-500K events/day depending on market activity.\n"
            "  Ingestion: Every 10 minutes via 'backfill catchup'."
        )

        bucket = self.settings.bronze_bucket
        prefix = "bronze/polymarket/order_filled/"

        print_subheader("Recent Ingestion Runs")

        try:
            # List recent date partitions
            paginator = self.s3.get_paginator("list_objects_v2")

            # Get all dt= partitions
            dates_found: list[str] = []
            for page in paginator.paginate(Bucket=bucket, Prefix=prefix, Delimiter="/"):
                for cp in page.get("CommonPrefixes", []):
                    p = cp["Prefix"]
                    if "dt=" in p:
                        date_str = p.split("dt=")[1].rstrip("/")
                        dates_found.append(date_str)

            if not dates_found:
                print_status("Bronze Data", "ERROR", "No date partitions found")
                self.issues.append("No Bronze order_filled data found in S3")
                return

            dates_found.sort(reverse=True)
            latest_date = dates_found[0]
            today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

            print_status("Date Partitions Found", "INFO", f"{len(dates_found)} dates")
            print_status("Latest Partition", "INFO", latest_date)

            # Check if we're current
            if latest_date < today:
                days_behind = (datetime.strptime(today, "%Y-%m-%d") -
                               datetime.strptime(latest_date, "%Y-%m-%d")).days
                if days_behind == 1:
                    print_status("Data Currency", "OK", "Current (yesterday's data expected)")
                else:
                    print_status("Data Currency", "WARN", f"{days_behind} days behind")
                    self.warnings.append(f"Bronze order_filled is {days_behind} days behind")
            else:
                print_status("Data Currency", "OK", "Current (today's partition exists)")

            # Check the latest partition for manifests
            latest_prefix = f"{prefix}dt={latest_date}/"
            manifests: list[dict[str, Any]] = []
            total_record_count = 0

            for page in paginator.paginate(Bucket=bucket, Prefix=latest_prefix):
                for obj in page.get("Contents", []):
                    if obj["Key"].endswith("manifest.json"):
                        # Read manifest
                        resp = self.s3.get_object(Bucket=bucket, Key=obj["Key"])
                        manifest = json.loads(resp["Body"].read().decode())
                        manifest["_key"] = obj["Key"]
                        manifest["_modified"] = obj["LastModified"]
                        manifests.append(manifest)
                        total_record_count += manifest.get("record_count", 0)

            if manifests:
                # Sort by timestamp
                manifests.sort(key=lambda m: m.get("ingestion_ts", ""), reverse=True)
                latest_manifest = manifests[0]

                ingestion_ts = latest_manifest.get("ingestion_ts", "")
                record_count = latest_manifest.get("record_count", 0)

                # Parse timestamp and calculate age
                if ingestion_ts:
                    try:
                        ts = datetime.fromisoformat(ingestion_ts.replace("Z", "+00:00"))
                        age = format_age(ts)
                        age_minutes = (datetime.now(timezone.utc) - ts).total_seconds() / 60

                        if age_minutes < 30:
                            print_status("Latest Ingestion", "OK", f"{age} ({format_number(record_count)} records)")
                        elif age_minutes < 120:
                            print_status("Latest Ingestion", "WARN", f"{age} ({format_number(record_count)} records)")
                            self.warnings.append(f"Bronze order_filled data is {age} old")
                        else:
                            print_status("Latest Ingestion", "ERROR", f"{age} ({format_number(record_count)} records)")
                            self.issues.append(f"Bronze order_filled data is stale: {age}")
                    except Exception:
                        print_status("Latest Ingestion", "INFO", f"{ingestion_ts} ({format_number(record_count)} records)")

                print_status("Total Runs Today", "INFO", f"{len(manifests)} run(s)")
                print_status("Total Records Today", "INFO", format_number(total_record_count))

                # Check expected volume
                if total_record_count < 10000:
                    print_status("Daily Volume", "WARN", f"Low volume: {format_number(total_record_count)} (expected 50K-500K)")
                    self.warnings.append(f"Low daily volume in Bronze: {total_record_count:,}")
                else:
                    print_status("Daily Volume", "OK", f"{format_number(total_record_count)} records")

            else:
                print_status("Manifests", "ERROR", "No manifests found for latest date")
                self.issues.append(f"No manifests in Bronze for {latest_date}")

            # Check previous days for consistency
            print_subheader("Historical Data (Last 7 Days)")
            for i, dt in enumerate(dates_found[:7]):
                dt_prefix = f"{prefix}dt={dt}/"
                day_manifests = []
                day_records = 0
                for page in paginator.paginate(Bucket=bucket, Prefix=dt_prefix):
                    for obj in page.get("Contents", []):
                        if obj["Key"].endswith("manifest.json"):
                            resp = self.s3.get_object(Bucket=bucket, Key=obj["Key"])
                            manifest = json.loads(resp["Body"].read().decode())
                            day_manifests.append(manifest)
                            day_records += manifest.get("record_count", 0)

                if day_records == 0:
                    print_status(f"  {dt}", "WARN", "No data")
                else:
                    print_status(f"  {dt}", "OK", f"{format_number(day_records)} records ({len(day_manifests)} runs)")

        except Exception as e:
            print_status("Bronze Check", "ERROR", str(e))
            self.issues.append(f"Bronze layer check failed: {e}")

    def check_silver_layer(self) -> None:
        """Check Silver layer Iceberg tables."""
        print_header("3. SILVER LAYER (Iceberg Tables - trades)")
        print_explanation(
            "Silver layer normalizes Bronze order_filled events into trades.\n"
            "  Table: silver_polymarket.trades\n"
            "  Processing: Every 10 minutes via EventBridge schedule.\n"
            "  Columns: trade_id, market_id, outcome_id, price, quantity, side, etc."
        )

        try:
            from pyiceberg.catalog import load_catalog

            # Connect to Glue catalog
            catalog = load_catalog(
                "glue",
                **{
                    "type": "glue",
                    "region_name": self.settings.aws_region,
                    "warehouse": f"s3://{self.settings.silver_bucket}/silver/",
                },
            )

            print_status("Glue Catalog", "OK", "Connected")

            # Load the trades table
            try:
                table = catalog.load_table("silver_polymarket.trades")
            except Exception as e:
                print_status("Trades Table", "ERROR", f"Cannot load: {e}")
                self.issues.append("Silver trades table not found or inaccessible")
                return

            # Get table metadata
            current_snapshot = table.current_snapshot()
            if current_snapshot:
                snapshot_ts = datetime.fromtimestamp(
                    current_snapshot.timestamp_ms / 1000, tz=timezone.utc
                )
                age = format_age(snapshot_ts)
                age_minutes = (datetime.now(timezone.utc) - snapshot_ts).total_seconds() / 60

                if age_minutes < 30:
                    print_status("Latest Snapshot", "OK", f"{age}")
                elif age_minutes < 120:
                    print_status("Latest Snapshot", "WARN", f"{age}")
                    self.warnings.append(f"Silver trades snapshot is {age} old")
                else:
                    print_status("Latest Snapshot", "ERROR", f"{age}")
                    self.issues.append(f"Silver trades data is stale: {age}")

                print_status("Snapshot ID", "INFO", str(current_snapshot.snapshot_id))
            else:
                print_status("Snapshot", "ERROR", "No snapshots found")
                self.issues.append("Silver trades table has no snapshots")
                return

            # Get snapshot summary stats (avoid full table scan)
            print_subheader("Snapshot Statistics")
            try:
                summary = current_snapshot.summary
                if summary:
                    total_records = int(summary.get("total-records", 0))
                    total_files = int(summary.get("total-data-files", 0))
                    added_records = int(summary.get("added-records", 0))

                    if total_records < 1000:
                        print_status("Total Records", "WARN", f"{format_number(total_records)} (expected millions)")
                        self.warnings.append(f"Low row count in Silver trades: {total_records:,}")
                    else:
                        print_status("Total Records", "OK", f"{format_number(total_records)}")
                    print_status("Data Files", "INFO", format_number(total_files))
                    print_status("Added in Last Snapshot", "INFO", format_number(added_records))
                else:
                    print_status("Snapshot Summary", "WARN", "No summary available")

            except Exception as e:
                print_status("Statistics", "WARN", f"Could not read: {e}")

            # Check table schema
            print_subheader("Table Schema")
            schema_fields = [f.name for f in table.schema().fields]
            expected_fields = ["event_ts", "platform_market_id", "price", "usd_amount", "maker", "taker"]
            missing = [f for f in expected_fields if f not in schema_fields]
            if missing:
                print_status("Schema", "WARN", f"Missing expected fields: {missing}")
            else:
                print_status("Schema", "OK", f"{len(schema_fields)} columns")
            print(f"      Columns: {', '.join(schema_fields[:8])}...")

        except ImportError:
            print_status("PyIceberg", "ERROR", "pyiceberg not installed")
            self.issues.append("Cannot check Silver layer: pyiceberg not installed")
        except Exception as e:
            print_status("Silver Check", "ERROR", str(e))
            self.issues.append(f"Silver layer check failed: {e}")

    def check_gold_layer(self) -> None:
        """Check Gold layer in ClickHouse."""
        print_header("4. GOLD LAYER (ClickHouse)")
        print_explanation(
            "Gold layer provides aggregated views for fast queries:\n"
            "  - market_mark_daily: VWAP, volume, prices per market per day\n"
            "  - wallet_pnl_daily: Realized PnL per wallet per day\n"
            "  - wallet_position_ledger: Position accounting audit trail\n"
            "  - wallet_position_state: Current position per wallet/market"
        )

        try:
            from prediction_data.gold.clickhouse import get_client

            client = get_client()

            # Test connection
            result = client.query("SELECT 1")
            print_status("ClickHouse Connection", "OK", f"{self.settings.clickhouse_host}")

            # Check each relevant table
            tables_to_check = [
                ("market_mark_daily", 1000, "Daily market metrics (VWAP, volume, prices)"),
                ("wallet_pnl_daily", 100, "Daily realized PnL per wallet"),
                ("wallet_position_ledger", 1000, "Position accounting records"),
                ("wallet_position_state", 100, "Current position state"),
            ]

            print_subheader("Table Row Counts")

            for table_name, min_expected, description in tables_to_check:
                try:
                    result = client.query(f"SELECT count() FROM {table_name}")
                    count = result.first_row[0]

                    if count == 0:
                        print_status(table_name, "WARN", f"0 rows - {description}")
                        self.warnings.append(f"Gold table {table_name} is empty")
                    elif count < min_expected:
                        print_status(table_name, "WARN", f"{format_number(count)} rows (expected >{min_expected:,})")
                        self.warnings.append(f"Low row count in {table_name}: {count:,}")
                    else:
                        print_status(table_name, "OK", f"{format_number(count)} rows")
                except Exception as e:
                    if "doesn't exist" in str(e).lower() or "unknown table" in str(e).lower():
                        print_status(table_name, "WARN", "Table not created yet")
                        self.warnings.append(f"Gold table {table_name} does not exist")
                    else:
                        print_status(table_name, "ERROR", str(e))
                        self.issues.append(f"Cannot query {table_name}: {e}")

            # Check data freshness
            print_subheader("Data Freshness")

            try:
                result = client.query("""
                    SELECT max(day_utc) as latest_day
                    FROM market_mark_daily
                """)
                latest_day = result.first_row[0]
                if latest_day:
                    days_old = (datetime.now(timezone.utc).date() - latest_day).days
                    if days_old <= 1:
                        print_status("market_mark_daily", "OK", f"Latest: {latest_day}")
                    elif days_old <= 3:
                        print_status("market_mark_daily", "WARN", f"Latest: {latest_day} ({days_old}d old)")
                        self.warnings.append(f"market_mark_daily is {days_old} days old")
                    else:
                        print_status("market_mark_daily", "ERROR", f"Latest: {latest_day} ({days_old}d old)")
                        self.issues.append(f"market_mark_daily is stale: {days_old} days old")
                else:
                    print_status("market_mark_daily", "WARN", "No data")
            except Exception as e:
                print_status("market_mark_daily freshness", "WARN", str(e)[:50])

            try:
                result = client.query("""
                    SELECT max(day_utc) as latest_day
                    FROM wallet_pnl_daily
                """)
                latest_day = result.first_row[0]
                if latest_day:
                    days_old = (datetime.now(timezone.utc).date() - latest_day).days
                    if days_old <= 1:
                        print_status("wallet_pnl_daily", "OK", f"Latest: {latest_day}")
                    elif days_old <= 3:
                        print_status("wallet_pnl_daily", "WARN", f"Latest: {latest_day} ({days_old}d old)")
                    else:
                        print_status("wallet_pnl_daily", "ERROR", f"Latest: {latest_day} ({days_old}d old)")
                else:
                    print_status("wallet_pnl_daily", "WARN", "No data")
            except Exception as e:
                print_status("wallet_pnl_daily freshness", "WARN", str(e)[:50])

            # Check sample data quality
            print_subheader("Data Quality Checks")

            try:
                # Check for reasonable mark price values
                result = client.query("""
                    SELECT
                        count() as total,
                        countIf(mark_price < 0 OR mark_price > 1) as invalid_price,
                        countIf(volume_usd_24h < 0) as negative_volume
                    FROM market_mark_daily
                    WHERE day_utc >= today() - 7
                """)
                row = result.first_row
                total, invalid_price, negative_volume = row[0], row[1], row[2]

                if total > 0:
                    if invalid_price > 0:
                        pct = (invalid_price / total) * 100
                        print_status("Price Range Check", "WARN", f"{invalid_price} records ({pct:.1f}%) outside [0,1]")
                    else:
                        print_status("Price Range Check", "OK", "All mark prices in valid range")

                    if negative_volume > 0:
                        print_status("Volume Check", "ERROR", f"{negative_volume} negative volume records")
                        self.issues.append(f"Negative volume records in market_mark_daily")
                    else:
                        print_status("Volume Check", "OK", "No negative volumes")
                else:
                    print_status("Quality Checks", "WARN", "No recent data to validate")

            except Exception as e:
                print_status("Quality Checks", "WARN", f"Could not run: {e}")

            # Check top trading activity
            print_subheader("Recent Trading Activity (Last 24h)")

            try:
                result = client.query("""
                    SELECT
                        sum(volume_usd_24h) as total_volume,
                        count(DISTINCT market_id) as markets_traded,
                        sum(trades_count_24h) as total_trades,
                        count() as records
                    FROM market_mark_daily
                    WHERE day_utc >= today() - 1
                """)
                row = result.first_row
                total_volume, markets_traded, total_trades, records = row[0], row[1], row[2], row[3]

                if total_volume and total_volume > 0:
                    print_status("24h Volume", "INFO", f"${total_volume:,.0f} USD")
                    print_status("Markets Active", "INFO", f"{markets_traded:,}")
                    print_status("Trades Recorded", "INFO", format_number(total_trades))
                else:
                    print_status("24h Activity", "WARN", "No trading activity recorded")

            except Exception as e:
                print_status("Activity Check", "WARN", str(e)[:50])

        except ImportError:
            print_status("ClickHouse", "ERROR", "clickhouse-connect not installed")
            self.issues.append("Cannot check Gold layer: clickhouse-connect not installed")
        except Exception as e:
            print_status("Gold Check", "ERROR", str(e))
            self.issues.append(f"Gold layer check failed: {e}")

    def check_schedules(self) -> None:
        """Check scheduled tasks and EventBridge rules."""
        print_header("5. SCHEDULED TASKS & INFRASTRUCTURE")
        print_explanation(
            "Trades data flows through scheduled tasks:\n"
            "  - Bronze: Every 10 min (backfill catchup --entity order_filled)\n"
            "  - Silver: Every 10 min (silver catchup --entity trades)\n"
            "  - Gold: Daily at midnight (gold daily-run)\n"
            "  - Gold CH Load: 00:30 UTC (gold ch-load --all)"
        )

        print_subheader("Expected Schedules")

        schedules = [
            ("Bronze order_filled Catchup", "Every 10 min", "backfill catchup --platform polymarket --entity order_filled"),
            ("Silver trades Catchup", "Every 10 min", "silver catchup --platform polymarket --entity trades"),
            ("Gold Daily Run", "Midnight UTC", "gold daily-run (process-trades, compute-marks, compute-pnl)"),
            ("Gold CH Load", "00:30 UTC", "gold ch-load --all"),
            ("Gold Freshness Check", "01:00 UTC", "gold freshness"),
        ]

        for name, schedule, command in schedules:
            print(f"    {name}")
            print(f"      Schedule: {schedule}")
            print(f"      Command: {command}")
            print()

        # Try to check AWS EventBridge schedules
        try:
            scheduler = boto3.client("scheduler")

            try:
                resp = scheduler.list_schedules(MaxResults=50)
                schedules_found = resp.get("Schedules", [])

                if schedules_found:
                    print_status("EventBridge Schedules", "OK", f"{len(schedules_found)} schedules found")

                    # Look for relevant schedules
                    trade_schedules = [
                        s for s in schedules_found
                        if any(kw in s["Name"].lower() for kw in ["trade", "order", "silver", "gold"])
                    ]

                    if trade_schedules:
                        print_subheader("Trade-Related Schedules")
                        for s in trade_schedules:
                            state = s.get("State", "UNKNOWN")
                            status = "OK" if state == "ENABLED" else "WARN"
                            print_status(f"  {s['Name']}", status, state)
                            if state != "ENABLED":
                                self.warnings.append(f"Schedule {s['Name']} is {state}")
                    else:
                        print_status("Trade Schedules", "WARN", "No trade-related schedules found")
                        self.warnings.append("No trade-related EventBridge schedules found")
                else:
                    print_status("EventBridge Schedules", "WARN", "No schedules found")
                    self.warnings.append("No EventBridge schedules found in AWS")
            except Exception as e:
                print_status("Scheduler API", "INFO", f"Skipped: {str(e)[:50]}")

        except Exception as e:
            print_status("AWS Check", "INFO", "Skipped (credentials/permissions)")

        # Check ECS task status (if applicable)
        print_subheader("Recent ECS Task Activity")
        try:
            ecs = boto3.client("ecs")

            # List clusters
            clusters_resp = ecs.list_clusters()
            clusters = clusters_resp.get("clusterArns", [])

            if clusters:
                for cluster_arn in clusters[:1]:  # Check first cluster
                    # List recent tasks
                    tasks_resp = ecs.list_tasks(
                        cluster=cluster_arn,
                        maxResults=10,
                        desiredStatus="STOPPED",
                    )
                    task_arns = tasks_resp.get("taskArns", [])

                    if task_arns:
                        # Describe tasks
                        desc_resp = ecs.describe_tasks(cluster=cluster_arn, tasks=task_arns[:5])
                        tasks = desc_resp.get("tasks", [])

                        silver_tasks = [
                            t for t in tasks
                            if any("silver" in str(t.get("overrides", {})).lower()
                                   or "trade" in str(t.get("overrides", {})).lower()
                                   for _ in [1])
                        ]

                        if silver_tasks:
                            print_status("Recent ECS Tasks", "INFO", f"{len(silver_tasks)} trade-related tasks")
                        else:
                            print_status("Recent ECS Tasks", "INFO", "No recent trade-related tasks")
                    else:
                        print_status("ECS Tasks", "INFO", "No recent stopped tasks")
            else:
                print_status("ECS Clusters", "INFO", "No clusters found")

        except Exception as e:
            print_status("ECS Check", "INFO", f"Skipped: {str(e)[:40]}")

    def print_summary(self) -> None:
        """Print diagnostic summary."""
        print_header("DIAGNOSTIC SUMMARY")

        if self.issues:
            print("\n  \033[91mISSUES FOUND ({}):\033[0m".format(len(self.issues)))
            for i, issue in enumerate(self.issues, 1):
                print(f"    {i}. {issue}")

        if self.warnings:
            print("\n  \033[93mWARNINGS ({}):\033[0m".format(len(self.warnings)))
            for i, warning in enumerate(self.warnings, 1):
                print(f"    {i}. {warning}")

        if not self.issues and not self.warnings:
            print("\n  \033[92mAll checks passed!\033[0m")

        # Recommended fixes
        if self.issues or self.warnings:
            print_header("RECOMMENDED FIXES")

            if any("bronze" in i.lower() and "stale" in i.lower() for i in self.issues):
                print("""
  1. Catch up Bronze order_filled data:
     If Bronze ingestion is stale, run the catchup command:

     Run: prediction-data backfill catchup --platform polymarket --entity order_filled

     This will fetch all order filled events since the last ingestion.
""")

            if any("silver" in i.lower() and "stale" in i.lower() for i in self.issues):
                print("""
  2. Catch up Silver trades processing:
     If Silver processing is behind, run:

     Run: prediction-data silver catchup --platform polymarket --entity trades

     This will process all new Bronze manifests into the Silver Iceberg table.
""")

            if any("gold" in i.lower() or "market_mark" in i.lower() or "wallet_pnl" in i.lower() for i in self.issues):
                print("""
  3. Run Gold daily processing:
     If Gold tables are stale or empty, run:

     Run: prediction-data gold daily-run

     This runs: load-dims -> process-trades -> compute-marks -> compute-wallet-metrics

     To load Gold data into ClickHouse:
     Run: prediction-data gold ch-load --all --lookback-days 90
""")

            if any("table" in i.lower() and ("not exist" in i.lower() or "empty" in i.lower()) for i in self.warnings):
                print("""
  4. Initialize Gold tables:
     If Gold tables don't exist, they may need to be created:

     Check: prediction-data gold freshness
     Init:  prediction-data gold load-dims
""")

            if any("schedule" in w.lower() and "enabled" not in w.lower() for w in self.warnings):
                print("""
  5. Check EventBridge schedules:
     Some schedules may be disabled. Check AWS Console:

     AWS Console -> EventBridge -> Schedules

     Ensure trade-related schedules are ENABLED.
""")

        print("\n" + "=" * 80)
        print(f"  Diagnostics complete at {datetime.now(timezone.utc).isoformat()}")
        print("=" * 80 + "\n")


def main() -> None:
    """Run trades diagnostics."""
    diag = TradesDiagnostics()
    diag.run_all()

    # Exit with error code if issues found
    if diag.issues:
        sys.exit(1)


if __name__ == "__main__":
    main()
