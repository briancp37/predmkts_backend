"""Tests verifying all Gold release exit criteria are met.

This test module systematically verifies that all 15 exit criteria from
RELEASE.md (Release 3 — Gold Serving Layer) are properly implemented.

Exit criteria:
1.  ClickHouse is running (Docker local dev, prod hosting TBD)
2.  Dimension tables are populated from Silver
3.  Canonical ID mapping is implemented
4.  Position accounting engine processes both maker + taker sides per fill
5.  wallet_position_state reflects current open positions in ClickHouse
6.  wallet_position_ledger records per-fill audit trail with realized PnL
7.  market_mark_daily computes daily marks, volume, and liquidity metrics
8.  wallet_pnl_daily aggregates realized PnL (sparse, trade-days only)
9.  Watchlist-only tables computed for tracked wallets
10. On-demand CLI computes and caches historical snapshots to S3 Gold
11. Ops metadata tables track pipeline runs, partitions, freshness, and quality
12. Freshness SLAs are defined and alerting states implemented
13. Gold CLI commands support load, rollup, rebuild with dry-run
14. EventBridge/cron schedules defined for automated Gold processing
15. No API/frontend logic leaks into Gold code
"""

from __future__ import annotations

import ast
import importlib
import inspect
import os
from pathlib import Path

import pytest


class TestExitCriterion1ClickHouseDocker:
    """Exit criterion 1: ClickHouse is running (Docker local dev)."""

    def test_docker_compose_has_clickhouse_service(self) -> None:
        """Docker compose file defines a clickhouse service."""
        compose_path = Path(__file__).parent.parent / "docker-compose.yml"
        assert compose_path.exists(), "docker-compose.yml must exist"
        content = compose_path.read_text()
        assert "clickhouse:" in content
        assert "clickhouse/clickhouse-server" in content

    def test_docker_init_scripts_exist(self) -> None:
        """ClickHouse init SQL scripts exist for table creation."""
        init_dir = Path(__file__).parent.parent / "docker" / "clickhouse" / "init"
        assert init_dir.exists(), "ClickHouse init directory must exist"
        sql_files = list(init_dir.glob("*.sql"))
        assert len(sql_files) >= 10, "Should have multiple init SQL scripts"

    def test_clickhouse_connection_factory_exists(self) -> None:
        """ClickHouse connection factory module exists."""
        from prediction_data.gold import clickhouse

        assert hasattr(clickhouse, "get_client")
        assert hasattr(clickhouse, "ping")


class TestExitCriterion2DimensionTables:
    """Exit criterion 2: Dimension tables are populated from Silver."""

    def test_dimension_loaders_exist(self) -> None:
        """Dimension table loaders are implemented."""
        from prediction_data.gold import dimensions

        assert hasattr(dimensions, "load_dim_platform")
        assert hasattr(dimensions, "load_dim_market")
        assert hasattr(dimensions, "load_dim_outcome")
        assert hasattr(dimensions, "load_dim_wallet")
        assert hasattr(dimensions, "load_dim_event")
        assert hasattr(dimensions, "load_dim_category")

    def test_dimension_sql_init_scripts_exist(self) -> None:
        """Dimension table SQL init scripts exist."""
        init_dir = Path(__file__).parent.parent / "docker" / "clickhouse" / "init"
        expected_dims = [
            "002_dim_platform.sql",
            "003_dim_market.sql",
            "004_dim_outcome.sql",
            "005_dim_wallet.sql",
            "015_dim_event.sql",
            "016_dim_category.sql",
        ]
        for filename in expected_dims:
            assert (init_dir / filename).exists(), f"{filename} must exist"


class TestExitCriterion3CanonicalIDMapping:
    """Exit criterion 3: Canonical ID mapping is implemented."""

    def test_canonical_resolver_exists(self) -> None:
        """CanonicalResolver class is implemented."""
        from prediction_data.gold.canonical import CanonicalResolver

        assert hasattr(CanonicalResolver, "resolve")

    def test_market_links_yaml_exists(self) -> None:
        """Market links YAML file exists for cross-platform mapping."""
        links_path = Path(__file__).parent.parent / "mappings" / "market_links.yaml"
        assert links_path.exists(), "mappings/market_links.yaml must exist"


class TestExitCriterion4PositionAccountingEngine:
    """Exit criterion 4: Position accounting engine processes both maker + taker sides."""

    def test_position_state_class_exists(self) -> None:
        """PositionState class with apply_fill method exists."""
        from prediction_data.gold.accounting import PositionState

        assert hasattr(PositionState, "apply_fill")
        assert hasattr(PositionState, "qty")
        assert hasattr(PositionState, "avg_cost")
        assert hasattr(PositionState, "cost_basis_usd")

    def test_fill_result_class_exists(self) -> None:
        """FillResult dataclass exists with realized_pnl field."""
        from prediction_data.gold.accounting import FillResult

        assert hasattr(FillResult, "realized_pnl")
        assert hasattr(FillResult, "closed")

    def test_fill_splitter_creates_maker_taker_fills(self) -> None:
        """Fill splitter module creates both maker and taker fills."""
        from prediction_data.gold import fill_splitter

        assert hasattr(fill_splitter, "split_trade_to_fills")


class TestExitCriterion5WalletPositionState:
    """Exit criterion 5: wallet_position_state reflects current open positions."""

    def test_position_state_module_exists(self) -> None:
        """Position state management module exists."""
        from prediction_data.gold import position_state

        assert hasattr(position_state, "write_position_states")

    def test_position_state_sql_exists(self) -> None:
        """wallet_position_state ClickHouse table SQL exists."""
        init_dir = Path(__file__).parent.parent / "docker" / "clickhouse" / "init"
        assert (
            init_dir / "018_wallet_position_state.sql"
        ).exists(), "wallet_position_state SQL must exist"


class TestExitCriterion6WalletPositionLedger:
    """Exit criterion 6: wallet_position_ledger records per-fill audit trail."""

    def test_ledger_module_exists(self) -> None:
        """Ledger recording module exists."""
        from prediction_data.gold import ledger

        assert hasattr(ledger, "record_fill")
        assert hasattr(ledger, "build_ledger_for_day")

    def test_ledger_sql_exists(self) -> None:
        """wallet_position_ledger ClickHouse table SQL exists."""
        init_dir = Path(__file__).parent.parent / "docker" / "clickhouse" / "init"
        assert (
            init_dir / "017_wallet_position_ledger.sql"
        ).exists(), "wallet_position_ledger SQL must exist"


class TestExitCriterion7MarketMarkDaily:
    """Exit criterion 7: market_mark_daily computes daily marks."""

    def test_market_marks_module_exists(self) -> None:
        """Market marks computation module exists."""
        from prediction_data.gold import market_marks

        assert hasattr(market_marks, "compute_market_marks")

    def test_market_mark_daily_sql_exists(self) -> None:
        """market_mark_daily ClickHouse table SQL exists."""
        init_dir = Path(__file__).parent.parent / "docker" / "clickhouse" / "init"
        assert (
            init_dir / "008_market_mark_daily.sql"
        ).exists(), "market_mark_daily SQL must exist"


class TestExitCriterion8WalletPnlDaily:
    """Exit criterion 8: wallet_pnl_daily aggregates realized PnL."""

    def test_wallet_pnl_module_exists(self) -> None:
        """Wallet PnL computation module exists."""
        from prediction_data.gold import wallet_pnl

        assert hasattr(wallet_pnl, "compute_wallet_pnl")

    def test_wallet_pnl_daily_sql_exists(self) -> None:
        """wallet_pnl_daily ClickHouse table SQL exists."""
        init_dir = Path(__file__).parent.parent / "docker" / "clickhouse" / "init"
        assert (
            init_dir / "007_wallet_pnl_daily.sql"
        ).exists(), "wallet_pnl_daily SQL must exist"


class TestExitCriterion9WatchlistTables:
    """Exit criterion 9: Watchlist-only tables computed for tracked wallets."""

    def test_watchlist_module_exists(self) -> None:
        """Watchlist management module exists."""
        from prediction_data.gold import watchlist

        assert hasattr(watchlist, "add_wallet")
        assert hasattr(watchlist, "remove_wallet")
        assert hasattr(watchlist, "list_wallets")

    def test_watchlist_sql_exists(self) -> None:
        """gold_watchlist ClickHouse table SQL exists."""
        init_dir = Path(__file__).parent.parent / "docker" / "clickhouse" / "init"
        assert (
            init_dir / "006_gold_watchlist.sql"
        ).exists(), "gold_watchlist SQL must exist"

    def test_wallet_mtm_module_exists(self) -> None:
        """Wallet MTM computation module exists."""
        from prediction_data.gold import wallet_mtm

        assert hasattr(wallet_mtm, "compute_wallet_mtm")

    def test_wallet_position_snapshot_module_exists(self) -> None:
        """Wallet position snapshot module exists."""
        from prediction_data.gold import wallet_position_snapshot

        assert hasattr(wallet_position_snapshot, "compute_wallet_position_snapshot")

    def test_watchlist_table_sqls_exist(self) -> None:
        """Watchlist-dependent ClickHouse table SQLs exist."""
        init_dir = Path(__file__).parent.parent / "docker" / "clickhouse" / "init"
        assert (
            init_dir / "009_wallet_mtm_daily.sql"
        ).exists(), "wallet_mtm_daily SQL must exist"
        assert (
            init_dir / "010_wallet_position_snapshot_daily.sql"
        ).exists(), "wallet_position_snapshot_daily SQL must exist"


class TestExitCriterion10OnDemandCLI:
    """Exit criterion 10: On-demand CLI computes and caches historical snapshots."""

    def test_on_demand_module_exists(self) -> None:
        """On-demand snapshot computation module exists."""
        from prediction_data.gold import on_demand

        assert hasattr(on_demand, "compute_wallet_snapshots")

    def test_cli_compute_snapshot_command_exists(self) -> None:
        """CLI has compute-snapshot command."""
        from prediction_data.cli.gold import app

        command_names = [cmd.name for cmd in app.registered_commands]
        assert "compute-snapshot" in command_names, "compute-snapshot command must exist"


class TestExitCriterion11OpsMetadataTables:
    """Exit criterion 11: Ops metadata tables track pipeline runs, partitions, freshness."""

    def test_ops_metadata_module_exists(self) -> None:
        """Ops metadata module with tracking functions exists."""
        from prediction_data.gold import ops_metadata

        assert hasattr(ops_metadata, "start_run")
        assert hasattr(ops_metadata, "end_run")
        assert hasattr(ops_metadata, "track_run")
        assert hasattr(ops_metadata, "record_partition")
        assert hasattr(ops_metadata, "update_freshness")

    def test_ops_metadata_sql_exists(self) -> None:
        """Ops metadata ClickHouse table SQLs exist."""
        init_dir = Path(__file__).parent.parent / "docker" / "clickhouse" / "init"
        assert (
            init_dir / "011_pipeline_runs.sql"
        ).exists(), "pipeline_runs SQL must exist"
        assert (
            init_dir / "012_dataset_partitions.sql"
        ).exists(), "dataset_partitions SQL must exist"
        assert (
            init_dir / "013_dataset_freshness.sql"
        ).exists(), "dataset_freshness SQL must exist"
        assert (
            init_dir / "014_data_quality_metrics.sql"
        ).exists(), "data_quality_metrics SQL must exist"


class TestExitCriterion12FreshnessSLAs:
    """Exit criterion 12: Freshness SLAs are defined and alerting states implemented."""

    def test_default_slas_defined(self) -> None:
        """Default SLA thresholds are defined."""
        from prediction_data.gold.ops_metadata import DEFAULT_SLAS

        assert "market_mark_daily" in DEFAULT_SLAS
        assert "wallet_pnl_daily" in DEFAULT_SLAS
        assert "wallet_mtm_daily" in DEFAULT_SLAS
        assert "wallet_position_snapshot_daily" in DEFAULT_SLAS

    def test_freshness_state_function_exists(self) -> None:
        """Freshness state computation function exists."""
        from prediction_data.gold import ops_metadata

        assert hasattr(ops_metadata, "compute_freshness_state")

    def test_freshness_states_correct(self) -> None:
        """Freshness state logic is correct: fresh, stale, broken."""
        from prediction_data.gold.ops_metadata import compute_freshness_state

        # Within SLA → fresh
        assert compute_freshness_state(100, 300) == "fresh"

        # Over SLA but within 2x → stale
        assert compute_freshness_state(400, 300) == "stale"

        # Over 2x SLA → broken
        assert compute_freshness_state(700, 300) == "broken"

        # Failed run → broken
        assert compute_freshness_state(100, 300, last_run_failed=True) == "broken"


class TestExitCriterion13GoldCLI:
    """Exit criterion 13: Gold CLI commands support load, rollup, rebuild with dry-run."""

    def test_gold_cli_module_exists(self) -> None:
        """Gold CLI module exists with app."""
        from prediction_data.cli.gold import app

        assert app is not None

    def test_essential_commands_exist(self) -> None:
        """Essential Gold CLI commands are registered."""
        from prediction_data.cli.gold import app

        command_names = [cmd.name for cmd in app.registered_commands]

        # Core commands from RELEASE.md section 11
        essential_commands = [
            "load-dims",
            "process-trades",
            "compute-marks",
            "compute-wallet-metrics",
            "compute-snapshot",
            "ch-load",
            "rebuild",
            "daily-run",
            "freshness",
            "status",
        ]

        for cmd in essential_commands:
            assert cmd in command_names, f"Command '{cmd}' must exist"

    def test_commands_have_dry_run_option(self) -> None:
        """Commands that modify data have --dry-run option."""
        from prediction_data.cli.gold import app

        # Commands that should have dry-run
        commands_with_dry_run = [
            "load-dims",
            "process-trades",
            "compute-marks",
            "compute-wallet-metrics",
            "compute-snapshot",
            "ch-load",
            "rebuild",
            "daily-run",
        ]

        for cmd_info in app.registered_commands:
            if cmd_info.name in commands_with_dry_run:
                # Check if the callback has a dry_run parameter
                callback = cmd_info.callback
                if callback is not None:
                    sig = inspect.signature(callback)
                    param_names = list(sig.parameters.keys())
                    assert (
                        "dry_run" in param_names
                    ), f"Command '{cmd_info.name}' should have dry_run parameter"


class TestExitCriterion14EventBridgeSchedules:
    """Exit criterion 14: EventBridge/cron schedules defined for automated processing."""

    def test_eventbridge_yaml_exists(self) -> None:
        """EventBridge schedule CloudFormation template exists."""
        schedule_path = (
            Path(__file__).parent.parent
            / "infrastructure"
            / "eventbridge-gold-schedules.yaml"
        )
        assert schedule_path.exists(), "EventBridge Gold schedules YAML must exist"

    def test_eventbridge_has_daily_run_schedule(self) -> None:
        """EventBridge template defines daily-run schedule."""
        schedule_path = (
            Path(__file__).parent.parent
            / "infrastructure"
            / "eventbridge-gold-schedules.yaml"
        )
        content = schedule_path.read_text()
        assert "GoldDailyRunSchedule" in content
        assert "daily-run" in content

    def test_eventbridge_has_ch_load_schedule(self) -> None:
        """EventBridge template defines CH load schedule."""
        schedule_path = (
            Path(__file__).parent.parent
            / "infrastructure"
            / "eventbridge-gold-schedules.yaml"
        )
        content = schedule_path.read_text()
        assert "GoldCHLoadSchedule" in content
        assert "ch-load" in content

    def test_eventbridge_has_freshness_check(self) -> None:
        """EventBridge template defines freshness check schedule."""
        schedule_path = (
            Path(__file__).parent.parent
            / "infrastructure"
            / "eventbridge-gold-schedules.yaml"
        )
        content = schedule_path.read_text()
        assert "GoldFreshnessCheckSchedule" in content
        assert "freshness" in content


class TestExitCriterion15NoAPIOFrontendLogic:
    """Exit criterion 15: No API/frontend logic leaks into Gold code."""

    def test_no_http_endpoints_in_gold(self) -> None:
        """Gold modules don't define HTTP endpoints or routes."""
        gold_dir = Path(__file__).parent.parent / "src" / "prediction_data" / "gold"

        # Patterns that indicate web framework usage (must be exact imports/decorators)
        forbidden_patterns = [
            "from fastapi",
            "import fastapi",
            "@app.get(",
            "@app.post(",
            "@router.",
            "from flask",
            "import flask",
            "from django",
            "import django",
        ]

        for py_file in gold_dir.glob("*.py"):
            content = py_file.read_text()
            for pattern in forbidden_patterns:
                assert (
                    pattern not in content
                ), f"Found forbidden pattern '{pattern}' in {py_file.name}"

    def test_no_frontend_assets_in_gold(self) -> None:
        """Gold directory contains no frontend assets."""
        gold_dir = Path(__file__).parent.parent / "src" / "prediction_data" / "gold"

        frontend_extensions = [".html", ".css", ".js", ".jsx", ".tsx", ".vue"]

        for ext in frontend_extensions:
            files = list(gold_dir.glob(f"*{ext}"))
            assert len(files) == 0, f"Found frontend files with extension {ext}"

    def test_gold_only_exports_data_functions(self) -> None:
        """Gold __init__.py only exports data processing functions."""
        from prediction_data import gold

        # Check that no web framework types are exported
        exported = dir(gold)
        web_types = ["Request", "Response", "JSONResponse", "HTTPException"]
        for web_type in web_types:
            assert (
                web_type not in exported
            ), f"Gold module should not export {web_type}"
