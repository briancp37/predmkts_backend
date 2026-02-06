#!/usr/bin/env python3
"""
Markets Data Pipeline Diagnostics

This script traces the entire journey of markets data through:
1. External API (Polymarket Gamma API)
2. Bronze Layer (S3 raw JSONL)
3. Silver Layer (Iceberg tables in Glue)
4. Gold Layer (ClickHouse dimension tables)
5. REST API response

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


# =============================================================================
# Diagnostic Checks
# =============================================================================

class MarketsDiagnostics:
    """Comprehensive diagnostics for the markets data pipeline."""

    def __init__(self) -> None:
        self.s3 = boto3.client("s3")
        self.issues: list[str] = []
        self.warnings: list[str] = []

    def run_all(self) -> None:
        """Run all diagnostic checks."""
        print_header("MARKETS DATA PIPELINE DIAGNOSTICS")
        print(f"  Run time: {datetime.now(timezone.utc).isoformat()}")
        print(f"  Platform: polymarket")
        print(f"  Entity: markets")

        # Load settings
        from prediction_data.core.config import get_settings
        self.settings = get_settings()

        # Run checks for each layer
        self.check_external_api()
        self.check_bronze_layer()
        self.check_silver_layer()
        self.check_gold_layer()
        self.check_api_endpoint()
        self.check_schedules()

        # Print summary
        self.print_summary()

    def check_external_api(self) -> None:
        """Check connectivity to Polymarket Gamma API."""
        print_header("1. EXTERNAL API (Polymarket Gamma)")
        print_explanation(
            "Markets data originates from the Polymarket Gamma API. This API provides\n"
            "  market metadata including questions, descriptions, token IDs, and status.\n"
            "  Rate limit: 300 requests/10 seconds."
        )

        import httpx

        try:
            # Test API connectivity
            resp = httpx.get(
                "https://gamma-api.polymarket.com/markets",
                params={"limit": 1},
                timeout=10,
            )

            if resp.status_code == 200:
                data = resp.json()
                if data:
                    print_status("API Connectivity", "OK", "Gamma API is reachable")
                    print_status("Sample Market", "INFO", f"ID: {data[0].get('id', 'N/A')}")

                    # Check if API returns expected fields
                    required_fields = ["id", "question", "clobTokenIds", "updatedAt"]
                    missing = [f for f in required_fields if f not in data[0]]
                    if missing:
                        print_status("Schema Check", "WARN", f"Missing fields: {missing}")
                        self.warnings.append(f"API response missing fields: {missing}")
                    else:
                        print_status("Schema Check", "OK", "All required fields present")
                else:
                    print_status("API Response", "WARN", "Empty response")
                    self.warnings.append("Gamma API returned empty response")
            else:
                print_status("API Connectivity", "ERROR", f"HTTP {resp.status_code}")
                self.issues.append(f"Gamma API returned HTTP {resp.status_code}")

        except Exception as e:
            print_status("API Connectivity", "ERROR", str(e))
            self.issues.append(f"Cannot reach Gamma API: {e}")

    def check_bronze_layer(self) -> None:
        """Check Bronze layer data in S3."""
        print_header("2. BRONZE LAYER (S3 Raw Data)")
        print_explanation(
            "Bronze layer stores raw API responses as JSONL.gz files in S3.\n"
            "  Path: s3://{bucket}/bronze/polymarket/markets/dt=YYYY-MM-DD/run_id={uuid}/\n"
            "  Each ingestion run creates a manifest file (_manifest.json) with metadata."
        )

        bucket = self.settings.bronze_bucket
        prefix = "bronze/polymarket/markets/"

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
                self.issues.append("No Bronze markets data found in S3")
                return

            dates_found.sort(reverse=True)
            latest_date = dates_found[0]

            print_status("Date Partitions Found", "INFO", f"{len(dates_found)} dates")
            print_status("Latest Partition", "INFO", latest_date)

            # Check the latest partition for manifests
            latest_prefix = f"{prefix}dt={latest_date}/"
            manifests: list[dict[str, Any]] = []

            for page in paginator.paginate(Bucket=bucket, Prefix=latest_prefix):
                for obj in page.get("Contents", []):
                    if obj["Key"].endswith("manifest.json"):
                        # Read manifest
                        resp = self.s3.get_object(Bucket=bucket, Key=obj["Key"])
                        manifest = json.loads(resp["Body"].read().decode())
                        manifest["_key"] = obj["Key"]
                        manifest["_modified"] = obj["LastModified"]
                        manifests.append(manifest)

            if manifests:
                # Sort by timestamp
                manifests.sort(key=lambda m: m.get("ingestion_ts", ""), reverse=True)
                latest_manifest = manifests[0]

                ingestion_ts = latest_manifest.get("ingestion_ts", "")
                record_count = latest_manifest.get("row_count", latest_manifest.get("record_count", 0))
                snapshot_type = latest_manifest.get("snapshot_type", "unknown")

                # Parse timestamp and calculate age
                if ingestion_ts:
                    try:
                        ts = datetime.fromisoformat(ingestion_ts.replace("Z", "+00:00"))
                        age = format_age(ts)
                        age_hours = (datetime.now(timezone.utc) - ts).total_seconds() / 3600

                        if age_hours < 2:
                            print_status("Latest Ingestion", "OK", f"{age} ({record_count:,} records)")
                        elif age_hours < 24:
                            print_status("Latest Ingestion", "WARN", f"{age} ({record_count:,} records)")
                            self.warnings.append(f"Bronze markets data is {age} old")
                        else:
                            print_status("Latest Ingestion", "ERROR", f"{age} ({record_count:,} records)")
                            self.issues.append(f"Bronze markets data is stale: {age}")
                    except Exception:
                        print_status("Latest Ingestion", "INFO", f"{ingestion_ts} ({record_count:,} records)")

                print_status("Snapshot Type", "INFO", snapshot_type)
                print_status("Total Runs Today", "INFO", f"{len(manifests)} run(s)")

                # Check record count
                if record_count < 100000:
                    print_status("Record Count", "WARN", f"Only {record_count:,} records (expected ~360K)")
                    self.warnings.append(f"Low record count in Bronze: {record_count:,}")
                else:
                    print_status("Record Count", "OK", f"{record_count:,} records")
            else:
                print_status("Manifests", "ERROR", "No manifests found for latest date")
                self.issues.append(f"No manifests in Bronze for {latest_date}")

        except Exception as e:
            print_status("Bronze Check", "ERROR", str(e))
            self.issues.append(f"Bronze layer check failed: {e}")

    def check_silver_layer(self) -> None:
        """Check Silver layer Iceberg tables."""
        print_header("3. SILVER LAYER (Iceberg Tables)")
        print_explanation(
            "Silver layer normalizes Bronze data into Iceberg tables in AWS Glue Catalog.\n"
            "  Table: silver_polymarket.markets\n"
            "  Processing: Every 30 minutes via EventBridge schedule.\n"
            "  Tracks processed manifests to avoid reprocessing."
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

            # Load the markets table
            table = catalog.load_table("silver_polymarket.markets")

            # Get table metadata
            current_snapshot = table.current_snapshot()
            if current_snapshot:
                snapshot_ts = datetime.fromtimestamp(
                    current_snapshot.timestamp_ms / 1000, tz=timezone.utc
                )
                age = format_age(snapshot_ts)
                age_hours = (datetime.now(timezone.utc) - snapshot_ts).total_seconds() / 3600

                if age_hours < 1:
                    print_status("Latest Snapshot", "OK", f"{age}")
                elif age_hours < 24:
                    print_status("Latest Snapshot", "WARN", f"{age}")
                    self.warnings.append(f"Silver markets snapshot is {age} old")
                else:
                    print_status("Latest Snapshot", "ERROR", f"{age}")
                    self.issues.append(f"Silver markets data is stale: {age}")

                print_status("Snapshot ID", "INFO", str(current_snapshot.snapshot_id))
            else:
                print_status("Snapshot", "ERROR", "No snapshots found")
                self.issues.append("Silver markets table has no snapshots")

            # Count rows (sample scan)
            try:
                scan = table.scan(limit=1)
                df = scan.to_pandas()
                # Do a full count
                full_scan = table.scan()
                row_count = sum(1 for _ in full_scan.to_arrow().to_batches())
                # Actually let's use a faster method
                import pyarrow as pa
                arrow_table = table.scan().to_arrow()
                row_count = arrow_table.num_rows

                if row_count < 100000:
                    print_status("Row Count", "WARN", f"{row_count:,} rows (expected ~360K)")
                    self.warnings.append(f"Low row count in Silver: {row_count:,}")
                else:
                    print_status("Row Count", "OK", f"{row_count:,} rows")
            except Exception as e:
                print_status("Row Count", "WARN", f"Could not count: {e}")

            # Check partitions
            print_status("Partitioning", "INFO", str(table.spec()))

        except Exception as e:
            print_status("Silver Check", "ERROR", str(e))
            self.issues.append(f"Silver layer check failed: {e}")

    def check_gold_layer(self) -> None:
        """Check Gold layer in ClickHouse."""
        print_header("4. GOLD LAYER (ClickHouse)")
        print_explanation(
            "Gold layer serves dimension tables via ClickHouse for fast API queries.\n"
            "  Tables: dim_market, dim_outcome, dim_event, market_mark_daily\n"
            "  Loading: Daily at midnight UTC via 'gold daily-run'.\n"
            "  The API joins these tables to build market responses."
        )

        try:
            from prediction_data.gold.clickhouse import get_client

            client = get_client()

            # Test connection
            result = client.query("SELECT 1")
            print_status("ClickHouse Connection", "OK", f"{self.settings.clickhouse_host}")

            # Check each relevant table
            tables_to_check = [
                ("dim_market", 100000, "Market dimension table with questions, descriptions"),
                ("dim_outcome", 0, "Outcome dimension with token IDs and names"),
                ("dim_event", 50000, "Event dimension with categories"),
                ("market_mark_daily", 1000, "Daily market metrics (volume, price)"),
            ]

            print_subheader("Table Row Counts")

            for table_name, min_expected, description in tables_to_check:
                try:
                    result = client.query(f"SELECT count() FROM {table_name}")
                    count = result.first_row[0]

                    if count == 0:
                        print_status(table_name, "ERROR", f"0 rows - {description}")
                        self.issues.append(f"Gold table {table_name} is empty")
                    elif count < min_expected:
                        print_status(table_name, "WARN", f"{count:,} rows (expected >{min_expected:,})")
                        self.warnings.append(f"Low row count in {table_name}: {count:,}")
                    else:
                        print_status(table_name, "OK", f"{count:,} rows")
                except Exception as e:
                    print_status(table_name, "ERROR", str(e))
                    self.issues.append(f"Cannot query {table_name}: {e}")

            # Check data freshness in dim_market
            print_subheader("Data Freshness")

            try:
                # Check when dim_market was last loaded (via dataset_freshness or partition)
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
                    print_status("market_mark_daily", "ERROR", "No data")
                    self.issues.append("market_mark_daily has no data")
            except Exception as e:
                print_status("Freshness Check", "WARN", str(e))

            # Check dim_outcome specifically (critical for API)
            print_subheader("dim_outcome Analysis (Critical for API)")

            try:
                result = client.query("SELECT count() FROM dim_outcome")
                outcome_count = result.first_row[0]

                if outcome_count == 0:
                    print_status("dim_outcome", "ERROR", "EMPTY - This is why API returns blank data!")
                    self.issues.append("dim_outcome is empty - API cannot return outcome data")
                    print_explanation(
                        "The dim_outcome table maps token IDs to outcome names (Yes/No).\n"
                        "  Without this data, the API cannot populate outcome fields.\n"
                        "  FIX: Run 'prediction-data gold load-dims --table dim_outcome'"
                    )
                else:
                    # Sample some outcomes
                    result = client.query("SELECT * FROM dim_outcome LIMIT 3")
                    print_status("dim_outcome", "OK", f"{outcome_count:,} outcomes loaded")
            except Exception as e:
                print_status("dim_outcome", "ERROR", str(e))

        except Exception as e:
            print_status("Gold Check", "ERROR", str(e))
            self.issues.append(f"Gold layer check failed: {e}")

    def check_api_endpoint(self) -> None:
        """Check the REST API endpoint."""
        print_header("5. REST API ENDPOINT")
        print_explanation(
            "The /api/v1/markets/advanced endpoint joins Gold tables to return market data.\n"
            "  It queries: dim_market + dim_event + market_mark_daily + dim_outcome\n"
            "  Then enriches with real-time CLOB order book data for bid/ask spreads."
        )

        import httpx

        try:
            # Call the API
            resp = httpx.get(
                "http://localhost:8000/api/v1/markets/advanced",
                params={"sortBy": "volume", "sortOrder": "desc", "limit": 5},
                timeout=30,
            )

            if resp.status_code == 200:
                print_status("API Response", "OK", f"HTTP {resp.status_code}")

                data = resp.json()
                markets = data.get("items", data.get("data", []))
                total = data.get("total", 0)

                print_status("Total Markets", "INFO", f"{total:,}")
                print_status("Returned", "INFO", f"{len(markets)} markets")

                if markets:
                    # Analyze first market
                    m = markets[0]
                    print_subheader("Sample Market Analysis")
                    print(f"    ID: {m.get('id', 'N/A')}")
                    print(f"    Question: {m.get('question', 'N/A')[:60]}...")
                    print(f"    Volume 24h: ${m.get('volume24h', 0):,.2f}")
                    print(f"    Liquidity: ${m.get('liquidity', 0):,.2f}")

                    outcomes = m.get("outcomes", [])
                    print(f"    Outcomes: {len(outcomes)}")

                    if not outcomes:
                        print_status("Outcomes", "ERROR", "No outcomes returned!")
                        self.issues.append("API returns markets without outcomes")
                        print_explanation(
                            "Markets have no outcomes because dim_outcome is likely empty.\n"
                            "  The API needs outcome data to populate Yes/No prices."
                        )
                    else:
                        for o in outcomes[:2]:
                            print(f"      - {o.get('name', 'N/A')}: {o.get('price', 0):.2%}")

                    # Check for blank fields
                    blank_fields = [k for k, v in m.items() if v is None or v == "" or v == 0]
                    if blank_fields:
                        print_status("Blank Fields", "WARN", ", ".join(blank_fields[:5]))
                else:
                    print_status("Markets", "ERROR", "No markets returned")
                    self.issues.append("API returns empty markets list")

            else:
                print_status("API Response", "ERROR", f"HTTP {resp.status_code}")
                self.issues.append(f"API returned HTTP {resp.status_code}")

        except httpx.ConnectError:
            print_status("API Connection", "ERROR", "Cannot connect to localhost:8000")
            self.issues.append("API server not running on localhost:8000")
        except Exception as e:
            print_status("API Check", "ERROR", str(e))
            self.issues.append(f"API check failed: {e}")

    def check_schedules(self) -> None:
        """Check scheduled tasks and infrastructure."""
        print_header("6. SCHEDULED TASKS & INFRASTRUCTURE")
        print_explanation(
            "Data flows through scheduled tasks:\n"
            "  - Bronze: Hourly ingestion from Gamma API\n"
            "  - Silver: Every 30 min processing from Bronze\n"
            "  - Gold: Daily loading at midnight UTC\n"
            "  These are configured via EventBridge schedules in AWS."
        )

        print_subheader("Expected Schedules")

        schedules = [
            ("Bronze Markets Ingestion", "Every 1 hour", "ingest polymarket-markets"),
            ("Silver Markets Catchup", "Every 30 min", "silver catchup --platform polymarket --entity markets"),
            ("Gold Daily Run", "Midnight UTC", "gold daily-run (includes load-dims)"),
            ("Gold CH Load", "00:30 UTC", "gold ch-load --all"),
        ]

        for name, schedule, command in schedules:
            print(f"    {name}")
            print(f"      Schedule: {schedule}")
            print(f"      Command: {command}")
            print()

        # Check if we can verify AWS schedules
        try:
            events = boto3.client("events")
            scheduler = boto3.client("scheduler")

            # Try to list schedules
            try:
                resp = scheduler.list_schedules(MaxResults=50)
                schedules_found = resp.get("Schedules", [])

                if schedules_found:
                    print_status("EventBridge Schedules", "OK", f"{len(schedules_found)} schedules found")

                    # Look for relevant schedules
                    market_schedules = [s for s in schedules_found if "market" in s["Name"].lower()]
                    if market_schedules:
                        for s in market_schedules:
                            state = s.get("State", "UNKNOWN")
                            status = "OK" if state == "ENABLED" else "WARN"
                            print_status(f"  {s['Name']}", status, state)
                else:
                    print_status("EventBridge Schedules", "WARN", "No schedules found")
                    self.warnings.append("No EventBridge schedules found in AWS")
            except Exception as e:
                print_status("Scheduler API", "WARN", f"Cannot check: {e}")

        except Exception as e:
            print_status("AWS Check", "INFO", "Skipped (credentials/permissions)")

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
        if self.issues:
            print_header("RECOMMENDED FIXES")

            if any("dim_outcome" in i for i in self.issues):
                print("""
  1. Load dim_outcome table:
     The dim_outcome table maps token IDs to outcome names. Without it,
     the API cannot return outcome data (Yes/No prices).

     Run: prediction-data gold load-dims --table dim_outcome

     Note: This may require Silver markets data to be populated first.
""")

            if any("empty" in i.lower() for i in self.issues):
                print("""
  2. Run full Gold dimension load:
     If dimension tables are empty, run the full load process:

     Run: prediction-data gold load-dims

     This loads: dim_platform, dim_market, dim_event, dim_category, dim_outcome
""")

            if any("stale" in i.lower() for i in self.issues):
                print("""
  3. Catch up stale data:
     If data is stale, run the catchup commands:

     Bronze: prediction-data backfill catchup --platform polymarket --entity markets
     Silver: prediction-data silver catchup --platform polymarket --entity markets
     Gold:   prediction-data gold daily-run
""")

        print("\n" + "=" * 80)
        print(f"  Diagnostics complete at {datetime.now(timezone.utc).isoformat()}")
        print("=" * 80 + "\n")


def main() -> None:
    """Run market diagnostics."""
    diag = MarketsDiagnostics()
    diag.run_all()

    # Exit with error code if issues found
    if diag.issues:
        sys.exit(1)


if __name__ == "__main__":
    main()
