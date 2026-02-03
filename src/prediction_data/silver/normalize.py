"""Bronze → Silver normalizers.

Each normalizer converts raw Bronze JSON records (dicts) into typed Silver
records ready for Iceberg ingestion.  The base class defines the interface;
concrete implementations handle per-entity field mapping, type coercion,
null handling, and dedup-key generation.
"""

from __future__ import annotations

import hashlib
import json
from abc import ABC, abstractmethod
from datetime import UTC, datetime
from typing import Any

from prediction_data.core.logging import get_logger
from prediction_data.silver.polymarket.derive_trades import (
    TradeDerivationError,
    derive_trade,
)
from prediction_data.silver.polymarket.markets_reference import MarketsReferenceLookup

logger = get_logger(__name__)


class NormalizationError(Exception):
    """Raised when a Bronze record cannot be normalized."""


# ---------------------------------------------------------------------------
# Base interface
# ---------------------------------------------------------------------------

class Normalizer(ABC):
    """Base normalizer interface for Bronze → Silver transformation."""

    @property
    @abstractmethod
    def platform(self) -> str:
        """Platform identifier (e.g. 'polymarket', 'kalshi')."""

    @property
    @abstractmethod
    def entity(self) -> str:
        """Entity name (e.g. 'trades', 'markets', 'events')."""

    @abstractmethod
    def normalize(
        self,
        record: dict[str, Any],
        *,
        bronze_run_id: str | None = None,
        silver_ingestion_ts: datetime | None = None,
    ) -> dict[str, Any]:
        """Convert a single Bronze JSON record to a Silver-typed dict.

        Args:
            record: Raw Bronze JSON record.
            bronze_run_id: Optional run ID for lineage tracking.
            silver_ingestion_ts: Optional timestamp of Silver processing.

        Returns:
            Dict matching the Silver Iceberg schema for this entity.

        Raises:
            NormalizationError: If the record cannot be normalized.
        """

    @abstractmethod
    def dedup_key(self, record: dict[str, Any]) -> str:
        """Return a string dedup key for the raw Bronze record.

        Used for deduplication before or during Silver writes.
        """

    @abstractmethod
    def merge_keys(self) -> list[str]:
        """Return Silver column names used as join keys for Iceberg upsert.

        These define the natural identity of the entity — records matching
        on these columns will be updated rather than inserted.
        """

    # Convenience: normalize a batch
    def normalize_batch(
        self,
        records: list[dict[str, Any]],
        *,
        bronze_run_id: str | None = None,
        silver_ingestion_ts: datetime | None = None,
    ) -> list[dict[str, Any]]:
        """Normalize a list of records, skipping failures with warnings."""
        results: list[dict[str, Any]] = []
        for rec in records:
            try:
                results.append(
                    self.normalize(
                        rec,
                        bronze_run_id=bronze_run_id,
                        silver_ingestion_ts=silver_ingestion_ts,
                    )
                )
            except NormalizationError:
                logger.warning(
                    "Skipping record due to normalization error",
                    platform=self.platform,
                    entity=self.entity,
                    record_snippet=str(rec)[:200],
                )
        return results


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _parse_timestamp_utc(value: Any) -> datetime:
    """Parse a timestamp value to a timezone-aware UTC datetime.

    Accepts:
      - int/float: Unix epoch seconds
      - str of digits: Unix epoch seconds
      - ISO-8601 string (with or without timezone)
    """
    if value is None:
        raise NormalizationError("Timestamp is None")

    # Numeric (int, float, or string of digits)
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(value, tz=UTC)
    if isinstance(value, str):
        stripped = value.strip()
        if stripped.isdigit():
            return datetime.fromtimestamp(int(stripped), tz=UTC)
        # Try float string (e.g. "1700000000.5")
        try:
            return datetime.fromtimestamp(float(stripped), tz=UTC)
        except ValueError:
            pass
        # ISO-8601
        try:
            dt = datetime.fromisoformat(stripped.replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=UTC)
            return dt
        except ValueError:
            pass

    raise NormalizationError(f"Cannot parse timestamp: {value!r}")


def _safe_str(value: Any) -> str | None:
    """Coerce to string or return None."""
    if value is None:
        return None
    return str(value)


def _safe_float(value: Any) -> float | None:
    """Coerce to float or return None."""
    if value is None:
        return None
    try:
        return float(value)
    except (ValueError, TypeError):
        return None


def _safe_int(value: Any) -> int | None:
    """Coerce to int or return None."""
    if value is None:
        return None
    try:
        return int(value)
    except (ValueError, TypeError):
        return None


def _content_hash(*fields: Any) -> str:
    """SHA-256 content hash over field values."""
    payload = json.dumps(fields, sort_keys=True, default=str)
    return hashlib.sha256(payload.encode()).hexdigest()


# ---------------------------------------------------------------------------
# Polymarket Markets Normalizer
# ---------------------------------------------------------------------------

class PolymarketMarketsNormalizer(Normalizer):
    """Normalize Bronze Polymarket markets (Gamma API) → Silver."""

    @property
    def platform(self) -> str:
        return "polymarket"

    @property
    def entity(self) -> str:
        return "markets"

    def dedup_key(self, record: dict[str, Any]) -> str:
        market_id = record.get("id") or record.get("condition_id") or record.get("conditionId", "")
        updated = record.get("updatedAt") or record.get("updated_at", "")
        return f"polymarket:{market_id}:{updated}"

    def merge_keys(self) -> list[str]:
        return ["platform_market_id"]

    def normalize(
        self,
        record: dict[str, Any],
        *,
        bronze_run_id: str | None = None,
        silver_ingestion_ts: datetime | None = None,
    ) -> dict[str, Any]:
        # Support both camelCase (Gamma API) and snake_case field names
        market_id = record.get("id") or record.get("condition_id") or record.get("conditionId")
        if not market_id:
            raise NormalizationError("Missing market id")

        # event_ts: use updatedAt, or fall back to endDateIso, or error
        # Support both camelCase and snake_case
        raw_ts = (
            record.get("updatedAt") or record.get("updated_at") or
            record.get("endDateIso") or record.get("end_date_iso")
        )
        if not raw_ts:
            raise NormalizationError(f"No timestamp for market {market_id}")
        event_ts = _parse_timestamp_utc(raw_ts)

        # tokens: serialize list/dict to JSON string
        tokens_raw = record.get("tokens") or record.get("clobTokenIds")
        tokens_str: str | None = None
        if tokens_raw is not None:
            tokens_str = json.dumps(tokens_raw) if not isinstance(tokens_raw, str) else tokens_raw

        updated_at: datetime | None = None
        raw_updated = record.get("updatedAt") or record.get("updated_at")
        if raw_updated:
            updated_at = _parse_timestamp_utc(raw_updated)

        # Extract event_id from events array if present (Gamma API format)
        event_id = record.get("event_id")
        if not event_id and record.get("events"):
            events_list = record.get("events", [])
            if events_list and isinstance(events_list, list) and len(events_list) > 0:
                event_id = events_list[0].get("id")

        return {
            "event_ts": event_ts,
            "platform_market_id": str(market_id),
            "question": _safe_str(record.get("question")),
            "description": _safe_str(record.get("description")),
            "market_slug": _safe_str(record.get("market_slug") or record.get("slug")),
            "status": _safe_str(record.get("status") or record.get("active")),
            "outcome": _safe_str(record.get("outcome")),
            "tokens": tokens_str,
            "event_id": _safe_str(event_id),
            "updated_at": updated_at,
            "bronze_run_id": bronze_run_id,
            "silver_ingestion_ts": silver_ingestion_ts,
        }


# ---------------------------------------------------------------------------
# Polymarket Events Normalizer
# ---------------------------------------------------------------------------

class PolymarketEventsNormalizer(Normalizer):
    """Normalize Bronze Polymarket events (Gamma API) → Silver."""

    @property
    def platform(self) -> str:
        return "polymarket"

    @property
    def entity(self) -> str:
        return "events"

    def dedup_key(self, record: dict[str, Any]) -> str:
        event_id = record.get("id", "")
        updated = record.get("updatedAt") or record.get("updated_at", "")
        return f"polymarket:{event_id}:{updated}"

    def merge_keys(self) -> list[str]:
        return ["platform_event_id"]

    def normalize(
        self,
        record: dict[str, Any],
        *,
        bronze_run_id: str | None = None,
        silver_ingestion_ts: datetime | None = None,
    ) -> dict[str, Any]:
        event_id = record.get("id")
        if not event_id:
            raise NormalizationError("Missing event id")

        # Support both camelCase (Gamma API) and snake_case field names
        # Fall back through: updatedAt -> endDateIso -> endDate
        raw_ts = (
            record.get("updatedAt") or record.get("updated_at") or
            record.get("endDateIso") or record.get("end_date_iso") or
            record.get("endDate") or record.get("end_date")
        )
        if not raw_ts:
            raise NormalizationError(f"No timestamp for event {event_id}")
        event_ts = _parse_timestamp_utc(raw_ts)

        updated_at: datetime | None = None
        raw_updated = record.get("updatedAt") or record.get("updated_at")
        if raw_updated:
            updated_at = _parse_timestamp_utc(raw_updated)

        return {
            "event_ts": event_ts,
            "platform_event_id": str(event_id),
            "title": _safe_str(record.get("title")),
            "description": _safe_str(record.get("description")),
            "slug": _safe_str(record.get("slug")),
            "status": _safe_str(record.get("status")),
            "category": _safe_str(record.get("category")),
            "updated_at": updated_at,
            "bronze_run_id": bronze_run_id,
            "silver_ingestion_ts": silver_ingestion_ts,
        }


# ---------------------------------------------------------------------------
# Kalshi Scaffold Normalizers
# ---------------------------------------------------------------------------

class KalshiTradesNormalizer(Normalizer):
    """Scaffold normalizer for Kalshi trades (no data yet)."""

    @property
    def platform(self) -> str:
        return "kalshi"

    @property
    def entity(self) -> str:
        return "trades"

    def dedup_key(self, record: dict[str, Any]) -> str:
        trade_id = record.get("trade_id", "")
        return f"kalshi:{trade_id}"

    def merge_keys(self) -> list[str]:
        return ["platform_trade_id"]

    def normalize(
        self,
        record: dict[str, Any],
        *,
        bronze_run_id: str | None = None,
        silver_ingestion_ts: datetime | None = None,
    ) -> dict[str, Any]:
        trade_id = record.get("trade_id")
        if not trade_id:
            raise NormalizationError("Missing trade_id")

        raw_ts = record.get("created_time")
        if not raw_ts:
            raise NormalizationError(f"No timestamp for trade {trade_id}")
        event_ts = _parse_timestamp_utc(raw_ts)

        return {
            "event_ts": event_ts,
            "platform_market_id": _safe_str(record.get("ticker")) or "",
            "platform_trade_id": str(trade_id),
            "side": _safe_str(record.get("side")),
            "yes_price": _safe_float(record.get("yes_price")),
            "no_price": _safe_float(record.get("no_price")),
            "count": _safe_int(record.get("count")),
            "taker_side": _safe_str(record.get("taker_side")),
            "bronze_run_id": bronze_run_id,
            "silver_ingestion_ts": silver_ingestion_ts,
        }


class KalshiMarketsNormalizer(Normalizer):
    """Scaffold normalizer for Kalshi markets (no data yet)."""

    @property
    def platform(self) -> str:
        return "kalshi"

    @property
    def entity(self) -> str:
        return "markets"

    def dedup_key(self, record: dict[str, Any]) -> str:
        ticker = record.get("ticker", "")
        updated = record.get("updated_at", "")
        return f"kalshi:{ticker}:{updated}"

    def merge_keys(self) -> list[str]:
        return ["platform_market_id"]

    def normalize(
        self,
        record: dict[str, Any],
        *,
        bronze_run_id: str | None = None,
        silver_ingestion_ts: datetime | None = None,
    ) -> dict[str, Any]:
        ticker = record.get("ticker")
        if not ticker:
            raise NormalizationError("Missing ticker")

        raw_ts = record.get("updated_at")
        if not raw_ts:
            raise NormalizationError(f"No timestamp for market {ticker}")
        event_ts = _parse_timestamp_utc(raw_ts)

        updated_at: datetime | None = None
        if record.get("updated_at"):
            updated_at = _parse_timestamp_utc(record["updated_at"])

        return {
            "event_ts": event_ts,
            "platform_market_id": str(ticker),
            "title": _safe_str(record.get("title")),
            "subtitle": _safe_str(record.get("subtitle")),
            "status": _safe_str(record.get("status")),
            "event_ticker": _safe_str(record.get("event_ticker")),
            "series_ticker": _safe_str(record.get("series_ticker")),
            "updated_at": updated_at,
            "bronze_run_id": bronze_run_id,
            "silver_ingestion_ts": silver_ingestion_ts,
        }


class KalshiEventsNormalizer(Normalizer):
    """Scaffold normalizer for Kalshi events (no data yet)."""

    @property
    def platform(self) -> str:
        return "kalshi"

    @property
    def entity(self) -> str:
        return "events"

    def dedup_key(self, record: dict[str, Any]) -> str:
        ticker = record.get("ticker", "")
        updated = record.get("updated_at", "")
        return f"kalshi:{ticker}:{updated}"

    def merge_keys(self) -> list[str]:
        return ["platform_event_id"]

    def normalize(
        self,
        record: dict[str, Any],
        *,
        bronze_run_id: str | None = None,
        silver_ingestion_ts: datetime | None = None,
    ) -> dict[str, Any]:
        ticker = record.get("ticker")
        if not ticker:
            raise NormalizationError("Missing ticker")

        raw_ts = record.get("updated_at")
        if not raw_ts:
            raise NormalizationError(f"No timestamp for event {ticker}")
        event_ts = _parse_timestamp_utc(raw_ts)

        updated_at: datetime | None = None
        if record.get("updated_at"):
            updated_at = _parse_timestamp_utc(record["updated_at"])

        return {
            "event_ts": event_ts,
            "platform_event_id": str(ticker),
            "title": _safe_str(record.get("title")),
            "category": _safe_str(record.get("category")),
            "status": _safe_str(record.get("status")),
            "series_ticker": _safe_str(record.get("series_ticker")),
            "updated_at": updated_at,
            "bronze_run_id": bronze_run_id,
            "silver_ingestion_ts": silver_ingestion_ts,
        }


# ---------------------------------------------------------------------------
# Polymarket Trades Normalizer (derived from OrderFilledEvents)
# ---------------------------------------------------------------------------


class PolymarketTradesNormalizer(Normalizer):
    """Normalize Bronze OrderFilledEvents → Silver trades via trade derivation.

    Unlike other normalizers that map fields 1:1, this normalizer delegates
    to the trade derivation logic which resolves conditional tokens to markets,
    computes price, and determines buy/sell direction.

    Requires a ``MarketsReferenceLookup`` to resolve token IDs to markets.
    """

    def __init__(self, lookup: MarketsReferenceLookup | None = None) -> None:
        self._lookup = lookup

    @property
    def platform(self) -> str:
        return "polymarket"

    @property
    def entity(self) -> str:
        return "trades"

    @property
    def lookup(self) -> MarketsReferenceLookup:
        if self._lookup is None:
            raise NormalizationError(
                "MarketsReferenceLookup not set — call set_lookup() before normalizing"
            )
        return self._lookup

    def set_lookup(self, lookup: MarketsReferenceLookup) -> None:
        """Set the markets reference lookup table."""
        self._lookup = lookup

    def dedup_key(self, record: dict[str, Any]) -> str:
        tx_hash = record.get("transactionHash", "")
        maker = record.get("maker", "")
        taker = record.get("taker", "")
        maker_asset = record.get("makerAssetId", "")
        return f"polymarket:{tx_hash}:{maker}:{taker}:{maker_asset}"

    def merge_keys(self) -> list[str]:
        return ["platform_trade_id"]

    def normalize(
        self,
        record: dict[str, Any],
        *,
        bronze_run_id: str | None = None,
        silver_ingestion_ts: datetime | None = None,
    ) -> dict[str, Any]:
        try:
            trade = derive_trade(record, self.lookup)
        except TradeDerivationError as e:
            raise NormalizationError(str(e)) from e

        # Parse timestamp to UTC datetime
        raw_ts = trade["timestamp"]
        if raw_ts is None:
            raise NormalizationError("Missing timestamp in derived trade")
        event_ts = _parse_timestamp_utc(raw_ts)

        return {
            "event_ts": event_ts,
            "platform_market_id": trade["market_id"],
            "platform_trade_id": trade["trade_id"],
            "maker": trade["maker"],
            "taker": trade["taker"],
            "nonusdc_side": trade["nonusdc_side"],
            "maker_direction": trade["maker_direction"],
            "taker_direction": trade["taker_direction"],
            "price": trade["price"],
            "usd_amount": trade["usd_amount"],
            "token_amount": trade["token_amount"],
            "transaction_hash": trade.get("transaction_hash"),
            "bronze_run_id": bronze_run_id,
            "silver_ingestion_ts": silver_ingestion_ts,
        }


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

NORMALIZERS: dict[tuple[str, str], type[Normalizer]] = {
    ("polymarket", "trades"): PolymarketTradesNormalizer,
    ("polymarket", "markets"): PolymarketMarketsNormalizer,
    ("polymarket", "events"): PolymarketEventsNormalizer,
    ("kalshi", "trades"): KalshiTradesNormalizer,
    ("kalshi", "markets"): KalshiMarketsNormalizer,
    ("kalshi", "events"): KalshiEventsNormalizer,
}


def get_normalizer(platform: str, entity: str) -> Normalizer:
    """Look up and instantiate the normalizer for a platform/entity pair."""
    key = (platform, entity)
    cls = NORMALIZERS.get(key)
    if cls is None:
        raise ValueError(f"No normalizer registered for {key}")
    return cls()
