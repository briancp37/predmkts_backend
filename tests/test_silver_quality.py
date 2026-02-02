"""Tests for silver.quality – data quality check framework."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from prediction_data.silver.quality import (
    NonNullCheck,
    QualityCheck,
    QualityCheckError,
    QualityCheckResult,
    ReferentialCheck,
    TimestampRangeCheck,
    UniquenessCheck,
    checks_for_entity,
    run_quality_checks,
)


# ---------------------------------------------------------------------------
# Concrete test check implementations
# ---------------------------------------------------------------------------

class AlwaysPassCheck(QualityCheck):
    @property
    def name(self) -> str:
        return "always_pass"

    def run(self, records: list[dict[str, Any]]) -> QualityCheckResult:
        return QualityCheckResult(check_name=self.name, passed=True)


class AlwaysFailCheck(QualityCheck):
    @property
    def name(self) -> str:
        return "always_fail"

    def run(self, records: list[dict[str, Any]]) -> QualityCheckResult:
        return QualityCheckResult(
            check_name=self.name,
            passed=False,
            failed_count=len(records),
            error_message="everything failed",
            sample_failures=[{"row": 0}],
        )


class CountingCheck(QualityCheck):
    """Track how many times run() is called."""

    def __init__(self) -> None:
        self.call_count = 0

    @property
    def name(self) -> str:
        return "counting"

    def run(self, records: list[dict[str, Any]]) -> QualityCheckResult:
        self.call_count += 1
        return QualityCheckResult(check_name=self.name, passed=True)


# ---------------------------------------------------------------------------
# QualityCheckResult
# ---------------------------------------------------------------------------

class TestQualityCheckResult:
    def test_defaults(self) -> None:
        r = QualityCheckResult(check_name="test", passed=True)
        assert r.failed_count == 0
        assert r.error_message is None
        assert r.sample_failures == []

    def test_with_failures(self) -> None:
        r = QualityCheckResult(
            check_name="test",
            passed=False,
            failed_count=3,
            error_message="bad data",
            sample_failures=[{"col": "x"}],
        )
        assert r.failed_count == 3
        assert r.error_message == "bad data"
        assert len(r.sample_failures) == 1


# ---------------------------------------------------------------------------
# run_quality_checks
# ---------------------------------------------------------------------------

class TestRunQualityChecks:
    def test_all_pass(self) -> None:
        results = run_quality_checks(
            [AlwaysPassCheck(), AlwaysPassCheck()],
            [{"a": 1}],
        )
        assert len(results) == 2
        assert all(r.passed for r in results)

    def test_fail_fast_raises(self) -> None:
        with pytest.raises(QualityCheckError, match="always_fail"):
            run_quality_checks(
                [AlwaysFailCheck()],
                [{"a": 1}],
            )

    def test_fail_fast_stops_subsequent_checks(self) -> None:
        counter = CountingCheck()
        with pytest.raises(QualityCheckError):
            run_quality_checks(
                [AlwaysFailCheck(), counter],
                [{"a": 1}],
            )
        assert counter.call_count == 0

    def test_pass_then_fail(self) -> None:
        """First check passes, second fails — only first result returned."""
        with pytest.raises(QualityCheckError):
            run_quality_checks(
                [AlwaysPassCheck(), AlwaysFailCheck()],
                [{"a": 1}],
            )

    def test_empty_checks_list(self) -> None:
        results = run_quality_checks([], [{"a": 1}])
        assert results == []

    def test_empty_records(self) -> None:
        results = run_quality_checks([AlwaysPassCheck()], [])
        assert len(results) == 1
        assert results[0].passed


# ---------------------------------------------------------------------------
# NonNullCheck
# ---------------------------------------------------------------------------

class TestNonNullCheck:
    def test_all_present(self) -> None:
        check = NonNullCheck(["a", "b"])
        result = check.run([{"a": 1, "b": 2}, {"a": 3, "b": 4}])
        assert result.passed
        assert result.failed_count == 0

    def test_null_detected(self) -> None:
        check = NonNullCheck(["a", "b"])
        result = check.run([{"a": 1, "b": None}, {"a": None, "b": 2}])
        assert not result.passed
        assert result.failed_count == 2

    def test_missing_key_treated_as_null(self) -> None:
        check = NonNullCheck(["a", "b"])
        result = check.run([{"a": 1}])
        assert not result.passed
        assert result.sample_failures[0]["null_columns"] == ["b"]

    def test_empty_records(self) -> None:
        check = NonNullCheck(["a"])
        result = check.run([])
        assert result.passed


# ---------------------------------------------------------------------------
# UniquenessCheck
# ---------------------------------------------------------------------------

class TestUniquenessCheck:
    def test_all_unique(self) -> None:
        check = UniquenessCheck("id")
        result = check.run([{"id": "a"}, {"id": "b"}, {"id": "c"}])
        assert result.passed

    def test_duplicates_detected(self) -> None:
        check = UniquenessCheck("id")
        result = check.run([{"id": "a"}, {"id": "b"}, {"id": "a"}])
        assert not result.passed
        assert result.failed_count == 1
        assert result.sample_failures[0]["key"] == "a"

    def test_null_keys_skipped(self) -> None:
        check = UniquenessCheck("id")
        result = check.run([{"id": None}, {"id": None}])
        assert result.passed

    def test_empty_records(self) -> None:
        check = UniquenessCheck("id")
        result = check.run([])
        assert result.passed


# ---------------------------------------------------------------------------
# TimestampRangeCheck
# ---------------------------------------------------------------------------

class TestTimestampRangeCheck:
    def test_within_range(self) -> None:
        expected = datetime(2025, 6, 15, tzinfo=UTC)
        check = TimestampRangeCheck(expected, tolerance_days=1)
        records = [
            {"event_ts": datetime(2025, 6, 15, 12, 0, tzinfo=UTC)},
            {"event_ts": datetime(2025, 6, 14, 1, 0, tzinfo=UTC)},
        ]
        result = check.run(records)
        assert result.passed

    def test_out_of_range(self) -> None:
        expected = datetime(2025, 6, 15, tzinfo=UTC)
        check = TimestampRangeCheck(expected, tolerance_days=1)
        records = [
            {"event_ts": datetime(2025, 6, 15, 12, 0, tzinfo=UTC)},
            {"event_ts": datetime(2025, 1, 1, tzinfo=UTC)},
        ]
        result = check.run(records)
        assert not result.passed
        assert result.failed_count == 1

    def test_future_timestamp(self) -> None:
        now = datetime.now(UTC)
        expected = now.replace(hour=0, minute=0, second=0, microsecond=0)
        check = TimestampRangeCheck(expected, tolerance_days=1)
        future = now + timedelta(hours=2)
        records = [{"event_ts": future}]
        result = check.run(records)
        assert not result.passed
        assert "future" in result.sample_failures[0]["reason"]

    def test_none_timestamps_skipped(self) -> None:
        expected = datetime(2025, 6, 15, tzinfo=UTC)
        check = TimestampRangeCheck(expected)
        result = check.run([{"event_ts": None}])
        assert result.passed


# ---------------------------------------------------------------------------
# ReferentialCheck
# ---------------------------------------------------------------------------

class TestReferentialCheck:
    def test_all_found(self) -> None:
        check = ReferentialCheck("market_id", {"m1", "m2"})
        result = check.run([{"market_id": "m1"}, {"market_id": "m2"}])
        assert result.passed
        assert result.failed_count == 0

    def test_orphan_warn_only(self) -> None:
        check = ReferentialCheck("market_id", {"m1"}, warn_only=True)
        result = check.run([{"market_id": "m1"}, {"market_id": "m999"}])
        assert result.passed  # warn-only still passes
        assert result.failed_count == 1

    def test_orphan_hard_fail(self) -> None:
        check = ReferentialCheck("market_id", {"m1"}, warn_only=False)
        result = check.run([{"market_id": "m999"}])
        assert not result.passed
        assert result.failed_count == 1

    def test_null_values_skipped(self) -> None:
        check = ReferentialCheck("market_id", {"m1"}, warn_only=False)
        result = check.run([{"market_id": None}])
        assert result.passed


# ---------------------------------------------------------------------------
# checks_for_entity
# ---------------------------------------------------------------------------

class TestChecksForEntity:
    def test_polymarket_trades_basic(self) -> None:
        checks = checks_for_entity("polymarket", "trades")
        names = [c.name for c in checks]
        assert "non_null" in names
        assert "uniqueness" in names

    def test_with_expected_date(self) -> None:
        checks = checks_for_entity(
            "polymarket", "trades",
            expected_date=datetime(2025, 6, 15, tzinfo=UTC),
        )
        names = [c.name for c in checks]
        assert "timestamp_range" in names

    def test_with_market_ids(self) -> None:
        checks = checks_for_entity(
            "polymarket", "trades",
            market_ids={"m1", "m2"},
        )
        names = [c.name for c in checks]
        assert "referential" in names

    def test_markets_no_referential(self) -> None:
        checks = checks_for_entity(
            "polymarket", "markets",
            market_ids={"m1"},
        )
        names = [c.name for c in checks]
        assert "referential" not in names


# ---------------------------------------------------------------------------
# Fixture-based tests for common quality violations
# ---------------------------------------------------------------------------


class TestNullViolationFixture:
    def test_non_null_check_catches_nulls(self, null_violation_records: list[dict]) -> None:
        check = NonNullCheck(["event_ts", "platform_trade_id", "platform_market_id"])
        result = check.run(null_violation_records)
        assert not result.passed
        # rows 1 (null event_ts), 2 (null trade_id), 3 (missing market_id)
        assert result.failed_count == 3

    def test_non_null_sample_failures_contain_details(self, null_violation_records: list[dict]) -> None:
        check = NonNullCheck(["event_ts", "platform_trade_id"])
        result = check.run(null_violation_records)
        assert not result.passed
        for sample in result.sample_failures:
            assert "row" in sample
            assert "null_columns" in sample


class TestDuplicateViolationFixture:
    def test_uniqueness_check_catches_duplicates(self, duplicate_violation_records: list[dict]) -> None:
        check = UniquenessCheck("platform_trade_id")
        result = check.run(duplicate_violation_records)
        assert not result.passed
        assert result.failed_count == 2  # t1 and t2 each duplicated once


class TestBadTimestampFixture:
    def test_timestamp_range_catches_violations(self, bad_timestamp_records: list[dict]) -> None:
        expected = datetime(2025, 6, 15, tzinfo=UTC)
        check = TimestampRangeCheck(expected, tolerance_days=1)
        result = check.run(bad_timestamp_records)
        assert not result.passed
        # out-of-range, future, and just-outside-tolerance
        assert result.failed_count >= 2


class TestRunQualityChecksWithViolations:
    def test_fail_fast_on_null_violations(self, null_violation_records: list[dict]) -> None:
        checks = [
            NonNullCheck(["event_ts", "platform_trade_id", "platform_market_id"]),
            UniquenessCheck("platform_trade_id"),
        ]
        with pytest.raises(QualityCheckError, match="non_null"):
            run_quality_checks(checks, null_violation_records)
