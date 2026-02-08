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
    PolymarketTradesNormalizer,
    _parse_timestamp_utc,
    get_normalizer,
)
from prediction_data.silver.polymarket.markets_reference import MarketsReferenceLookup

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

    def test_camelcase_gamma_api_record(self) -> None:
        """Gamma API returns camelCase fields; normalizer should accept them."""
        rec = {
            "id": "0xmarket_gamma",
            "question": "Will it rain tomorrow?",
            "description": "Weather market",
            "slug": "will-it-rain",
            "status": "open",
            "outcome": "",
            "updatedAt": "2026-01-20T15:30:00Z",
            "endDateIso": "2026-06-01T00:00:00Z",
            "conditionId": "0xcond_gamma",
            "clobTokenIds": ["tok_yes", "tok_no"],
            "events": [{"id": "evt-gamma-1"}],
        }
        result = self.norm.normalize(rec, bronze_run_id="run-gamma")
        assert result["platform_market_id"] == "0xmarket_gamma"
        assert result["event_ts"].year == 2026
        assert result["updated_at"] is not None
        assert result["tokens"] is not None
        assert "tok_yes" in result["tokens"]
        assert result["event_id"] == "evt-gamma-1"
        assert result["market_slug"] == "will-it-rain"

    def test_camelcase_condition_id_fallback(self) -> None:
        """conditionId (camelCase) used when id is missing."""
        rec = {"conditionId": "0xcamel", "updatedAt": "2026-01-01T00:00:00Z"}
        result = self.norm.normalize(rec)
        assert result["platform_market_id"] == "0xcamel"

    def test_camelcase_endDateIso_fallback(self) -> None:
        """endDateIso used for event_ts when updatedAt is absent."""
        rec = {"id": "m1", "endDateIso": "2026-12-31T23:59:59Z"}
        result = self.norm.normalize(rec)
        assert result["event_ts"].year == 2026
        assert result["updated_at"] is None

    def test_dedup_key_camelcase(self) -> None:
        """dedup_key uses camelCase field lookups for Gamma API records."""
        rec = {"id": "m1", "updatedAt": "2026-01-20T15:30:00Z"}
        key = self.norm.dedup_key(rec)
        assert key == "polymarket:m1:2026-01-20T15:30:00Z"

    def test_dedup_key_conditionId_camelcase(self) -> None:
        """dedup_key falls back to conditionId when id is missing."""
        rec = {"conditionId": "0xcamel", "updatedAt": "2026-02-01T00:00:00Z"}
        key = self.norm.dedup_key(rec)
        assert key == "polymarket:0xcamel:2026-02-01T00:00:00Z"


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

    def test_camelcase_gamma_api_record(self) -> None:
        """Gamma API events with camelCase fields should normalize correctly."""
        rec = {
            "id": "0xevent_gamma",
            "title": "Major Election",
            "description": "Full description",
            "slug": "major-election",
            "status": "active",
            "category": "Politics",
            "updatedAt": "2026-01-20T15:30:00Z",
            "endDateIso": "2026-11-06T00:00:00Z",
        }
        result = self.norm.normalize(rec)
        assert result["platform_event_id"] == "0xevent_gamma"
        assert result["event_ts"].year == 2026
        assert result["updated_at"] is not None
        assert result["title"] == "Major Election"

    def test_camelcase_endDate_fallback(self) -> None:
        """endDate used as final fallback when updatedAt and endDateIso are null."""
        rec = {"id": "e1", "endDate": "2026-06-15T00:00:00Z"}
        result = self.norm.normalize(rec)
        assert result["event_ts"].year == 2026
        assert result["updated_at"] is None

    def test_dedup_key_camelcase(self) -> None:
        """dedup_key uses camelCase updatedAt for Gamma API records."""
        rec = {"id": "e1", "updatedAt": "2026-01-20T15:30:00Z"}
        key = self.norm.dedup_key(rec)
        assert key == "polymarket:e1:2026-01-20T15:30:00Z"

    def test_tags_extracted_from_array(self) -> None:
        """Tags array should be extracted as list of label strings."""
        rec = {
            "id": "e1",
            "updated_at": "2024-06-01T00:00:00Z",
            "tags": [
                {"id": "1", "label": "Sports", "slug": "sports"},
                {"id": "2", "label": "Basketball", "slug": "basketball"},
                {"id": "3", "label": "NBA", "slug": "nba"},
            ],
        }
        result = self.norm.normalize(rec)
        assert result["tags"] == ["Sports", "Basketball", "NBA"]

    def test_tags_empty_array_returns_none(self) -> None:
        """Empty tags array should return None for storage efficiency."""
        rec = {"id": "e1", "updated_at": "2024-06-01T00:00:00Z", "tags": []}
        result = self.norm.normalize(rec)
        assert result["tags"] is None

    def test_tags_missing_returns_none(self) -> None:
        """Missing tags field should return None."""
        rec = {"id": "e1", "updated_at": "2024-06-01T00:00:00Z"}
        result = self.norm.normalize(rec)
        assert result["tags"] is None

    def test_tags_null_returns_none(self) -> None:
        """Null tags field should return None."""
        rec = {"id": "e1", "updated_at": "2024-06-01T00:00:00Z", "tags": None}
        result = self.norm.normalize(rec)
        assert result["tags"] is None

    def test_tags_filters_invalid_entries(self) -> None:
        """Non-dict tag entries and entries without labels should be filtered."""
        rec = {
            "id": "e1",
            "updated_at": "2024-06-01T00:00:00Z",
            "tags": [
                {"id": "1", "label": "Sports", "slug": "sports"},
                {"id": "2"},  # Missing label
                "string_not_dict",  # Not a dict
                {"id": "3", "label": "", "slug": "empty"},  # Empty label
                {"id": "4", "label": None, "slug": "null"},  # Null label
                {"id": "5", "label": "Politics", "slug": "politics"},
            ],
        }
        result = self.norm.normalize(rec)
        assert result["tags"] == ["Sports", "Politics"]

    def test_tags_with_gamma_api_format(self) -> None:
        """Tags from Gamma API format with full metadata should extract labels."""
        rec = {
            "id": "e1",
            "updatedAt": "2024-06-01T00:00:00Z",
            "tags": [
                {
                    "id": "100",
                    "label": "Crypto",
                    "slug": "crypto",
                    "forceShow": True,
                    "publishedAt": "2024-01-01T00:00:00Z",
                    "createdAt": "2024-01-01T00:00:00Z",
                    "updatedAt": "2024-01-02T00:00:00Z",
                },
                {
                    "id": "101",
                    "label": "DeFi",
                    "slug": "defi",
                    "forceShow": False,
                    "requiresTranslation": True,
                },
            ],
        }
        result = self.norm.normalize(rec)
        assert result["tags"] == ["Crypto", "DeFi"]


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
# Polymarket Trades (derived from OrderFilledEvents)
# ---------------------------------------------------------------------------


def _make_lookup() -> MarketsReferenceLookup:
    """Build a small lookup for testing."""
    lookup = MarketsReferenceLookup()
    lookup.load_from_records([
        {
            "id": "market-abc",
            "clobTokenIds": ["111222333", "444555666"],
        },
    ])
    return lookup


def _order_filled_record(
    *,
    maker_asset: str = "0",
    taker_asset: str = "111222333",
    maker_amount: int = 5_000_000,
    taker_amount: int = 10_000_000,
    timestamp: int = 1700000000,
    tx_hash: str = "0xabc123",
) -> dict:
    return {
        "makerAssetId": maker_asset,
        "takerAssetId": taker_asset,
        "makerAmountFilled": maker_amount,
        "takerAmountFilled": taker_amount,
        "timestamp": timestamp,
        "transactionHash": tx_hash,
        "maker": "0xmaker",
        "taker": "0xtaker",
    }


class TestPolymarketTradesNormalizer:
    def setup_method(self) -> None:
        self.lookup = _make_lookup()
        self.norm = PolymarketTradesNormalizer(lookup=self.lookup)

    def test_basic_taker_buys(self) -> None:
        """Taker provides USDC (asset 0) → taker is buying."""
        rec = _order_filled_record(
            maker_asset="111222333",
            taker_asset="0",
            maker_amount=10_000_000,
            taker_amount=5_000_000,
        )
        result = self.norm.normalize(rec, bronze_run_id="run-1")
        assert result["platform_market_id"] == "market-abc"
        assert result["taker_direction"] == "buy"
        assert result["maker_direction"] == "sell"
        assert result["nonusdc_side"] == "token1"
        assert result["price"] == pytest.approx(0.5)
        assert result["usd_amount"] == pytest.approx(5.0)
        assert result["token_amount"] == pytest.approx(10.0)
        assert result["transaction_hash"] == "0xabc123"
        assert result["bronze_run_id"] == "run-1"
        assert result["event_ts"].tzinfo is not None

    def test_basic_taker_sells(self) -> None:
        """Maker provides USDC (asset 0) → taker is selling."""
        rec = _order_filled_record(
            maker_asset="0",
            taker_asset="111222333",
            maker_amount=5_000_000,
            taker_amount=10_000_000,
        )
        result = self.norm.normalize(rec)
        assert result["taker_direction"] == "sell"
        assert result["maker_direction"] == "buy"
        assert result["price"] == pytest.approx(0.5)

    def test_token2_side(self) -> None:
        """Token in second position should resolve to token2."""
        rec = _order_filled_record(
            maker_asset="444555666",
            taker_asset="0",
            maker_amount=10_000_000,
            taker_amount=7_000_000,
        )
        result = self.norm.normalize(rec)
        assert result["nonusdc_side"] == "token2"
        assert result["price"] == pytest.approx(0.7)

    def test_missing_market_lookup_raises(self) -> None:
        rec = _order_filled_record(taker_asset="unknown_token", maker_asset="0")
        with pytest.raises(NormalizationError, match="Market lookup failed"):
            self.norm.normalize(rec)

    def test_both_usdc_raises(self) -> None:
        rec = _order_filled_record(maker_asset="0", taker_asset="0")
        with pytest.raises(NormalizationError, match="Cannot identify USDC side"):
            self.norm.normalize(rec)

    def test_both_non_usdc_raises(self) -> None:
        rec = _order_filled_record(maker_asset="111222333", taker_asset="444555666")
        with pytest.raises(NormalizationError, match="Cannot identify USDC side"):
            self.norm.normalize(rec)

    def test_zero_token_amount_raises(self) -> None:
        rec = _order_filled_record(maker_asset="111222333", taker_asset="0", maker_amount=0)
        with pytest.raises(NormalizationError, match="Zero token amount"):
            self.norm.normalize(rec)

    def test_missing_timestamp_raises(self) -> None:
        rec = _order_filled_record()
        rec["timestamp"] = None
        with pytest.raises(NormalizationError, match="Missing timestamp"):
            self.norm.normalize(rec)

    def test_no_lookup_raises(self) -> None:
        norm = PolymarketTradesNormalizer()
        rec = _order_filled_record()
        with pytest.raises(NormalizationError, match="MarketsReferenceLookup not set"):
            norm.normalize(rec)

    def test_set_lookup(self) -> None:
        norm = PolymarketTradesNormalizer()
        norm.set_lookup(self.lookup)
        rec = _order_filled_record(maker_asset="111222333", taker_asset="0")
        result = norm.normalize(rec)
        assert result["platform_market_id"] == "market-abc"

    def test_dedup_key(self) -> None:
        rec = _order_filled_record()
        key = self.norm.dedup_key(rec)
        assert key == "polymarket:0xabc123:0xmaker:0xtaker:0"

    def test_batch_skips_bad_records(self) -> None:
        good = _order_filled_record(maker_asset="111222333", taker_asset="0")
        bad = _order_filled_record(maker_asset="0", taker_asset="0")  # both USDC
        results = self.norm.normalize_batch([good, bad, good])
        assert len(results) == 2

    def test_lineage_columns(self) -> None:
        rec = _order_filled_record(maker_asset="111222333", taker_asset="0")
        ts = datetime(2026, 1, 30, 12, 0, 0, tzinfo=UTC)
        result = self.norm.normalize(rec, bronze_run_id="r1", silver_ingestion_ts=ts)
        assert result["bronze_run_id"] == "r1"
        assert result["silver_ingestion_ts"] == ts

    def test_platform_and_entity(self) -> None:
        assert self.norm.platform == "polymarket"
        assert self.norm.entity == "trades"


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

class TestRegistry:
    def test_get_normalizer(self) -> None:
        n = get_normalizer("polymarket", "markets")
        assert isinstance(n, PolymarketMarketsNormalizer)

    def test_get_polymarket_trades_normalizer(self) -> None:
        n = get_normalizer("polymarket", "trades")
        assert isinstance(n, PolymarketTradesNormalizer)

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
        assert result["status"] == "unknown"  # No status fields → "unknown"
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
        assert result["status"] == "unknown"  # No status fields → "unknown"
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
