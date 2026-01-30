"""Tests for markets reference lookup (token ID -> market/side)."""

from __future__ import annotations

import gzip
import json

from prediction_data.silver.polymarket.markets_reference import (
    MarketSide,
    MarketsReferenceLookup,
)


class TestMarketsReferenceLookup:
    """Core lookup table tests."""

    def _make_market(
        self,
        market_id: str,
        token_ids: list[str],
    ) -> dict:
        return {"id": market_id, "clobTokenIds": json.dumps(token_ids)}

    def test_basic_lookup(self) -> None:
        lookup = MarketsReferenceLookup()
        lookup.load_from_records([
            self._make_market("m1", ["token_a", "token_b"]),
        ])
        assert len(lookup) > 0

        result = lookup.get("token_a")
        assert result == MarketSide(market_id="m1", side="token1")

        result = lookup.get("token_b")
        assert result == MarketSide(market_id="m1", side="token2")

    def test_unknown_asset_returns_none(self) -> None:
        lookup = MarketsReferenceLookup()
        lookup.load_from_records([
            self._make_market("m1", ["token_a", "token_b"]),
        ])
        assert lookup.get("nonexistent") is None

    def test_float_notation_resolution(self) -> None:
        """Large token IDs should be findable via float-notation key."""
        big_id = "65849477124286266918061032853957867543040"
        lookup = MarketsReferenceLookup()
        lookup.load_from_records([
            self._make_market("m1", [big_id, "other"]),
        ])

        # Full-precision lookup
        assert lookup.get(big_id) is not None
        assert lookup.get(big_id).market_id == "m1"

        # Float-notation lookup
        float_key = str(float(big_id))
        assert lookup.get(float_key) is not None
        assert lookup.get(float_key).market_id == "m1"

    def test_multiple_markets(self) -> None:
        lookup = MarketsReferenceLookup()
        lookup.load_from_records([
            self._make_market("m1", ["t1a", "t1b"]),
            self._make_market("m2", ["t2a", "t2b"]),
        ])
        assert lookup.get("t1a").market_id == "m1"
        assert lookup.get("t2a").market_id == "m2"
        assert lookup.get("t1b").side == "token2"
        assert lookup.get("t2a").side == "token1"

    def test_missing_clob_token_ids_skipped(self) -> None:
        lookup = MarketsReferenceLookup()
        lookup.load_from_records([
            {"id": "m1"},  # no clobTokenIds
            self._make_market("m2", ["t2a", "t2b"]),
        ])
        assert lookup.get("t2a") is not None
        stats = lookup.coverage_stats
        assert stats["unique_markets"] == 1

    def test_missing_market_id_skipped(self) -> None:
        lookup = MarketsReferenceLookup()
        lookup.load_from_records([
            {"clobTokenIds": json.dumps(["t1", "t2"])},  # no id
        ])
        assert len(lookup) == 0

    def test_condition_id_fallback(self) -> None:
        lookup = MarketsReferenceLookup()
        lookup.load_from_records([
            {"condition_id": "cond1", "clobTokenIds": json.dumps(["t1", "t2"])},
        ])
        assert lookup.get("t1").market_id == "cond1"

    def test_clob_token_ids_as_list(self) -> None:
        """clobTokenIds can be a native list (not JSON string)."""
        lookup = MarketsReferenceLookup()
        lookup.load_from_records([
            {"id": "m1", "clobTokenIds": ["t1", "t2"]},
        ])
        assert lookup.get("t1") is not None

    def test_more_than_two_tokens_only_first_two(self) -> None:
        """Only first 2 tokens are indexed (token1, token2)."""
        lookup = MarketsReferenceLookup()
        lookup.load_from_records([
            self._make_market("m1", ["t1", "t2", "t3"]),
        ])
        assert lookup.get("t1") is not None
        assert lookup.get("t2") is not None
        assert lookup.get("t3") is None

    def test_coverage_stats(self) -> None:
        lookup = MarketsReferenceLookup()
        lookup.load_from_records([
            self._make_market("m1", ["t1a", "t1b"]),
            self._make_market("m2", ["t2a", "t2b"]),
        ])
        stats = lookup.coverage_stats
        assert stats["unique_markets"] == 2
        assert stats["lookup_entries"] >= 4


class TestLoadFromJsonlBytes:
    """Test loading from raw JSONL bytes."""

    def test_gzipped_jsonl(self) -> None:
        records = [
            {"id": "m1", "clobTokenIds": json.dumps(["t1", "t2"])},
            {"id": "m2", "clobTokenIds": json.dumps(["t3", "t4"])},
        ]
        raw = "\n".join(json.dumps(r) for r in records).encode()
        compressed = gzip.compress(raw)

        lookup = MarketsReferenceLookup()
        lookup.load_from_jsonl_bytes(compressed)
        assert lookup.get("t1") is not None
        assert lookup.get("t3") is not None

    def test_plain_jsonl(self) -> None:
        records = [
            {"id": "m1", "clobTokenIds": json.dumps(["t1", "t2"])},
        ]
        raw = "\n".join(json.dumps(r) for r in records).encode()

        lookup = MarketsReferenceLookup()
        lookup.load_from_jsonl_bytes(raw)
        assert lookup.get("t1") is not None

    def test_empty_input(self) -> None:
        lookup = MarketsReferenceLookup()
        lookup.load_from_jsonl_bytes(b"")
        assert len(lookup) == 0

    def test_malformed_lines_skipped(self) -> None:
        raw = b'{"id":"m1","clobTokenIds":"[\\"t1\\",\\"t2\\"]"}\nnot-json\n'
        lookup = MarketsReferenceLookup()
        lookup.load_from_jsonl_bytes(raw)
        assert lookup.get("t1") is not None
