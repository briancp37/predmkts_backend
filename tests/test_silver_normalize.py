"""Tests for Silver normalizers."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from prediction_data.silver.normalize import (
    KalshiEventsNormalizer,
    KalshiMarketsNormalizer,
    KalshiTradesNormalizer,
    NormalizationError,
    PolymarketEventsNormalizer,
    PolymarketMarketsNormalizer,
    _parse_timestamp_utc,
    get_normalizer,
)

# ---------------------------------------------------------------------------
# Timestamp parsing
# ---------------------------------------------------------------------------

class TestParseTimestampUtc:
    def test_unix_int(self) -> None:
        dt = _parse_timestamp_utc(1700000000)
        assert dt == datetime(2023, 11, 14, 22, 13, 20, tzinfo=UTC)

    def test_unix_string(self) -> None:
        dt = _parse_timestamp_utc("1700000000")
        assert dt == datetime(2023, 11, 14, 22, 13, 20, tzinfo=UTC)

    def test_iso_with_z(self) -> None:
        dt = _parse_timestamp_utc("2024-01-15T12:00:00Z")
        assert dt.year == 2024
        assert dt.tzinfo is not None

    def test_iso_with_offset(self) -> None:
        dt = _parse_timestamp_utc("2024-01-15T12:00:00+00:00")
        assert dt.tzinfo is not None

    def test_iso_naive(self) -> None:
        dt = _parse_timestamp_utc("2024-01-15T12:00:00")
        assert dt.tzinfo == UTC

    def test_none_raises(self) -> None:
        with pytest.raises(NormalizationError):
            _parse_timestamp_utc(None)

    def test_garbage_raises(self) -> None:
        with pytest.raises(NormalizationError):
            _parse_timestamp_utc("not-a-timestamp")


# ---------------------------------------------------------------------------
# Polymarket Markets
# ---------------------------------------------------------------------------

class TestPolymarketMarketsNormalizer:
    def setup_method(self) -> None:
        self.norm = PolymarketMarketsNormalizer()

    def test_basic(self) -> None:
        rec = {
            "id": "0xmarket1",
            "question": "Will X happen?",
            "description": "Details",
            "market_slug": "will-x-happen",
            "status": "open",
            "outcome": "YES",
            "tokens": [{"token_id": "t1", "outcome": "YES"}],
            "event_id": "0xevent1",
            "updated_at": "2024-06-15T10:00:00Z",
        }
        result = self.norm.normalize(rec, bronze_run_id="run-1")
        assert result["platform_market_id"] == "0xmarket1"
        assert result["question"] == "Will X happen?"
        assert result["bronze_run_id"] == "run-1"
        assert result["event_ts"].tzinfo is not None
        # tokens serialized to JSON string
        assert '"token_id"' in result["tokens"]

    def test_missing_id_raises(self) -> None:
        with pytest.raises(NormalizationError):
            self.norm.normalize({"updated_at": "2024-01-01T00:00:00Z"})

    def test_missing_timestamp_raises(self) -> None:
        with pytest.raises(NormalizationError):
            self.norm.normalize({"id": "m1"})

    def test_dedup_key(self) -> None:
        key = self.norm.dedup_key({"id": "m1", "updated_at": "2024-01-01"})
        assert key == "polymarket:m1:2024-01-01"

    def test_null_optional_fields(self) -> None:
        rec = {"id": "m1", "updated_at": "2024-01-01T00:00:00Z"}
        result = self.norm.normalize(rec)
        assert result["question"] is None
        assert result["tokens"] is None


# ---------------------------------------------------------------------------
# Polymarket Events
# ---------------------------------------------------------------------------

class TestPolymarketEventsNormalizer:
    def setup_method(self) -> None:
        self.norm = PolymarketEventsNormalizer()

    def test_basic(self) -> None:
        rec = {
            "id": "0xevent1",
            "title": "2024 Election",
            "description": "Details",
            "slug": "2024-election",
            "status": "open",
            "category": "Politics",
            "updated_at": "2024-06-15T10:00:00Z",
        }
        result = self.norm.normalize(rec)
        assert result["platform_event_id"] == "0xevent1"
        assert result["title"] == "2024 Election"
        assert result["category"] == "Politics"

    def test_missing_id_raises(self) -> None:
        with pytest.raises(NormalizationError):
            self.norm.normalize({"updated_at": "2024-01-01T00:00:00Z"})


# ---------------------------------------------------------------------------
# Kalshi Trades
# ---------------------------------------------------------------------------

class TestKalshiTradesNormalizer:
    def setup_method(self) -> None:
        self.norm = KalshiTradesNormalizer()

    def test_basic(self) -> None:
        rec = {
            "trade_id": "trade-001",
            "ticker": "PRES-2024-R-DEM",
            "count": 10,
            "yes_price": 55,
            "no_price": 45,
            "taker_side": "yes",
            "created_time": "2024-01-15T12:00:00Z",
        }
        result = self.norm.normalize(rec)
        assert result["platform_trade_id"] == "trade-001"
        assert result["platform_market_id"] == "PRES-2024-R-DEM"
        assert result["yes_price"] == 55.0
        assert result["count"] == 10

    def test_missing_trade_id_raises(self) -> None:
        with pytest.raises(NormalizationError):
            self.norm.normalize({"created_time": "2024-01-01T00:00:00Z"})


# ---------------------------------------------------------------------------
# Kalshi Markets
# ---------------------------------------------------------------------------

class TestKalshiMarketsNormalizer:
    def setup_method(self) -> None:
        self.norm = KalshiMarketsNormalizer()

    def test_basic(self) -> None:
        rec = {
            "ticker": "PRES-2024-R-DEM",
            "title": "Will Democrat win?",
            "subtitle": "Presidential",
            "status": "open",
            "event_ticker": "PRES-2024",
            "series_ticker": "PRES",
            "updated_at": "2024-01-15T12:00:00Z",
        }
        result = self.norm.normalize(rec)
        assert result["platform_market_id"] == "PRES-2024-R-DEM"
        assert result["event_ticker"] == "PRES-2024"


# ---------------------------------------------------------------------------
# Kalshi Events
# ---------------------------------------------------------------------------

class TestKalshiEventsNormalizer:
    def setup_method(self) -> None:
        self.norm = KalshiEventsNormalizer()

    def test_basic(self) -> None:
        rec = {
            "ticker": "PRES-2024",
            "title": "2024 Election",
            "category": "Politics",
            "status": "open",
            "series_ticker": "PRES",
            "updated_at": "2024-01-15T12:00:00Z",
        }
        result = self.norm.normalize(rec)
        assert result["platform_event_id"] == "PRES-2024"
        assert result["category"] == "Politics"


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

class TestRegistry:
    def test_get_normalizer(self) -> None:
        n = get_normalizer("polymarket", "markets")
        assert isinstance(n, PolymarketMarketsNormalizer)

    def test_unknown_raises(self) -> None:
        with pytest.raises(ValueError):
            get_normalizer("unknown", "unknown")


# ---------------------------------------------------------------------------
# Batch normalization
# ---------------------------------------------------------------------------

class TestBatchNormalization:
    def test_batch_skips_errors(self) -> None:
        norm = PolymarketMarketsNormalizer()
        records = [
            {"id": "m1", "updated_at": "2024-01-01T00:00:00Z"},
            {"bad": "record"},  # will fail
            {"id": "m2", "updated_at": "2024-01-02T00:00:00Z"},
        ]
        results = norm.normalize_batch(records)
        assert len(results) == 2

    def test_type_conversion_numeric_string(self) -> None:
        norm = KalshiTradesNormalizer()
        rec = {
            "trade_id": "t1",
            "ticker": "T",
            "yes_price": "55.5",
            "no_price": "44.5",
            "count": "10",
            "created_time": "2024-01-01T00:00:00Z",
        }
        result = norm.normalize(rec)
        assert result["yes_price"] == 55.5
        assert result["count"] == 10
