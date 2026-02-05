"""Exit criteria verification tests for Release 1 (Bronze MVP).

These tests verify all 8 exit criteria can be confirmed through code inspection,
infrastructure template validation, and local test execution without live AWS.

Exit criteria:
1. S3 Bronze bucket exists with versioning enabled
2. Polymarket trades/markets/events ingestion runs on schedule
3. Kalshi trades/markets/events ingestion runs on schedule
4. Each run writes part-000.jsonl.gz and manifest.json
5. Ingestion is restart-safe (no overwrites, no mutable state)
6. Backfills work via same ECS task definitions
7. CloudWatch logs show successful, observable runs
8. No Silver/Gold assumptions exist in Bronze code
"""

import os
import re
from pathlib import Path

import yaml

INFRA_DIR = Path(__file__).resolve().parent.parent / "infrastructure"
SRC_DIR = Path(__file__).resolve().parent.parent / "src" / "prediction_data"


def _load_yaml(name: str) -> dict:
    """Load a CloudFormation YAML template, stripping !Sub/!Ref/etc."""
    path = INFRA_DIR / name
    # Add constructors for CloudFormation intrinsic functions so PyYAML doesn't choke
    loader = yaml.SafeLoader
    for tag in ("!Sub", "!Ref", "!GetAtt", "!If", "!Not", "!Equals", "!Select", "!Join"):
        loader.add_constructor(tag, lambda l, n, t=tag: {"__cfn": t, "value": l.construct_scalar(n)})
    for tag in ("!Sub", "!If", "!Not", "!Equals", "!Select", "!Join", "!GetAtt"):
        loader.add_multi_constructor(
            tag,
            lambda l, suffix, n, t=tag: {"__cfn": t, "value": l.construct_sequence(n)},
        )
    # Sequence constructors for tags that take sequences
    for tag in ("!Sub", "!If", "!Not", "!Equals", "!Select", "!Join"):
        try:
            loader.add_constructor(
                tag, lambda l, n, t=tag: {"__cfn": t, "value": l.construct_sequence(n) if n.id == "sequence" else l.construct_scalar(n)}
            )
        except Exception:
            pass

    with open(path) as f:
        return yaml.load(f, Loader=loader)


class TestS3BucketWithVersioning:
    """Criterion 1: S3 Bronze bucket exists with versioning enabled."""

    def test_s3_template_exists(self) -> None:
        assert (INFRA_DIR / "s3-bronze-bucket.yaml").exists()

    def test_versioning_enabled_in_template(self) -> None:
        content = (INFRA_DIR / "s3-bronze-bucket.yaml").read_text()
        assert "VersioningConfiguration:" in content
        assert "Status: Enabled" in content

    def test_encryption_configured(self) -> None:
        content = (INFRA_DIR / "s3-bronze-bucket.yaml").read_text()
        assert "BucketEncryption:" in content
        assert "AES256" in content

    def test_public_access_blocked(self) -> None:
        content = (INFRA_DIR / "s3-bronze-bucket.yaml").read_text()
        assert "BlockPublicAcls: true" in content
        assert "BlockPublicPolicy: true" in content


class TestScheduledIngestion:
    """Criteria 2 & 3: All 6 ingestion jobs have EventBridge schedules."""

    def test_eventbridge_template_exists(self) -> None:
        assert (INFRA_DIR / "eventbridge-schedules.yaml").exists()

    def test_all_six_schedules_defined(self) -> None:
        content = (INFRA_DIR / "eventbridge-schedules.yaml").read_text()
        for name in [
            "PolymarketOrderFilledSchedule",
            "KalshiTradesSchedule",
            "PolymarketMarketsSchedule",
            "KalshiMarketsSchedule",
            "PolymarketEventsSchedule",
            "KalshiEventsSchedule",
        ]:
            assert name in content, f"Missing schedule: {name}"

    def test_schedule_commands_match_cli(self) -> None:
        content = (INFRA_DIR / "eventbridge-schedules.yaml").read_text()
        # Polymarket order_filled uses backfill catchup with concurrency guard
        assert (
            '"backfill", "catchup", "--platform", "polymarket", "--entity", "order_filled", "--skip-if-concurrent"'
            in content
        ), "Missing CLI command: backfill catchup order_filled"
        # Kalshi trades uses backfill catchup with concurrency guard
        assert (
            '"backfill", "catchup", "--platform", "kalshi", "--entity", "trades", "--skip-if-concurrent"'
            in content
        ), "Missing CLI command: backfill catchup kalshi trades"
        # Remaining schedules still use ingest commands
        for cmd in [
            "polymarket-markets",
            "kalshi-markets",
            "polymarket-events",
            "kalshi-events",
        ]:
            assert f'"ingest", "{cmd}"' in content, f"Missing CLI command: ingest {cmd}"

    def test_trades_schedule_rate(self) -> None:
        content = (INFRA_DIR / "eventbridge-schedules.yaml").read_text()
        assert "rate(5 minutes)" in content

    def test_markets_schedule_rate(self) -> None:
        content = (INFRA_DIR / "eventbridge-schedules.yaml").read_text()
        assert "rate(1 hour)" in content


class TestOutputFormat:
    """Criterion 4: Each run writes part-000.jsonl.gz and manifest.json."""

    def test_s3_client_writes_part_000(self) -> None:
        from prediction_data.storage.s3 import S3Client

        # Verify the upload_jsonl method produces part-000 filename
        import inspect
        source = inspect.getsource(S3Client.upload_jsonl)
        assert "part-{part_number:03d}.jsonl.gz" in source

    def test_s3_client_writes_manifest(self) -> None:
        from prediction_data.storage.s3 import S3Client

        import inspect
        source = inspect.getsource(S3Client.upload_manifest)
        assert "manifest.json" in source

    def test_bronze_key_pattern_validates_output_files(self) -> None:
        from prediction_data.storage.s3 import validate_bronze_key

        assert validate_bronze_key("bronze/polymarket/trades/dt=2026-01-28/run_id=abc-123/part-000.jsonl.gz")
        assert validate_bronze_key("bronze/polymarket/trades/dt=2026-01-28/run_id=abc-123/manifest.json")
        assert not validate_bronze_key("silver/polymarket/trades/dt=2026-01-28/run_id=abc-123/part-000.jsonl.gz")


class TestRestartSafety:
    """Criterion 5: Ingestion is restart-safe (unique run_ids, no overwrites)."""

    def test_run_id_uses_uuid4(self) -> None:
        from prediction_data.core.run import RunContext

        ctx1 = RunContext(platform="test", entity="test")
        ctx2 = RunContext(platform="test", entity="test")
        assert ctx1.run_id != ctx2.run_id

    def test_run_id_is_valid_uuid(self) -> None:
        import uuid

        from prediction_data.core.run import RunContext

        ctx = RunContext(platform="test", entity="test")
        # Should not raise
        uuid.UUID(ctx.run_id, version=4)

    def test_s3_key_includes_run_id(self) -> None:
        from prediction_data.storage.s3 import build_s3_key_prefix

        prefix = build_s3_key_prefix("polymarket", "trades", "2026-01-28", "my-run-id")
        assert "run_id=my-run-id/" in prefix

    def test_no_put_if_exists_or_overwrite_logic(self) -> None:
        """Verify S3 client has no conditional overwrite or delete logic."""
        source = (SRC_DIR / "storage" / "s3.py").read_text()
        assert "delete_object" not in source
        assert "overwrite" not in source.lower()


class TestBackfillViaSameTaskDef:
    """Criterion 6: Backfills use same ECS task definition with command overrides."""

    def test_single_task_definition_in_ecs_template(self) -> None:
        content = (INFRA_DIR / "ecs-cluster.yaml").read_text()
        # Should have exactly one TaskDefinition resource
        assert content.count("Type: AWS::ECS::TaskDefinition") == 1

    def test_backfill_uses_command_override(self) -> None:
        content = (INFRA_DIR / "ecs-cluster.yaml").read_text()
        assert "containerOverrides" in content
        assert "--dt" in content


class TestCloudWatchObservability:
    """Criterion 7: CloudWatch logs show successful, observable runs."""

    def test_structured_logging_configured(self) -> None:
        from prediction_data.core.logging import configure_logging

        # Just verify the function exists and is callable
        assert callable(configure_logging)

    def test_json_renderer_for_cloudwatch(self) -> None:
        source = (SRC_DIR / "core" / "logging.py").read_text()
        assert "JSONRenderer" in source

    def test_run_context_logs_start_and_end(self) -> None:
        source = (SRC_DIR / "core" / "run.py").read_text()
        assert "Run started" in source
        assert "Run completed" in source
        assert "duration_seconds" in source

    def test_ecs_task_has_awslogs_driver(self) -> None:
        content = (INFRA_DIR / "ecs-cluster.yaml").read_text()
        assert "awslogs" in content
        assert "/ecs/prediction-data" in content

    def test_cloudwatch_monitoring_template_exists(self) -> None:
        assert (INFRA_DIR / "cloudwatch-monitoring.yaml").exists()


class TestNoSilverGoldAssumptions:
    """Criterion 8: No Silver/Gold assumptions exist in Bronze source code."""

    def test_no_silver_references_in_bronze_source(self) -> None:
        for py_file in (SRC_DIR / "bronze").rglob("*.py"):
            content = py_file.read_text()
            # Allow "silver" only in comments about the medallion architecture
            lines = [
                line
                for line in content.split("\n")
                if not line.strip().startswith("#") and not line.strip().startswith('"""')
            ]
            code_only = "\n".join(lines)
            assert "silver" not in code_only.lower(), f"Found 'silver' reference in {py_file}"

    def test_no_gold_references_in_bronze_source(self) -> None:
        """Bronze layer should not contain gold tier references."""
        for py_file in (SRC_DIR / "bronze").rglob("*.py"):
            content = py_file.read_text()
            lines = [
                line
                for line in content.split("\n")
                if not line.strip().startswith("#") and not line.strip().startswith('"""')
            ]
            code_only = "\n".join(lines)
            # Exclude "goldsky" (vendor name) before checking for "gold" tier references
            filtered = code_only.lower().replace("goldsky", "")
            assert "gold" not in filtered, f"Found 'gold' reference in {py_file}"

    def test_no_transformation_or_aggregation_logic(self) -> None:
        """Bronze layer should only do ingestion, not transformation."""
        for py_file in (SRC_DIR / "bronze").rglob("*.py"):
            content = py_file.read_text().lower()
            assert "aggregate" not in content, f"Found aggregation logic in {py_file}"
            assert "transform" not in content, f"Found transformation logic in {py_file}"


class TestOperationalVerification:
    """Tests for verifying Bronze operational state.

    Note: These tests check local artifacts only. For live AWS verification,
    run: python scripts/verify_bronze_operational.py
    """

    def test_verification_script_exists(self) -> None:
        """Verify the operational verification script exists."""
        script_path = Path(__file__).resolve().parent.parent / "scripts" / "verify_bronze_operational.py"
        assert script_path.exists(), (
            "Missing scripts/verify_bronze_operational.py - "
            "run this script to verify AWS deployment state"
        )

    def test_eventbridge_template_has_all_expected_schedules(self) -> None:
        """Verify template defines all 6 expected Bronze schedules."""
        content = (INFRA_DIR / "eventbridge-schedules.yaml").read_text()
        expected_schedules = [
            "PolymarketOrderFilledSchedule",
            "KalshiTradesSchedule",
            "PolymarketMarketsSchedule",
            "KalshiMarketsSchedule",
            "PolymarketEventsSchedule",
            "KalshiEventsSchedule",
        ]
        for schedule in expected_schedules:
            assert schedule in content, f"Missing schedule definition: {schedule}"

    def test_no_polymarket_trades_schedule_in_template(self) -> None:
        """Verify PolymarketTradesSchedule is NOT in the template (trades only in Silver)."""
        content = (INFRA_DIR / "eventbridge-schedules.yaml").read_text()
        # The template should NOT have a PolymarketTradesSchedule resource
        # (order_filled is used instead, trades are derived in Silver)
        assert "PolymarketTradesSchedule:" not in content, (
            "Template should not define PolymarketTradesSchedule - "
            "Polymarket trades are derived from order_filled in Silver layer"
        )

    def test_order_filled_uses_catchup_command(self) -> None:
        """Verify order_filled schedule uses backfill catchup, not ingest."""
        content = (INFRA_DIR / "eventbridge-schedules.yaml").read_text()
        # Find the PolymarketOrderFilledSchedule section and verify command
        assert '"backfill", "catchup", "--platform", "polymarket", "--entity", "order_filled"' in content

    def test_kalshi_trades_uses_catchup_command(self) -> None:
        """Verify Kalshi trades schedule uses backfill catchup, not ingest."""
        content = (INFRA_DIR / "eventbridge-schedules.yaml").read_text()
        assert '"backfill", "catchup", "--platform", "kalshi", "--entity", "trades"' in content
