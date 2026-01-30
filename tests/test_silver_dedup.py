"""Tests for silver.dedup – in-batch deduplication engine."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from unittest.mock import MagicMock

import pytest

from prediction_data.silver.dedup import DedupStats, dedup_batch


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_normalizer(
    platform: str = "polymarket",
    entity: str = "markets",
    key_field: str = "id",
) -> MagicMock:
    """Return a mock Normalizer whose dedup_key returns record[key_field]."""
    norm = MagicMock()
    norm.platform = platform
    norm.entity = entity
    norm.dedup_key.side_effect = lambda rec: rec.get(key_field, "")
    return norm


# ---------------------------------------------------------------------------
# DedupStats
# ---------------------------------------------------------------------------

class TestDedupStats:
    def test_records_out(self) -> None:
        s = DedupStats(records_in=10, duplicates_dropped=3)
        assert s.records_out == 7

    def test_zero_dupes(self) -> None:
        s = DedupStats(records_in=5, duplicates_dropped=0)
        assert s.records_out == 5


# ---------------------------------------------------------------------------
# dedup_batch
# ---------------------------------------------------------------------------

class TestDedupBatch:
    def test_no_duplicates(self) -> None:
        records = [{"id": "a"}, {"id": "b"}, {"id": "c"}]
        result, stats = dedup_batch(records, _make_normalizer())
        assert len(result) == 3
        assert stats.records_in == 3
        assert stats.duplicates_dropped == 0

    def test_empty_batch(self) -> None:
        result, stats = dedup_batch([], _make_normalizer())
        assert result == []
        assert stats.records_in == 0
        assert stats.records_out == 0

    def test_exact_duplicates_keeps_first(self) -> None:
        """When no timestamps are available, first occurrence wins."""
        records = [
            {"id": "a", "value": "first"},
            {"id": "a", "value": "second"},
        ]
        result, stats = dedup_batch(records, _make_normalizer())
        assert len(result) == 1
        assert result[0]["value"] == "first"
        assert stats.duplicates_dropped == 1

    def test_latest_wins_by_updated_at(self) -> None:
        records = [
            {"id": "m1", "updated_at": datetime(2024, 1, 1, tzinfo=UTC)},
            {"id": "m1", "updated_at": datetime(2024, 6, 1, tzinfo=UTC)},
        ]
        result, stats = dedup_batch(records, _make_normalizer())
        assert len(result) == 1
        assert result[0]["updated_at"] == datetime(2024, 6, 1, tzinfo=UTC)
        assert stats.duplicates_dropped == 1

    def test_latest_wins_by_event_ts(self) -> None:
        records = [
            {"id": "t1", "event_ts": datetime(2024, 6, 15, 12, 0, tzinfo=UTC)},
            {"id": "t1", "event_ts": datetime(2024, 6, 15, 18, 0, tzinfo=UTC)},
        ]
        result, stats = dedup_batch(records, _make_normalizer())
        assert len(result) == 1
        assert result[0]["event_ts"].hour == 18

    def test_updated_at_preferred_over_event_ts(self) -> None:
        """updated_at takes priority when both fields exist."""
        records = [
            {
                "id": "x",
                "updated_at": datetime(2024, 1, 1, tzinfo=UTC),
                "event_ts": datetime(2025, 1, 1, tzinfo=UTC),
            },
            {
                "id": "x",
                "updated_at": datetime(2024, 6, 1, tzinfo=UTC),
                "event_ts": datetime(2023, 1, 1, tzinfo=UTC),
            },
        ]
        result, stats = dedup_batch(records, _make_normalizer())
        assert len(result) == 1
        # Second record wins because updated_at is later
        assert result[0]["updated_at"] == datetime(2024, 6, 1, tzinfo=UTC)

    def test_multiple_duplicates_across_keys(self) -> None:
        records = [
            {"id": "a", "updated_at": datetime(2024, 1, 1, tzinfo=UTC)},
            {"id": "b"},
            {"id": "a", "updated_at": datetime(2024, 6, 1, tzinfo=UTC)},
            {"id": "c"},
            {"id": "b"},
        ]
        result, stats = dedup_batch(records, _make_normalizer())
        assert len(result) == 3
        assert stats.duplicates_dropped == 2
        # Preserved original order of kept records
        assert [r["id"] for r in result] == ["b", "a", "c"]

    def test_preserves_order(self) -> None:
        """Surviving records retain their original order."""
        records = [
            {"id": "c"},
            {"id": "a"},
            {"id": "b"},
        ]
        result, _ = dedup_batch(records, _make_normalizer())
        assert [r["id"] for r in result] == ["c", "a", "b"]

    def test_three_way_duplicate(self) -> None:
        """Three records with the same key — latest timestamp wins."""
        records = [
            {"id": "m", "updated_at": datetime(2024, 3, 1, tzinfo=UTC)},
            {"id": "m", "updated_at": datetime(2024, 1, 1, tzinfo=UTC)},
            {"id": "m", "updated_at": datetime(2024, 6, 1, tzinfo=UTC)},
        ]
        result, stats = dedup_batch(records, _make_normalizer())
        assert len(result) == 1
        assert result[0]["updated_at"] == datetime(2024, 6, 1, tzinfo=UTC)
        assert stats.duplicates_dropped == 2

    def test_mixed_timestamps_none_vs_present(self) -> None:
        """When one record has a timestamp and the other doesn't, first seen wins."""
        records = [
            {"id": "x"},
            {"id": "x", "updated_at": datetime(2024, 6, 1, tzinfo=UTC)},
        ]
        result, stats = dedup_batch(records, _make_normalizer())
        assert len(result) == 1
        # First wins because comparison requires both timestamps
        assert "updated_at" not in result[0]
