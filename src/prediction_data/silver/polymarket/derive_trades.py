"""Transform Bronze OrderFilledEvents into derived Silver trades.

Each OrderFilledEvent has a maker and taker, each providing an asset.
One asset is USDC (asset_id == "0"), the other is a conditional token.
This module resolves the conditional token to a market and side via the
markets reference lookup, then derives trade direction, price, and amounts.
"""

from __future__ import annotations

from typing import Any

from prediction_data.core.logging import get_logger
from prediction_data.silver.polymarket.markets_reference import MarketsReferenceLookup

logger = get_logger(__name__)

# USDC asset ID in Polymarket order fills
_USDC_ASSET_ID = "0"


class TradeDerivationError(Exception):
    """Raised when a trade cannot be derived from an order fill."""


def derive_trade(
    record: dict[str, Any],
    lookup: MarketsReferenceLookup,
) -> dict[str, Any]:
    """Derive a single Silver trade record from a Bronze OrderFilledEvent.

    Args:
        record: Raw Bronze OrderFilledEvent dict.
        lookup: Markets reference lookup for token ID resolution.

    Returns:
        Dict with derived trade fields (not yet enriched with lineage columns).

    Raises:
        TradeDerivationError: If the record cannot be transformed.
    """
    maker_asset = str(record.get("makerAssetId", ""))
    taker_asset = str(record.get("takerAssetId", ""))

    if not maker_asset or not taker_asset:
        raise TradeDerivationError("Missing makerAssetId or takerAssetId")

    # Identify which side provides the conditional token (non-USDC)
    if taker_asset == _USDC_ASSET_ID and maker_asset != _USDC_ASSET_ID:
        # Taker provides USDC, maker provides conditional token
        nonusdc_asset = maker_asset
        usdc_amount_raw = record.get("takerAmountFilled")
        token_amount_raw = record.get("makerAmountFilled")
        # Taker providing USDC = taker is buying the token
        taker_direction = "buy"
        maker_direction = "sell"
    elif maker_asset == _USDC_ASSET_ID and taker_asset != _USDC_ASSET_ID:
        # Maker provides USDC, taker provides conditional token
        nonusdc_asset = taker_asset
        usdc_amount_raw = record.get("makerAmountFilled")
        token_amount_raw = record.get("takerAmountFilled")
        # Taker providing token = taker is selling
        taker_direction = "sell"
        maker_direction = "buy"
    else:
        raise TradeDerivationError(
            f"Cannot identify USDC side: maker={maker_asset}, taker={taker_asset}"
        )

    # Resolve conditional token to market + side
    market_side = lookup.get(nonusdc_asset)
    if market_side is None:
        raise TradeDerivationError(
            f"Market lookup failed for asset_id={nonusdc_asset}"
        )

    # Scale amounts from base units (1e6) to decimal
    try:
        usdc_amount = int(usdc_amount_raw) / 1e6  # type: ignore[arg-type]
        token_amount = int(token_amount_raw) / 1e6  # type: ignore[arg-type]
    except (TypeError, ValueError) as e:
        raise TradeDerivationError(f"Invalid amount fields: {e}") from e

    if token_amount == 0:
        raise TradeDerivationError("Zero token amount — cannot compute price")

    price = usdc_amount / token_amount

    # Build trade ID from transaction hash (or fallback to subgraph id)
    tx_hash = record.get("transactionHash")
    trade_id = tx_hash or record.get("id") or ""

    return {
        "timestamp": record.get("timestamp"),
        "market_id": market_side.market_id,
        "maker": record.get("maker", ""),
        "taker": record.get("taker", ""),
        "nonusdc_side": market_side.side,
        "maker_direction": maker_direction,
        "taker_direction": taker_direction,
        "price": price,
        "usd_amount": usdc_amount,
        "token_amount": token_amount,
        "transaction_hash": tx_hash,
        "trade_id": trade_id,
    }


def derive_trades_batch(
    records: list[dict[str, Any]],
    lookup: MarketsReferenceLookup,
) -> list[dict[str, Any]]:
    """Derive trades from a batch of OrderFilledEvents.

    Records that fail derivation are skipped with a warning log.

    Returns:
        List of successfully derived trade dicts.
    """
    results: list[dict[str, Any]] = []
    skipped = 0
    for rec in records:
        try:
            results.append(derive_trade(rec, lookup))
        except TradeDerivationError:
            skipped += 1
            logger.warning(
                "Skipping order fill — derivation failed",
                record_snippet=str(rec)[:200],
            )
    if skipped:
        logger.info(
            "Trade derivation batch complete",
            derived=len(results),
            skipped=skipped,
        )
    return results
