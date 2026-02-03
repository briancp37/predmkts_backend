"""Data quality check framework for Silver processing pipeline.

Provides an abstract base class for quality checks, a result dataclass,
concrete check implementations (NonNull, Uniqueness, TimestampRange,
Referential), per-entity check configurations, and a sequential runner
with fail-fast semantics.
"""

from __future__ import annotations

import dataclasses
from abc import ABC, abstractmethod
from datetime import UTC, datetime, timedelta
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


# ---------------------------------------------------------------------------
# Concrete checks
# ---------------------------------------------------------------------------


class NonNullCheck(QualityCheck):
    """Check that specified columns are non-null in all records."""

    def __init__(self, columns: list[str]) -> None:
        self._columns = columns

    @property
    def name(self) -> str:
        return "non_null"

    def run(self, records: list[dict[str, Any]]) -> QualityCheckResult:
        failures: list[dict[str, Any]] = []
        for i, rec in enumerate(records):
            missing = [c for c in self._columns if rec.get(c) is None]
            if missing:
                failures.append({"row": i, "null_columns": missing})

        if failures:
            return QualityCheckResult(
                check_name=self.name,
                passed=False,
                failed_count=len(failures),
                error_message=f"Non-null violation in columns: {self._columns}",
                sample_failures=failures[:5],
            )
        return QualityCheckResult(check_name=self.name, passed=True)


class UniquenessCheck(QualityCheck):
    """Check that a dedup key column is unique within the batch."""

    def __init__(self, key_column: str) -> None:
        self._key_column = key_column

    @property
    def name(self) -> str:
        return "uniqueness"

    def run(self, records: list[dict[str, Any]]) -> QualityCheckResult:
        seen: dict[str, int] = {}
        duplicates: list[dict[str, Any]] = []
        for i, rec in enumerate(records):
            key = rec.get(self._key_column)
            if key is None:
                continue
            key_str = str(key)
            if key_str in seen:
                duplicates.append(
                    {"row": i, "key": key_str, "first_seen_row": seen[key_str]}
                )
            else:
                seen[key_str] = i

        if duplicates:
            return QualityCheckResult(
                check_name=self.name,
                passed=False,
                failed_count=len(duplicates),
                error_message=f"Duplicate values in '{self._key_column}'",
                sample_failures=duplicates[:5],
            )
        return QualityCheckResult(check_name=self.name, passed=True)


class TimestampRangeCheck(QualityCheck):
    """Check that event_ts is within expected_date +/- tolerance and not in the future."""

    def __init__(
        self,
        expected_date: datetime,
        tolerance_days: int = 1,
    ) -> None:
        self._expected_date = expected_date.replace(
            hour=0, minute=0, second=0, microsecond=0, tzinfo=UTC
        )
        self._tolerance = timedelta(days=tolerance_days)
        self._now = datetime.now(UTC)

    @property
    def name(self) -> str:
        return "timestamp_range"

    def run(self, records: list[dict[str, Any]]) -> QualityCheckResult:
        lower = self._expected_date - self._tolerance
        upper = self._expected_date + timedelta(days=1) + self._tolerance
        failures: list[dict[str, Any]] = []

        for i, rec in enumerate(records):
            ts = rec.get("event_ts")
            if ts is None:
                continue
            if not isinstance(ts, datetime):
                failures.append({"row": i, "event_ts": str(ts), "reason": "not a datetime"})
                continue
            if ts < lower or ts > upper:
                failures.append({"row": i, "event_ts": str(ts), "reason": "out of range"})
            elif ts > self._now:
                failures.append({"row": i, "event_ts": str(ts), "reason": "future timestamp"})

        if failures:
            return QualityCheckResult(
                check_name=self.name,
                passed=False,
                failed_count=len(failures),
                error_message=(
                    f"Timestamps outside {lower.date()}..{upper.date()} or in the future"
                ),
                sample_failures=failures[:5],
            )
        return QualityCheckResult(check_name=self.name, passed=True)


class ReferentialCheck(QualityCheck):
    """Check that a column's values exist in a reference set.

    Operates in warn-only mode by default: logs warnings but still passes.
    Set ``warn_only=False`` to make violations a hard failure.
    """

    def __init__(
        self,
        column: str,
        reference_values: set[str],
        *,
        warn_only: bool = True,
    ) -> None:
        self._column = column
        self._reference_values = reference_values
        self._warn_only = warn_only

    @property
    def name(self) -> str:
        return "referential"

    def run(self, records: list[dict[str, Any]]) -> QualityCheckResult:
        orphans: list[dict[str, Any]] = []
        for i, rec in enumerate(records):
            val = rec.get(self._column)
            if val is None:
                continue
            if str(val) not in self._reference_values:
                orphans.append({"row": i, self._column: str(val)})

        if orphans and not self._warn_only:
            return QualityCheckResult(
                check_name=self.name,
                passed=False,
                failed_count=len(orphans),
                error_message=f"Referential violation: {len(orphans)} orphan(s) in '{self._column}'",
                sample_failures=orphans[:5],
            )

        if orphans:
            logger.warning(
                "referential_check_orphans",
                column=self._column,
                orphan_count=len(orphans),
                sample=orphans[:5],
            )

        return QualityCheckResult(
            check_name=self.name,
            passed=True,
            failed_count=len(orphans),
            error_message=f"{len(orphans)} orphan(s) (warn-only)" if orphans else None,
        )


# ---------------------------------------------------------------------------
# Per-entity check configurations
# ---------------------------------------------------------------------------

# Catalog entities contain full snapshots with timestamps spanning years
# (e.g. a markets snapshot for dt=2026-02-03 has records from 2023-2026).
# Timestamp range checks are not meaningful for these entities.
CATALOG_ENTITIES: frozenset[str] = frozenset({"markets", "events"})

# Critical non-null columns per entity (platform, entity) -> columns
ENTITY_NON_NULL_COLUMNS: dict[tuple[str, str], list[str]] = {
    ("polymarket", "trades"): [
        "event_ts", "platform_trade_id", "platform_market_id",
        "maker", "taker", "price", "usd_amount", "token_amount",
    ],
    ("polymarket", "markets"): ["event_ts", "platform_market_id"],
    ("polymarket", "events"): ["event_ts", "platform_event_id"],
    ("kalshi", "trades"): ["event_ts", "platform_trade_id", "platform_market_id"],
    ("kalshi", "markets"): ["event_ts", "platform_market_id"],
    ("kalshi", "events"): ["event_ts", "platform_event_id"],
}

# Uniqueness key column per entity
ENTITY_UNIQUENESS_KEY: dict[tuple[str, str], str] = {
    ("polymarket", "trades"): "platform_trade_id",
    ("polymarket", "markets"): "platform_market_id",
    ("polymarket", "events"): "platform_event_id",
    ("kalshi", "trades"): "platform_trade_id",
    ("kalshi", "markets"): "platform_market_id",
    ("kalshi", "events"): "platform_event_id",
}


def checks_for_entity(
    platform: str,
    entity: str,
    *,
    expected_date: datetime | None = None,
    market_ids: set[str] | None = None,
) -> list[QualityCheck]:
    """Build the ordered list of quality checks for a given entity.

    Args:
        platform: Platform identifier.
        entity: Entity name.
        expected_date: If provided, adds a TimestampRangeCheck.
        market_ids: If provided and entity is 'trades', adds a ReferentialCheck.

    Returns:
        List of QualityCheck instances to run in order.
    """
    key = (platform, entity)
    checks: list[QualityCheck] = []

    # 1. Non-null check
    non_null_cols = ENTITY_NON_NULL_COLUMNS.get(key)
    if non_null_cols:
        checks.append(NonNullCheck(non_null_cols))

    # 2. Uniqueness check
    uniq_col = ENTITY_UNIQUENESS_KEY.get(key)
    if uniq_col:
        checks.append(UniquenessCheck(uniq_col))

    # 3. Timestamp range check (skip for catalog entities whose snapshots
    #    naturally contain records with timestamps spanning years)
    if expected_date is not None and entity not in CATALOG_ENTITIES:
        checks.append(TimestampRangeCheck(expected_date))

    # 4. Referential check (trades -> markets, warn-only)
    if entity == "trades" and market_ids is not None:
        checks.append(
            ReferentialCheck("platform_market_id", market_ids, warn_only=True)
        )

    return checks


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
