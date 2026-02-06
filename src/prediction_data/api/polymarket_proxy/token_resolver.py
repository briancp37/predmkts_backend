"""Token ID resolution for mapping market IDs to Polymarket CLOB token IDs.

Provides caching and efficient lookup of token IDs from our dim_outcome table.
Token IDs are stable identifiers that don't change, so they are cached in memory.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from prediction_data.api.clickhouse import execute_query, get_clickhouse_client
from prediction_data.core.logging import get_logger

if TYPE_CHECKING:
    from clickhouse_connect.driver.client import Client

logger = get_logger(__name__)


@dataclass
class MarketTokens:
    """Token IDs for a market's outcomes."""

    market_id: str
    tokens: list[dict[str, str]] = field(default_factory=list)

    @property
    def yes_token_id(self) -> str | None:
        """Get the YES outcome token ID (typically token1/first outcome)."""
        for token in self.tokens:
            label = token.get("outcome_label", "").lower()
            side = token.get("side", "").lower()
            if "yes" in label or side == "token1":
                return token.get("token_id")
        # Fall back to first token if no explicit YES found
        return self.tokens[0]["token_id"] if self.tokens else None

    @property
    def no_token_id(self) -> str | None:
        """Get the NO outcome token ID (typically token2/second outcome)."""
        for token in self.tokens:
            label = token.get("outcome_label", "").lower()
            side = token.get("side", "").lower()
            if "no" in label or side == "token2":
                return token.get("token_id")
        # Fall back to second token if available
        return self.tokens[1]["token_id"] if len(self.tokens) > 1 else None

    @property
    def all_token_ids(self) -> list[str]:
        """Get all token IDs for this market."""
        return [t["token_id"] for t in self.tokens if t.get("token_id")]


class TokenResolver:
    """Resolves market IDs to Polymarket CLOB token IDs.

    Caches token mappings in memory since they don't change.
    Thread-safe for concurrent access.
    """

    def __init__(self, max_cache_size: int = 50000) -> None:
        """Initialize the token resolver.

        Args:
            max_cache_size: Maximum number of market mappings to cache.
        """
        self._cache: dict[str, MarketTokens] = {}
        self._max_cache_size = max_cache_size
        self._cache_hits = 0
        self._cache_misses = 0

    async def get_tokens(
        self,
        market_id: str,
        *,
        client: Client | None = None,
    ) -> MarketTokens | None:
        """Get token IDs for a market.

        Args:
            market_id: Our platform_market_id.
            client: Optional ClickHouse client.

        Returns:
            MarketTokens with all token IDs, or None if market not found.
        """
        # Check cache first
        if market_id in self._cache:
            self._cache_hits += 1
            return self._cache[market_id]

        self._cache_misses += 1

        # Query ClickHouse
        ch = client or get_clickhouse_client()
        query = """
            SELECT
                o.market_id,
                o.outcome_id,
                o.token_id,
                o.side,
                o.outcome_label
            FROM prediction_gold.dim_outcome o
            WHERE o.platform = 'polymarket'
                AND o.market_id = {market_id:String}
            ORDER BY o.side
        """
        rows = await execute_query(query, {"market_id": market_id}, client=ch)

        if not rows:
            logger.debug("No tokens found for market", market_id=market_id)
            return None

        # Build MarketTokens
        tokens = []
        for row in rows:
            token_id = row.get("token_id")
            if token_id:
                tokens.append({
                    "outcome_id": row.get("outcome_id", ""),
                    "token_id": token_id,
                    "side": row.get("side", ""),
                    "outcome_label": row.get("outcome_label", ""),
                })

        market_tokens = MarketTokens(market_id=market_id, tokens=tokens)

        # Cache the result (evict oldest if full)
        if len(self._cache) >= self._max_cache_size:
            # Simple eviction: remove first item (oldest insertion)
            oldest_key = next(iter(self._cache))
            del self._cache[oldest_key]

        self._cache[market_id] = market_tokens
        return market_tokens

    async def get_tokens_batch(
        self,
        market_ids: list[str],
        *,
        client: Client | None = None,
    ) -> dict[str, MarketTokens]:
        """Get token IDs for multiple markets efficiently.

        Args:
            market_ids: List of platform_market_ids.
            client: Optional ClickHouse client.

        Returns:
            Dict mapping market_id to MarketTokens. Missing markets are omitted.
        """
        result: dict[str, MarketTokens] = {}
        uncached: list[str] = []

        # Check cache for each market
        for market_id in market_ids:
            if market_id in self._cache:
                self._cache_hits += 1
                result[market_id] = self._cache[market_id]
            else:
                uncached.append(market_id)

        if not uncached:
            return result

        # Query uncached markets in batch
        self._cache_misses += len(uncached)
        ch = client or get_clickhouse_client()

        query = """
            SELECT
                o.market_id,
                o.outcome_id,
                o.token_id,
                o.side,
                o.outcome_label
            FROM prediction_gold.dim_outcome o
            WHERE o.platform = 'polymarket'
                AND o.market_id IN {market_ids:Array(String)}
            ORDER BY o.market_id, o.side
        """
        rows = await execute_query(query, {"market_ids": uncached}, client=ch)

        # Group by market_id
        tokens_by_market: dict[str, list[dict[str, str]]] = {}
        for row in rows:
            mid = row.get("market_id", "")
            token_id = row.get("token_id")
            if not token_id:
                continue

            if mid not in tokens_by_market:
                tokens_by_market[mid] = []

            tokens_by_market[mid].append({
                "outcome_id": row.get("outcome_id", ""),
                "token_id": token_id,
                "side": row.get("side", ""),
                "outcome_label": row.get("outcome_label", ""),
            })

        # Build MarketTokens and cache
        for mid, tokens in tokens_by_market.items():
            market_tokens = MarketTokens(market_id=mid, tokens=tokens)

            # Cache (with eviction)
            if len(self._cache) >= self._max_cache_size:
                oldest_key = next(iter(self._cache))
                del self._cache[oldest_key]

            self._cache[mid] = market_tokens
            result[mid] = market_tokens

        return result

    async def get_token_id(
        self,
        market_id: str,
        *,
        outcome: str = "yes",
        client: Client | None = None,
    ) -> str | None:
        """Get a specific token ID for a market outcome.

        Args:
            market_id: Our platform_market_id.
            outcome: Which outcome's token to get ("yes", "no", or outcome_id).
            client: Optional ClickHouse client.

        Returns:
            Token ID string, or None if not found.
        """
        market_tokens = await self.get_tokens(market_id, client=client)
        if not market_tokens:
            return None

        outcome_lower = outcome.lower()
        if outcome_lower == "yes":
            return market_tokens.yes_token_id
        elif outcome_lower == "no":
            return market_tokens.no_token_id
        else:
            # Try to find by outcome_id
            for token in market_tokens.tokens:
                if token.get("outcome_id") == outcome:
                    return token.get("token_id")
            return None

    def get_stats(self) -> dict[str, int | float]:
        """Get cache statistics."""
        total = self._cache_hits + self._cache_misses
        return {
            "cache_size": len(self._cache),
            "cache_hits": self._cache_hits,
            "cache_misses": self._cache_misses,
            "hit_rate": (
                round(self._cache_hits / total * 100, 1) if total > 0 else 0.0
            ),
        }

    def clear_cache(self) -> int:
        """Clear the token cache.

        Returns:
            Number of entries cleared.
        """
        count = len(self._cache)
        self._cache.clear()
        return count


# Singleton instance
_token_resolver: TokenResolver | None = None


def get_token_resolver() -> TokenResolver:
    """Get the global token resolver instance.

    Returns:
        Initialized TokenResolver.
    """
    global _token_resolver
    if _token_resolver is None:
        _token_resolver = TokenResolver()
    return _token_resolver
