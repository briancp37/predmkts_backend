"""Integration tests: OrderFilledEvent -> Silver trades pipeline.

Tests the full transformation pipeline with realistic Bronze data samples:
  Bronze markets JSONL → MarketsReferenceLookup
  Bronze order_filled events → derive_trades → PolymarketTradesNormalizer

These tests use realistic record structures matching actual Goldsky subgraph
and Gamma API output, including edge cases from parquet-backfilled data
(missing orderHash/fee/id, float-notation asset IDs).
"""

from __future__ import annotations

import gzip
import json

import pytest

from prediction_data.silver.normalize import (
    NormalizationError,
    PolymarketTradesNormalizer,
)
from prediction_data.silver.polymarket.derive_trades import (
    derive_trades_batch,
)
from prediction_data.silver.polymarket.markets_reference import (
    MarketsReferenceLookup,
)

pytestmark = pytest.mark.integration

# ---------------------------------------------------------------------------
# Realistic Bronze data fixtures
# ---------------------------------------------------------------------------

# Modeled after real Gamma API /markets records stored as Bronze JSONL
BRONZE_MARKETS_RECORDS: list[dict] = [
    {
        "id": "0xbd31dc8a20211944f6b70f31257f866a43df22a5",
        "question": "Will BTC hit $100k by end of 2025?",
        "condition_id": "0xcond_btc100k",
        "slug": "will-btc-hit-100k",
        "clobTokenIds": json.dumps([
            "48331043535085899657362305750079252580571906693705",
            "71044137838484739093467636855828940702015804485320",
        ]),
    },
    {
        "id": "0xf2c3a7d1e9b4c5a8d6e0f3b2c7a9d1e4f5b8c3a2",
        "question": "Will ETH merge succeed?",
        "condition_id": "0xcond_ethmerge",
        "slug": "eth-merge",
        "clobTokenIds": json.dumps([
            "93218476502837465019283746501928374650192837465012",
            "10293847561029384756102938475610293847561029384756",
        ]),
    },
    # Market with no clobTokenIds — should be gracefully skipped
    {
        "id": "0xorphan_market_no_tokens",
        "question": "Orphan market",
        "condition_id": "0xcond_orphan",
        "slug": "orphan",
    },
]

# Token IDs for convenience
BTC_YES_TOKEN = "48331043535085899657362305750079252580571906693705"
BTC_NO_TOKEN = "71044137838484739093467636855828940702015804485320"
ETH_YES_TOKEN = "93218476502837465019283746501928374650192837465012"
ETH_NO_TOKEN = "10293847561029384756102938475610293847561029384756"

# Modeled after real Goldsky subgraph OrderFilledEvent records
BRONZE_ORDER_FILLED_EVENTS: list[dict] = [
    # 1. Taker buys YES token on BTC market (taker provides USDC)
    {
        "id": "0x1234-evt-1",
        "transactionHash": "0xtx_buy_btc_yes",
        "orderHash": "0xorder_1",
        "timestamp": "1706745600",  # 2024-02-01 00:00:00 UTC
        "maker": "0xmaker_alice",
        "taker": "0xtaker_bob",
        "makerAssetId": BTC_YES_TOKEN,
        "takerAssetId": "0",
        "makerAmountFilled": "10000000",  # 10 tokens
        "takerAmountFilled": "6500000",  # 6.5 USDC
        "fee": "13000",
    },
    # 2. Taker sells NO token on BTC market (maker provides USDC)
    {
        "id": "0x1234-evt-2",
        "transactionHash": "0xtx_sell_btc_no",
        "orderHash": "0xorder_2",
        "timestamp": "1706745700",
        "maker": "0xmaker_charlie",
        "taker": "0xtaker_dave",
        "makerAssetId": "0",
        "takerAssetId": BTC_NO_TOKEN,
        "makerAmountFilled": "3000000",  # 3 USDC
        "takerAmountFilled": "8000000",  # 8 tokens
        "fee": "6000",
    },
    # 3. Taker buys YES token on ETH market
    {
        "id": "0x5678-evt-3",
        "transactionHash": "0xtx_buy_eth_yes",
        "orderHash": "0xorder_3",
        "timestamp": "1706745800",
        "maker": "0xmaker_eve",
        "taker": "0xtaker_frank",
        "makerAssetId": ETH_YES_TOKEN,
        "takerAssetId": "0",
        "makerAmountFilled": "20000000",  # 20 tokens
        "takerAmountFilled": "18000000",  # 18 USDC
        "fee": "36000",
    },
    # 4. Parquet-backfilled record: missing orderHash, fee, id
    {
        "id": None,
        "transactionHash": "0xtx_parquet_backfill",
        "orderHash": None,
        "timestamp": "1706745900",
        "maker": "0xmaker_backfill",
        "taker": "0xtaker_backfill",
        "makerAssetId": BTC_YES_TOKEN,
        "takerAssetId": "0",
        "makerAmountFilled": "4450000",  # 4.45 tokens (from parquet float * 1e6)
        "takerAmountFilled": "2000000",  # 2 USDC
        "fee": None,
    },
    # 5. Event with unknown asset ID — should be skipped in batch
    {
        "id": "0xbad-evt",
        "transactionHash": "0xtx_unknown",
        "orderHash": "0xorder_bad",
        "timestamp": "1706746000",
        "maker": "0xmaker_unknown",
        "taker": "0xtaker_unknown",
        "makerAssetId": "999999999999",
        "takerAssetId": "0",
        "makerAmountFilled": "5000000",
        "takerAmountFilled": "2500000",
        "fee": "5000",
    },
    # 6. Event with zero maker amount — should be skipped in batch
    {
        "id": "0xzero-evt",
        "transactionHash": "0xtx_zero",
        "orderHash": "0xorder_zero",
        "timestamp": "1706746100",
        "maker": "0xmaker_zero",
        "taker": "0xtaker_zero",
        "makerAssetId": BTC_YES_TOKEN,
        "takerAssetId": "0",
        "makerAmountFilled": "0",
        "takerAmountFilled": "1000000",
        "fee": "0",
    },
]


def _build_lookup_from_jsonl_bytes() -> MarketsReferenceLookup:
    """Build lookup from gzip-compressed JSONL, simulating S3 Bronze read."""
    raw = "\n".join(json.dumps(r) for r in BRONZE_MARKETS_RECORDS).encode()
    compressed = gzip.compress(raw)
    lookup = MarketsReferenceLookup()
    lookup.load_from_jsonl_bytes(compressed)
    return lookup


class TestEndToEndLookupBuild:
    """Verify lookup table built from realistic Bronze markets data."""

    def test_lookup_resolves_all_known_tokens(self) -> None:
        lookup = _build_lookup_from_jsonl_bytes()
        for token, expected_market in [
            (BTC_YES_TOKEN, "0xbd31dc8a20211944f6b70f31257f866a43df22a5"),
            (BTC_NO_TOKEN, "0xbd31dc8a20211944f6b70f31257f866a43df22a5"),
            (ETH_YES_TOKEN, "0xf2c3a7d1e9b4c5a8d6e0f3b2c7a9d1e4f5b8c3a2"),
            (ETH_NO_TOKEN, "0xf2c3a7d1e9b4c5a8d6e0f3b2c7a9d1e4f5b8c3a2"),
        ]:
            result = lookup.get(token)
            assert result is not None, f"Token {token[:20]}... not found"
            assert result.market_id == expected_market

    def test_lookup_sides_correct(self) -> None:
        lookup = _build_lookup_from_jsonl_bytes()
        assert lookup.get(BTC_YES_TOKEN).side == "token1"
        assert lookup.get(BTC_NO_TOKEN).side == "token2"
        assert lookup.get(ETH_YES_TOKEN).side == "token1"
        assert lookup.get(ETH_NO_TOKEN).side == "token2"

    def test_orphan_market_skipped(self) -> None:
        lookup = _build_lookup_from_jsonl_bytes()
        stats = lookup.coverage_stats
        assert stats["unique_markets"] == 2  # not 3

    def test_float_notation_resolves(self) -> None:
        """Large token IDs should be findable via float-notation key."""
        lookup = _build_lookup_from_jsonl_bytes()
        float_key = str(float(BTC_YES_TOKEN))
        assert lookup.get(float_key) is not None
        assert lookup.get(float_key).market_id == lookup.get(BTC_YES_TOKEN).market_id


class TestEndToEndBatchDerivation:
    """Run batch derivation on realistic Bronze order_filled events."""

    def setup_method(self) -> None:
        self.lookup = _build_lookup_from_jsonl_bytes()

    def test_batch_processes_valid_and_skips_bad(self) -> None:
        results = derive_trades_batch(BRONZE_ORDER_FILLED_EVENTS, self.lookup)
        # Events 1-4 should succeed, 5 (unknown asset) and 6 (zero amount) should skip
        assert len(results) == 4

    def test_buy_btc_yes_trade(self) -> None:
        results = derive_trades_batch(BRONZE_ORDER_FILLED_EVENTS[:1], self.lookup)
        trade = results[0]
        assert trade["taker_direction"] == "buy"
        assert trade["maker_direction"] == "sell"
        assert trade["nonusdc_side"] == "token1"
        assert trade["usd_amount"] == pytest.approx(6.5)
        assert trade["token_amount"] == pytest.approx(10.0)
        assert trade["price"] == pytest.approx(0.65)
        assert trade["transaction_hash"] == "0xtx_buy_btc_yes"

    def test_sell_btc_no_trade(self) -> None:
        results = derive_trades_batch(BRONZE_ORDER_FILLED_EVENTS[1:2], self.lookup)
        trade = results[0]
        assert trade["taker_direction"] == "sell"
        assert trade["maker_direction"] == "buy"
        assert trade["nonusdc_side"] == "token2"
        assert trade["usd_amount"] == pytest.approx(3.0)
        assert trade["token_amount"] == pytest.approx(8.0)
        assert trade["price"] == pytest.approx(0.375)

    def test_parquet_backfill_record(self) -> None:
        """Parquet-backfilled records (missing id/orderHash/fee) should derive."""
        results = derive_trades_batch(BRONZE_ORDER_FILLED_EVENTS[3:4], self.lookup)
        assert len(results) == 1
        trade = results[0]
        assert trade["transaction_hash"] == "0xtx_parquet_backfill"
        assert trade["trade_id"] == "0xtx_parquet_backfill"
        assert trade["price"] == pytest.approx(2.0 / 4.45, rel=1e-4)

    def test_cross_market_trades(self) -> None:
        """Trades across different markets should resolve to correct market IDs."""
        results = derive_trades_batch(BRONZE_ORDER_FILLED_EVENTS[:3], self.lookup)
        market_ids = [r["market_id"] for r in results]
        assert market_ids[0] == "0xbd31dc8a20211944f6b70f31257f866a43df22a5"  # BTC
        assert market_ids[1] == "0xbd31dc8a20211944f6b70f31257f866a43df22a5"  # BTC
        assert market_ids[2] == "0xf2c3a7d1e9b4c5a8d6e0f3b2c7a9d1e4f5b8c3a2"  # ETH


class TestEndToEndNormalizer:
    """Full pipeline: Bronze events through PolymarketTradesNormalizer."""

    def setup_method(self) -> None:
        self.lookup = _build_lookup_from_jsonl_bytes()
        self.norm = PolymarketTradesNormalizer(lookup=self.lookup)

    def test_normalize_produces_silver_schema(self) -> None:
        event = BRONZE_ORDER_FILLED_EVENTS[0]
        result = self.norm.normalize(event, bronze_run_id="run-integ-1")

        # All Silver trades schema fields present
        assert result["platform_market_id"] == "0xbd31dc8a20211944f6b70f31257f866a43df22a5"
        assert result["taker_direction"] == "buy"
        assert result["maker_direction"] == "sell"
        assert result["nonusdc_side"] == "token1"
        assert result["price"] == pytest.approx(0.65)
        assert result["usd_amount"] == pytest.approx(6.5)
        assert result["token_amount"] == pytest.approx(10.0)
        assert result["transaction_hash"] == "0xtx_buy_btc_yes"
        assert result["bronze_run_id"] == "run-integ-1"
        assert result["event_ts"] is not None
        # silver_ingestion_ts is set when explicitly passed; defaults to None
        assert "silver_ingestion_ts" in result

    def test_normalize_batch_skips_errors(self) -> None:
        results = self.norm.normalize_batch(
            BRONZE_ORDER_FILLED_EVENTS,
            bronze_run_id="run-batch",
        )
        # 4 valid out of 6 (unknown asset + zero amount skipped)
        assert len(results) == 4

    def test_unknown_asset_raises_normalization_error(self) -> None:
        bad_event = BRONZE_ORDER_FILLED_EVENTS[4]  # unknown asset
        with pytest.raises(NormalizationError, match="Market lookup failed"):
            self.norm.normalize(bad_event)

    def test_zero_amount_raises_normalization_error(self) -> None:
        zero_event = BRONZE_ORDER_FILLED_EVENTS[5]  # zero maker amount
        with pytest.raises(NormalizationError, match="Zero token amount"):
            self.norm.normalize(zero_event)

    def test_parquet_record_normalizes(self) -> None:
        """Parquet-backfilled record (null fields) normalizes correctly."""
        event = BRONZE_ORDER_FILLED_EVENTS[3]
        result = self.norm.normalize(event, bronze_run_id="run-parquet")
        assert result["transaction_hash"] == "0xtx_parquet_backfill"
        assert result["bronze_run_id"] == "run-parquet"
        assert result["price"] == pytest.approx(2.0 / 4.45, rel=1e-4)
