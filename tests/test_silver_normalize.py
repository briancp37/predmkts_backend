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


# ---------------------------------------------------------------------------
# Null handling and default values
# ---------------------------------------------------------------------------

class TestNullHandling:
    """Test null/missing field handling across all normalizers."""

    def test_polymarket_markets_all_optional_null(self) -> None:
        """Markets normalizer should set optional fields to None when missing."""
        norm = PolymarketMarketsNormalizer()
        rec = {"id": "m1", "updated_at": "2024-06-01T00:00:00Z"}
        result = norm.normalize(rec)
        assert result["question"] is None
        assert result["description"] is None
        assert result["market_slug"] is None
        assert result["status"] is None
        assert result["outcome"] is None
        assert result["tokens"] is None
        assert result["event_id"] is None
        assert result["bronze_run_id"] is None
        assert result["silver_ingestion_ts"] is None

    def test_polymarket_events_all_optional_null(self) -> None:
        norm = PolymarketEventsNormalizer()
        rec = {"id": "e1", "updated_at": "2024-06-01T00:00:00Z"}
        result = norm.normalize(rec)
        assert result["title"] is None
        assert result["description"] is None
        assert result["slug"] is None
        assert result["status"] is None
        assert result["category"] is None
        assert result["bronze_run_id"] is None

    def test_kalshi_trades_all_optional_null(self) -> None:
        norm = KalshiTradesNormalizer()
        rec = {"trade_id": "t1", "created_time": "2024-01-01T00:00:00Z"}
        result = norm.normalize(rec)
        assert result["platform_market_id"] == ""  # empty string default
        assert result["side"] is None
        assert result["yes_price"] is None
        assert result["no_price"] is None
        assert result["count"] is None
        assert result["taker_side"] is None

    def test_kalshi_markets_all_optional_null(self) -> None:
        norm = KalshiMarketsNormalizer()
        rec = {"ticker": "T", "updated_at": "2024-01-01T00:00:00Z"}
        result = norm.normalize(rec)
        assert result["title"] is None
        assert result["subtitle"] is None
        assert result["status"] is None
        assert result["event_ticker"] is None
        assert result["series_ticker"] is None

    def test_kalshi_events_all_optional_null(self) -> None:
        norm = KalshiEventsNormalizer()
        rec = {"ticker": "E", "updated_at": "2024-01-01T00:00:00Z"}
        result = norm.normalize(rec)
        assert result["title"] is None
        assert result["category"] is None
        assert result["status"] is None
        assert result["series_ticker"] is None

    def test_explicit_none_values_handled(self) -> None:
        """Fields explicitly set to None should not crash."""
        norm = PolymarketMarketsNormalizer()
        rec = {
            "id": "m1",
            "updated_at": "2024-06-01T00:00:00Z",
            "question": None,
            "tokens": None,
            "outcome": None,
        }
        result = norm.normalize(rec)
        assert result["question"] is None
        assert result["tokens"] is None
        assert result["outcome"] is None


# ---------------------------------------------------------------------------
# Type conversion edge cases
# ---------------------------------------------------------------------------

class TestTypeConversionEdgeCases:
    """Test edge cases in type coercion helpers."""

    def test_safe_float_malformed_returns_none(self) -> None:
        norm = KalshiTradesNormalizer()
        rec = {
            "trade_id": "t1",
            "ticker": "T",
            "yes_price": "not-a-number",
            "no_price": "",
            "created_time": "2024-01-01T00:00:00Z",
        }
        result = norm.normalize(rec)
        assert result["yes_price"] is None
        assert result["no_price"] is None

    def test_safe_int_malformed_returns_none(self) -> None:
        norm = KalshiTradesNormalizer()
        rec = {
            "trade_id": "t1",
            "ticker": "T",
            "count": "abc",
            "created_time": "2024-01-01T00:00:00Z",
        }
        result = norm.normalize(rec)
        assert result["count"] is None

    def test_timestamp_float_epoch(self) -> None:
        dt = _parse_timestamp_utc(1700000000.5)
        assert dt.year == 2023
        assert dt.tzinfo is not None

    def test_timestamp_float_string(self) -> None:
        dt = _parse_timestamp_utc("1700000000.5")
        assert dt.year == 2023

    def test_timestamp_empty_string_raises(self) -> None:
        with pytest.raises(NormalizationError):
            _parse_timestamp_utc("")

    def test_tokens_dict_serialized(self) -> None:
        """Tokens as a dict (not list) should still serialize to JSON."""
        norm = PolymarketMarketsNormalizer()
        rec = {
            "id": "m1",
            "updated_at": "2024-06-01T00:00:00Z",
            "tokens": {"token_id": "t1"},
        }
        result = norm.normalize(rec)
        assert '"token_id"' in result["tokens"]

    def test_tokens_already_string_passthrough(self) -> None:
        """Tokens as an already-serialized string should pass through."""
        norm = PolymarketMarketsNormalizer()
        rec = {
            "id": "m1",
            "updated_at": "2024-06-01T00:00:00Z",
            "tokens": '[{"token_id": "t1"}]',
        }
        result = norm.normalize(rec)
        assert result["tokens"] == '[{"token_id": "t1"}]'

    def test_polymarket_markets_fallback_timestamp(self) -> None:
        """Markets can fall back to end_date_iso when updated_at is missing."""
        norm = PolymarketMarketsNormalizer()
        rec = {"id": "m1", "end_date_iso": "2024-12-31T23:59:59Z"}
        result = norm.normalize(rec)
        assert result["event_ts"].year == 2024

    def test_polymarket_events_fallback_timestamp(self) -> None:
        """Events can fall back to end_date_iso when updated_at is missing."""
        norm = PolymarketEventsNormalizer()
        rec = {"id": "e1", "end_date_iso": "2024-12-31T23:59:59Z"}
        result = norm.normalize(rec)
        assert result["event_ts"].year == 2024
        assert result["updated_at"] is None

    def test_polymarket_markets_condition_id_fallback(self) -> None:
        """Markets can use condition_id when id is missing."""
        norm = PolymarketMarketsNormalizer()
        rec = {"condition_id": "0xcond1", "updated_at": "2024-06-01T00:00:00Z"}
        result = norm.normalize(rec)
        assert result["platform_market_id"] == "0xcond1"


# ---------------------------------------------------------------------------
# Test fixtures from realistic Bronze data samples
# ---------------------------------------------------------------------------

class TestBronzeDataFixtures:
    """Tests using realistic Bronze JSON records matching actual API shapes."""

    POLYMARKET_MARKET_FIXTURE: dict = {
        "id": "0x1234567890abcdef",
        "question": "Will Bitcoin reach $100k by end of 2024?",
        "description": "Resolves YES if BTC/USD hits $100,000 on any major exchange.",
        "market_slug": "will-bitcoin-reach-100k-2024",
        "status": "open",
        "outcome": "",
        "tokens": [
            {"token_id": "71321045", "outcome": "Yes"},
            {"token_id": "71321046", "outcome": "No"},
        ],
        "event_id": "0xevent_btc_100k",
        "updated_at": "2024-06-15T18:30:45Z",
        "end_date_iso": "2024-12-31T23:59:59Z",
        "active": True,
        "condition_id": "0xcondition_btc",
        "slug": "bitcoin-100k",
    }

    POLYMARKET_EVENT_FIXTURE: dict = {
        "id": "0xevent_us_election",
        "title": "2024 US Presidential Election",
        "description": "Markets related to the 2024 presidential race.",
        "slug": "2024-us-presidential-election",
        "status": "active",
        "category": "Politics",
        "updated_at": "2024-07-20T14:00:00Z",
        "end_date_iso": "2024-11-06T00:00:00Z",
    }

    KALSHI_TRADE_FIXTURE: dict = {
        "trade_id": "abc12345-6789-0def-ghij-klmnopqrstuv",
        "ticker": "KXBTC-24DEC31-T100000",
        "count": 5,
        "yes_price": 42,
        "no_price": 58,
        "taker_side": "yes",
        "side": "buy",
        "created_time": "2024-06-15T12:34:56Z",
    }

    KALSHI_MARKET_FIXTURE: dict = {
        "ticker": "KXBTC-24DEC31-T100000",
        "title": "Bitcoin above $100,000?",
        "subtitle": "Dec 31, 2024",
        "status": "open",
        "event_ticker": "KXBTC-24DEC31",
        "series_ticker": "KXBTC",
        "updated_at": "2024-06-15T09:00:00Z",
    }

    KALSHI_EVENT_FIXTURE: dict = {
        "ticker": "KXBTC-24DEC31",
        "title": "Bitcoin End of Year 2024",
        "category": "Crypto",
        "status": "open",
        "series_ticker": "KXBTC",
        "updated_at": "2024-06-15T09:00:00Z",
    }

    def test_polymarket_market_fixture(self) -> None:
        norm = PolymarketMarketsNormalizer()
        result = norm.normalize(self.POLYMARKET_MARKET_FIXTURE, bronze_run_id="run-abc")
        assert result["platform_market_id"] == "0x1234567890abcdef"
        assert result["question"] == "Will Bitcoin reach $100k by end of 2024?"
        assert result["event_id"] == "0xevent_btc_100k"
        assert result["bronze_run_id"] == "run-abc"
        assert result["event_ts"].year == 2024
        assert result["updated_at"].month == 6
        assert '"token_id"' in result["tokens"]

    def test_polymarket_event_fixture(self) -> None:
        norm = PolymarketEventsNormalizer()
        result = norm.normalize(self.POLYMARKET_EVENT_FIXTURE)
        assert result["platform_event_id"] == "0xevent_us_election"
        assert result["title"] == "2024 US Presidential Election"
        assert result["category"] == "Politics"
        assert result["slug"] == "2024-us-presidential-election"

    def test_kalshi_trade_fixture(self) -> None:
        norm = KalshiTradesNormalizer()
        result = norm.normalize(self.KALSHI_TRADE_FIXTURE)
        assert result["platform_trade_id"] == "abc12345-6789-0def-ghij-klmnopqrstuv"
        assert result["platform_market_id"] == "KXBTC-24DEC31-T100000"
        assert result["yes_price"] == 42.0
        assert result["count"] == 5
        assert result["taker_side"] == "yes"

    def test_kalshi_market_fixture(self) -> None:
        norm = KalshiMarketsNormalizer()
        result = norm.normalize(self.KALSHI_MARKET_FIXTURE)
        assert result["platform_market_id"] == "KXBTC-24DEC31-T100000"
        assert result["event_ticker"] == "KXBTC-24DEC31"
        assert result["series_ticker"] == "KXBTC"

    def test_kalshi_event_fixture(self) -> None:
        norm = KalshiEventsNormalizer()
        result = norm.normalize(self.KALSHI_EVENT_FIXTURE)
        assert result["platform_event_id"] == "KXBTC-24DEC31"
        assert result["category"] == "Crypto"

    def test_dedup_keys_from_fixtures(self) -> None:
        """Verify dedup keys have expected format from realistic data."""
        pm_norm = PolymarketMarketsNormalizer()
        key = pm_norm.dedup_key(self.POLYMARKET_MARKET_FIXTURE)
        assert key == "polymarket:0x1234567890abcdef:2024-06-15T18:30:45Z"

        pe_norm = PolymarketEventsNormalizer()
        key = pe_norm.dedup_key(self.POLYMARKET_EVENT_FIXTURE)
        assert key == "polymarket:0xevent_us_election:2024-07-20T14:00:00Z"

        kt_norm = KalshiTradesNormalizer()
        key = kt_norm.dedup_key(self.KALSHI_TRADE_FIXTURE)
        assert key == "kalshi:abc12345-6789-0def-ghij-klmnopqrstuv"

    def test_batch_with_fixture_and_bad_record(self) -> None:
        """Batch normalization should succeed for fixture and skip bad records."""
        norm = PolymarketMarketsNormalizer()
        records = [
            self.POLYMARKET_MARKET_FIXTURE,
            {"garbage": True},
            {"id": "m2", "updated_at": "2024-01-01T00:00:00Z"},
        ]
        results = norm.normalize_batch(records, bronze_run_id="batch-1")
        assert len(results) == 2
        assert results[0]["platform_market_id"] == "0x1234567890abcdef"
        assert results[1]["platform_market_id"] == "m2"
