"""Data quality check framework for Silver processing pipeline.

Provides an abstract base class for quality checks, a result dataclass,
a check registry with per-entity configurations, and a sequential runner
with fail-fast semantics.
"""

from __future__ import annotations

import dataclasses
from abc import ABC, abstractmethod
from typing import Any

from prediction_data.core.logging import get_logger

logger = get_logger(__name__)


class QualityCheckError(Exception):
    """Raised when a quality check fails and the pipeline should abort."""


@dataclasses.dataclass(slots=True)
class QualityCheckResult:
    """Result of running a single quality check."""

    check_name: str
    passed: bool
    failed_count: int = 0
    error_message: str | None = None
    sample_failures: list[dict[str, Any]] = dataclasses.field(default_factory=list)


class QualityCheck(ABC):
    """Abstract base class for a data quality check."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Human-readable name for this check."""

    @abstractmethod
    def run(self, records: list[dict[str, Any]]) -> QualityCheckResult:
        """Execute the check against a batch of normalized records.

        Args:
            records: List of normalized Silver-schema dicts.

        Returns:
            A QualityCheckResult indicating pass/fail with details.
        """


def run_quality_checks(
    checks: list[QualityCheck],
    records: list[dict[str, Any]],
) -> list[QualityCheckResult]:
    """Run quality checks sequentially with fail-fast semantics.

    Executes each check in order. On the first failure, raises
    ``QualityCheckError`` — no partial commits should occur.

    Args:
        checks: Ordered list of quality checks to run.
        records: Normalized Silver records to validate.

    Returns:
        List of all QualityCheckResult objects (only if all pass).

    Raises:
        QualityCheckError: On the first check failure.
    """
    results: list[QualityCheckResult] = []

    for check in checks:
        result = check.run(records)
        results.append(result)

        logger.info(
            "quality_check_result",
            check_name=result.check_name,
            passed=result.passed,
            failed_count=result.failed_count,
        )

        if not result.passed:
            logger.error(
                "quality_check_failed",
                check_name=result.check_name,
                failed_count=result.failed_count,
                error_message=result.error_message,
                sample_failures=result.sample_failures[:5],
            )
            raise QualityCheckError(
                f"Quality check '{result.check_name}' failed: "
                f"{result.failed_count} failures. {result.error_message or ''}"
            )

    return results
