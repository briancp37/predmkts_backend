"""In-batch deduplication engine for Silver processing.

Deduplicates Bronze records using entity-specific dedup keys from the
normalizer.  Conflict resolution: when two records share the same dedup key,
the one with the latest timestamp wins (``updated_at`` for catalog entities,
``event_ts`` for trades).
"""

from __future__ import annotations

import dataclasses
from datetime import datetime
from typing import Any

from prediction_data.core.logging import get_logger
from prediction_data.silver.normalize import Normalizer

logger = get_logger(__name__)


@dataclasses.dataclass(slots=True)
class DedupStats:
    """Statistics from a dedup pass."""

    records_in: int = 0
    duplicates_dropped: int = 0

    @property
    def records_out(self) -> int:
        return self.records_in - self.duplicates_dropped


def _resolve_ts(record: dict[str, Any]) -> datetime | None:
    """Extract the best available timestamp for conflict resolution.

    Prefers ``updated_at`` (catalog entities), falls back to ``event_ts``.
    Returns ``None`` when neither is present.
    """
    for field in ("updated_at", "event_ts"):
        val = record.get(field)
        if isinstance(val, datetime):
            return val
    return None


def dedup_batch(
    records: list[dict[str, Any]],
    normalizer: Normalizer,
) -> tuple[list[dict[str, Any]], DedupStats]:
    """Deduplicate a batch of *raw Bronze* records in memory.

    Args:
        records: Raw Bronze dicts (pre-normalization).
        normalizer: Normalizer whose ``dedup_key`` method defines uniqueness.

    Returns:
        A tuple of (deduplicated records, stats).
    """
    stats = DedupStats(records_in=len(records))
    # Maps dedup_key → (index into *records*, resolved timestamp)
    seen: dict[str, tuple[int, datetime | None]] = {}

    for idx, rec in enumerate(records):
        key = normalizer.dedup_key(rec)
        ts = _resolve_ts(rec)

        if key not in seen:
            seen[key] = (idx, ts)
            continue

        # Duplicate detected
        prev_idx, prev_ts = seen[key]
        stats.duplicates_dropped += 1

        # Latest wins when both timestamps are available
        if ts is not None and prev_ts is not None and ts > prev_ts:
            seen[key] = (idx, ts)
            logger.debug(
                "dedup_replace key=%s old_idx=%d new_idx=%d",
                key,
                prev_idx,
                idx,
            )
        else:
            logger.debug(
                "dedup_drop key=%s kept_idx=%d dropped_idx=%d",
                key,
                prev_idx,
                idx,
            )

    # Preserve original ordering for determinism
    kept_indices = sorted(i for i, _ in seen.values())
    result = [records[i] for i in kept_indices]

    if stats.duplicates_dropped:
        logger.info(
            "dedup platform=%s entity=%s in=%d dropped=%d out=%d",
            normalizer.platform,
            normalizer.entity,
            stats.records_in,
            stats.duplicates_dropped,
            stats.records_out,
        )

    return result, stats
