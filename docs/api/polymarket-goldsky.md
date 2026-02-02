# Polymarket Goldsky Subgraph API (OrderFilledEvents)

- **Endpoint:** `https://api.goldsky.com/api/public/project_cl6mb8i9h0003e201j6li0diw/subgraphs/orderbook-subgraph/prod/gn`
- **Docs:** https://docs.polymarket.com/developers/subgraph/overview.md
- **Auth:** None (public subgraph)
- **Rate limits:** No documented hard limit. Use configurable `page_delay` between requests.
- **Query language:** GraphQL
- **Source code:** https://github.com/Polymarket/polymarket-subgraph

---

## OrderFilledEvent Entity

The primary entity used for ingestion.

### Query Pattern

```graphql
{
  orderFilledEvents(
    first: 1000
    orderBy: id
    where: {
      id_gt: $cursor
      timestamp_gte: $start_timestamp
      timestamp_lte: $end_timestamp
    }
  ) {
    id
    transactionHash
    orderHash
    timestamp
    maker
    taker
    makerAssetId
    takerAssetId
    makerAmountFilled
    takerAmountFilled
    fee
  }
}
```

### Pagination

Cursor-based using `id_gt` (standard subgraph pattern):
- `first: 1000` — page size
- `orderBy: id` — deterministic ordering
- `where: { id_gt: $cursor }` — cursor from last record's `id`

Continue until fewer results than `first` are returned.

### Filtering

- `timestamp_gte` / `timestamp_lte` — Unix epoch seconds, for day boundaries
- `id_gt` — cursor for pagination

### Schema

| Field | Type | Notes |
|---|---|---|
| `id` | string | Subgraph entity ID |
| `transactionHash` | string | On-chain tx hash |
| `orderHash` | string | Order identifier |
| `timestamp` | int | Unix epoch seconds |
| `maker` | string | Maker address |
| `taker` | string | Taker address |
| `makerAssetId` | string | Maker asset token ID |
| `takerAssetId` | string | Taker asset token ID |
| `makerAmountFilled` | int | Base units (divide by 1e6 for USDC) |
| `takerAmountFilled` | int | Base units (divide by 1e6 for USDC) |
| `fee` | int | Fee in base units |

### Historical Data Notes

Parquet-backfilled records are missing `orderHash`, `fee`, and `id` (set to null). Amounts in parquet source are scaled floats (e.g., 4.45 USDC) multiplied by 1e6 to match subgraph base units.

---

## Other Available Entities

The subgraph also indexes other on-chain data (positions, conditions, etc.). See the `schema.graphql` in the GitHub repo for the full entity list.
