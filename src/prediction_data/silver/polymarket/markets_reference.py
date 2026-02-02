"""Build token ID to market/side lookup from Bronze markets data.

Loads Bronze markets JSONL data, extracts clobTokenIds per market, and
produces a long-form lookup table: (asset_id) -> (market_id, side).

Side is "token1" (index 0 in clobTokenIds) or "token2" (index 1).

Float-notation asset IDs (e.g. 6.58e+76) are also indexed so lookups
work for both full-precision and float-notation keys.
"""

from __future__ import annotations

import gzip
import json
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from prediction_data.core.logging import get_logger

if TYPE_CHECKING:
    from prediction_data.storage.s3 import S3Client

logger = get_logger(__name__)

SIDE_LABELS = ("token1", "token2")


@dataclass(frozen=True, slots=True)
class MarketSide:
    """Lookup result: which market and side a token ID belongs to."""

    market_id: str
    side: str  # "token1" or "token2"


class MarketsReferenceLookup:
    """Token ID -> (market_id, side) lookup table.

    Built from Bronze markets JSONL records. Each market has a
    ``clobTokenIds`` field containing [token1_id, token2_id].
    """

    def __init__(self) -> None:
        self._lookup: dict[str, MarketSide] = {}

    def __len__(self) -> int:
        return len(self._lookup)

    def get(self, asset_id: str) -> MarketSide | None:
        """Look up market_id and side for a given asset ID."""
        return self._lookup.get(asset_id)

    def load_from_records(self, records: list[dict[str, Any]]) -> None:
        """Populate lookup from a list of Bronze markets JSON records.

        Each record should have ``id`` (or ``condition_id``) and
        ``clobTokenIds`` (JSON string or list of token ID strings).
        """
        total = 0
        skipped = 0
        for rec in records:
            market_id = rec.get("id") or rec.get("condition_id")
            if not market_id:
                skipped += 1
                continue
            market_id = str(market_id)

            raw_tokens = rec.get("clobTokenIds")
            if not raw_tokens:
                skipped += 1
                continue

            tokens: list[str]
            if isinstance(raw_tokens, str):
                try:
                    tokens = json.loads(raw_tokens)
                except (json.JSONDecodeError, TypeError):
                    skipped += 1
                    continue
            elif isinstance(raw_tokens, list):
                tokens = raw_tokens
            else:
                skipped += 1
                continue

            for idx, token_id in enumerate(tokens):
                if idx >= len(SIDE_LABELS):
                    break
                token_id_str = str(token_id)
                side = SIDE_LABELS[idx]
                entry = MarketSide(market_id=market_id, side=side)

                # Index by full-precision token ID
                self._lookup[token_id_str] = entry

                # Also index by float-notation for parquet-backfilled data
                try:
                    float_key = str(float(token_id_str))
                    if float_key != token_id_str:
                        self._lookup[float_key] = entry
                except (ValueError, OverflowError):
                    pass

            total += 1

        logger.info(
            "Markets reference lookup built",
            markets_loaded=total,
            markets_skipped=skipped,
            lookup_entries=len(self._lookup),
        )

    def load_from_jsonl_bytes(self, data: bytes) -> None:
        """Load from raw JSONL bytes (possibly gzip-compressed)."""
        try:
            raw = gzip.decompress(data)
        except gzip.BadGzipFile:
            raw = data

        records: list[dict[str, Any]] = []
        for line in raw.split(b"\n"):
            line = line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError:
                continue

        self.load_from_records(records)

    @property
    def coverage_stats(self) -> dict[str, int]:
        """Return coverage statistics for logging."""
        markets = {e.market_id for e in self._lookup.values()}
        return {
            "unique_markets": len(markets),
            "lookup_entries": len(self._lookup),
        }


async def load_markets_reference(
    s3_client: S3Client,
    *,
    end_date: str | None = None,
) -> MarketsReferenceLookup:
    """Build a markets reference lookup from Bronze manifests.

    Discovers all Bronze ``polymarket/markets`` manifests, selects the
    latest snapshot plus any subsequent deltas, reads the data, and
    populates a :class:`MarketsReferenceLookup`.

    Args:
        s3_client: S3 client bound to the Bronze bucket.
        end_date: Optional upper-bound date (YYYY-MM-DD). If ``None``,
            all available dates are considered.

    Returns:
        Populated :class:`MarketsReferenceLookup`.
    """
    from prediction_data.silver.discovery import (
        discover_manifests,
        select_snapshot_and_deltas,
    )
    from prediction_data.silver.reader import read_manifest_data

    all_manifests = await discover_manifests(
        s3_client,
        platform="polymarket",
        entity="markets",
        end_date=end_date,
    )

    selected = select_snapshot_and_deltas(all_manifests)

    lookup = MarketsReferenceLookup()

    if not selected:
        logger.warning("No markets manifests found, returning empty lookup")
        return lookup

    for manifest in selected:
        logger.info(
            "Loading markets manifest",
            dt=manifest.dt,
            run_id=manifest.run_id,
            snapshot_type=manifest.snapshot_type,
        )
        result = await read_manifest_data(s3_client, manifest)
        lookup.load_from_records(result.records)

    logger.info(
        "Markets reference loaded",
        manifests_loaded=len(selected),
        **lookup.coverage_stats,
    )

    return lookup
