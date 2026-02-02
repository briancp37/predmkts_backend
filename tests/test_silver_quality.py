"""Tests for silver.quality – data quality check framework."""

from __future__ import annotations

from typing import Any

import pytest

from prediction_data.silver.quality import (
    QualityCheck,
    QualityCheckError,
    QualityCheckResult,
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
