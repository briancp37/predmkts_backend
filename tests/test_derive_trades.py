"""Tests for silver/polymarket/derive_trades.py — OrderFilledEvent to trade derivation."""

from __future__ import annotations

import pytest

from prediction_data.silver.polymarket.derive_trades import (
    TradeDerivationError,
    derive_trade,
    derive_trades_batch,
)
from prediction_data.silver.polymarket.markets_reference import (
    MarketsReferenceLookup,
)


def _make_lookup(*entries: tuple[str, str, str]) -> MarketsReferenceLookup:
    """Build a lookup from (asset_id, market_id, side) tuples."""
    lookup = MarketsReferenceLookup()
    records = []
    for asset_id, market_id, side in entries:
        # Build a fake markets record with clobTokenIds
        if side == "token1":
            tokens = [asset_id, "9999"]
        else:
            tokens = ["9999", asset_id]
        records.append({"id": market_id, "clobTokenIds": tokens})
    lookup.load_from_records(records)
    return lookup


def _base_event(**overrides: object) -> dict[str, object]:
    """Return a valid OrderFilledEvent with optional overrides."""
    event: dict[str, object] = {
        "id": "evt-1",
        "transactionHash": "0xabc",
        "orderHash": "0xdef",
        "timestamp": "1700000000",
        "maker": "0xmaker",
        "taker": "0xtaker",
        "makerAssetId": "100",  # conditional token
        "takerAssetId": "0",  # USDC
        "makerAmountFilled": "5000000",  # 5 tokens
        "takerAmountFilled": "3000000",  # 3 USDC
        "fee": "10000",
    }
    event.update(overrides)
    return event


class TestDeriveTradeBasic:
    """Basic trade derivation: taker provides USDC (buy)."""

    def setup_method(self) -> None:
        self.lookup = _make_lookup(("100", "market-A", "token1"))

    def test_taker_buys(self) -> None:
        """Taker provides USDC -> taker is buying."""
        result = derive_trade(_base_event(), self.lookup)
        assert result["taker_direction"] == "buy"
        assert result["maker_direction"] == "sell"
        assert result["market_id"] == "market-A"
        assert result["nonusdc_side"] == "token1"

    def test_amounts_scaled(self) -> None:
        result = derive_trade(_base_event(), self.lookup)
        assert result["usd_amount"] == pytest.approx(3.0)
        assert result["token_amount"] == pytest.approx(5.0)

    def test_price_calculation(self) -> None:
        result = derive_trade(_base_event(), self.lookup)
        assert result["price"] == pytest.approx(3.0 / 5.0)

    def test_output_fields(self) -> None:
        result = derive_trade(_base_event(), self.lookup)
        assert result["timestamp"] == "1700000000"
        assert result["maker"] == "0xmaker"
        assert result["taker"] == "0xtaker"
        assert result["transaction_hash"] == "0xabc"
        assert result["trade_id"] == "evt-1"


class TestDeriveTradeReversed:
    """Maker provides USDC, taker provides conditional token (sell)."""

    def setup_method(self) -> None:
        self.lookup = _make_lookup(("200", "market-B", "token2"))

    def test_taker_sells(self) -> None:
        event = _base_event(
            makerAssetId="0",
            takerAssetId="200",
            makerAmountFilled="4000000",  # 4 USDC (maker provides)
            takerAmountFilled="2000000",  # 2 tokens (taker provides)
        )
        result = derive_trade(event, self.lookup)
        assert result["taker_direction"] == "sell"
        assert result["maker_direction"] == "buy"
        assert result["market_id"] == "market-B"
        assert result["nonusdc_side"] == "token2"
        assert result["usd_amount"] == pytest.approx(4.0)
        assert result["token_amount"] == pytest.approx(2.0)
        assert result["price"] == pytest.approx(2.0)


class TestDeriveTradeEdgeCases:
    """Edge cases and error handling."""

    def setup_method(self) -> None:
        self.lookup = _make_lookup(("100", "market-A", "token1"))

    def test_both_non_usdc_raises(self) -> None:
        event = _base_event(makerAssetId="100", takerAssetId="200")
        with pytest.raises(TradeDerivationError, match="Cannot identify USDC"):
            derive_trade(event, self.lookup)

    def test_both_usdc_raises(self) -> None:
        event = _base_event(makerAssetId="0", takerAssetId="0")
        with pytest.raises(TradeDerivationError, match="Cannot identify USDC"):
            derive_trade(event, self.lookup)

    def test_missing_asset_id_raises(self) -> None:
        event = _base_event(makerAssetId="", takerAssetId="0")
        with pytest.raises(TradeDerivationError, match="Missing"):
            derive_trade(event, self.lookup)

    def test_market_lookup_fails(self) -> None:
        event = _base_event(makerAssetId="999", takerAssetId="0")
        with pytest.raises(TradeDerivationError, match="Market lookup failed"):
            derive_trade(event, self.lookup)

    def test_zero_token_amount_raises(self) -> None:
        event = _base_event(makerAmountFilled="0")
        with pytest.raises(TradeDerivationError, match="Zero token amount"):
            derive_trade(event, self.lookup)

    def test_invalid_amount_raises(self) -> None:
        event = _base_event(makerAmountFilled="not-a-number")
        with pytest.raises(TradeDerivationError, match="Invalid amount"):
            derive_trade(event, self.lookup)

    def test_none_amount_raises(self) -> None:
        event = _base_event(makerAmountFilled=None)
        with pytest.raises(TradeDerivationError, match="Invalid amount"):
            derive_trade(event, self.lookup)

    def test_no_tx_hash_falls_back_to_id(self) -> None:
        event = _base_event(transactionHash=None)
        result = derive_trade(event, self.lookup)
        assert result["trade_id"] == "evt-1"
        assert result["transaction_hash"] is None


class TestDeriveTradeBatch:
    """Batch derivation with mixed valid/invalid records."""

    def setup_method(self) -> None:
        self.lookup = _make_lookup(("100", "market-A", "token1"))

    def test_batch_skips_failures(self) -> None:
        records = [
            _base_event(),
            _base_event(makerAssetId="999", takerAssetId="0"),  # lookup fail
            _base_event(makerAmountFilled="0"),  # zero amount
        ]
        results = derive_trades_batch(records, self.lookup)
        assert len(results) == 1
        assert results[0]["market_id"] == "market-A"

    def test_batch_all_valid(self) -> None:
        records = [_base_event(), _base_event()]
        results = derive_trades_batch(records, self.lookup)
        assert len(results) == 2

    def test_batch_empty(self) -> None:
        results = derive_trades_batch([], self.lookup)
        assert results == []
