# Polymarket API Documentation

This document captures the research findings for integrating with Polymarket's APIs for Bronze layer data ingestion.

## API Architecture Overview

Polymarket provides multiple API services:

| Service | Base URL | Purpose |
|---------|----------|---------|
| **Gamma API** | `https://gamma-api.polymarket.com` | Market discovery, metadata, indexed on-chain data |
| **Data API** | `https://data-api.polymarket.com` | User positions, historical trades |
| **CLOB API** | `https://clob.polymarket.com` | Order management, pricing, order books |

For Bronze layer ingestion, we primarily use:
- **Gamma API** for markets data
- **Data API** for trades data

## Authentication

### Gamma API
- **No authentication required** - Public read-only access
- Useful for non-profit research, trading interfaces, and automated systems

### Data API (Trades)
- **No authentication required** for the `/trades` endpoint
- The security specification is empty, allowing public access

### CLOB API
- Requires L2 Header authentication for user-specific endpoints
- Not needed for our Bronze layer ingestion use case

## Markets Endpoint

### Endpoint
```
GET https://gamma-api.polymarket.com/markets
```

### Query Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `limit` | integer (min: 0) | Results per page |
| `offset` | integer (min: 0) | Starting position for pagination |
| `order` | string | Comma-separated list of fields to order by |
| `ascending` | boolean | Sort direction |
| `id` | array[integer] | Filter by market IDs |
| `slug` | array[string] | Filter by market slugs |
| `clob_token_ids` | array[string] | Filter by CLOB token identifiers |
| `condition_ids` | array[string] | Filter by condition identifiers |
| `closed` | boolean | Filter by closed status |
| `tag_id` | integer | Filter by tag ID |
| `liquidity_num_min` | number | Minimum liquidity filter |
| `liquidity_num_max` | number | Maximum liquidity filter |
| `volume_num_min` | number | Minimum volume filter |
| `volume_num_max` | number | Maximum volume filter |
| `start_date_min` | datetime | Start date range minimum |
| `start_date_max` | datetime | Start date range maximum |
| `end_date_min` | datetime | End date range minimum |
| `end_date_max` | datetime | End date range maximum |

### Response Schema
Returns a JSON array of Market objects containing:
- Market identifiers (id, slug, condition_id, clob_token_ids)
- Pricing data (best_bid, best_ask, last_trade_price)
- Volume and liquidity metrics
- Market metadata (title, description, image, icon)
- Event association
- Tags and categories
- Resolution status

### Pagination
**Offset-based pagination** using `limit` and `offset` parameters.

Example pagination sequence:
```
Page 1: GET /markets?limit=500&offset=0
Page 2: GET /markets?limit=500&offset=500
Page 3: GET /markets?limit=500&offset=1000
```

Continue until fewer results than `limit` are returned.

## Trades Endpoint

### Endpoint
```
GET https://data-api.polymarket.com/trades
```

### Query Parameters

| Parameter | Type | Description | Default |
|-----------|------|-------------|---------|
| `limit` | integer (0-10000) | Results per page | 100 |
| `offset` | integer (0-10000) | Starting position for pagination | 0 |
| `market` | string | Comma-separated condition IDs | - |
| `eventId` | string | Comma-separated event IDs | - |
| `user` | string | User's wallet address | - |
| `side` | string | BUY or SELL filter | - |
| `takerOnly` | boolean | Filter to taker-only trades | true |
| `filterType` | string | CASH or TOKENS (use with filterAmount) | - |
| `filterAmount` | number | Amount threshold (use with filterType) | - |

**Note:** `market` and `eventId` are mutually exclusive parameters.

### Response Schema
Returns a JSON array of Trade objects:
```json
{
  "side": "BUY|SELL",
  "asset": "string",
  "conditionId": "string",
  "size": "string",
  "price": "string",
  "timestamp": "string (ISO 8601)",
  "transactionHash": "string",
  "title": "string",
  "slug": "string",
  "icon": "string",
  "eventSlug": "string",
  "outcome": "string",
  "outcomeIndex": "integer",
  "proxyWallet": "string",
  "pseudonym": "string",
  "bio": "string",
  "profileImage": "string",
  "profileImageOptimized": "string"
}
```

### Pagination
**Offset-based pagination** using `limit` and `offset` parameters.
- Maximum limit: 10,000
- Maximum offset: 10,000

**Important:** The offset limit of 10,000 means we can only access up to 10,000 + limit records through offset pagination. For high-volume days, this may require filtering by time ranges.

### Error Responses
| Status | Description |
|--------|-------------|
| 400 | Bad Request - Invalid parameters |
| 401 | Unauthorized |
| 500 | Server Error |

## Rate Limits

**Not explicitly documented.** Recommended defensive assumptions:
- Implement exponential backoff on 429 responses
- Use reasonable request intervals (100-500ms between requests)
- Monitor for rate limit headers in responses

## API Quirks and Defensive Assumptions

### Markets API
1. **Offset pagination limits**: Large datasets may hit practical limits
2. **Empty response**: Indicates end of data (no explicit "has_more" flag)
3. **Ordering**: Use `order=id&ascending=false` for consistent pagination
4. **Closed markets**: Include `closed=true` to get all markets including resolved ones

### Trades API
1. **Offset limit of 10,000**: Cannot paginate beyond offset=10,000
   - Mitigation: Filter by time ranges or markets to reduce result sets
2. **No filtering by date**: Trades endpoint lacks direct date filtering
   - Mitigation: Fetch all trades and filter client-side, or use event/market filtering
3. **takerOnly default**: Defaults to true, set explicitly if you need all trades
4. **Size/price as strings**: Numeric values returned as strings for precision

### General Recommendations
1. Always log pagination progress (current offset, records fetched)
2. Implement retry logic with exponential backoff
3. Store raw API responses with minimal transformation (Bronze layer principle)
4. Track cursor/offset state for resumable ingestion
5. Validate response structure before processing

## Ingestion Strategy

### Markets Ingestion
For a daily snapshot of all markets:
```python
# Pseudocode
offset = 0
limit = 500
all_markets = []

while True:
    response = GET /markets?limit={limit}&offset={offset}&closed=true
    markets = response.json()

    if not markets:
        break

    all_markets.extend(markets)
    offset += limit

# Write to JSONL and upload to S3
```

### Trades Ingestion
For daily trades, we face the 10,000 offset limit. Strategy options:

**Option A: Filter by markets**
- First fetch all market condition_ids
- Then fetch trades for each market separately
- Allows complete coverage but requires many requests

**Option B: Time-based filtering** (if available)
- Filter trades by timestamp ranges
- More efficient but requires timestamp parameters

**Option C: Accept limitation**
- For most days, 10,000 trades may be sufficient
- Monitor and alert if hitting the limit

## References

- [Polymarket Documentation](https://docs.polymarket.com/)
- [Endpoints Reference](https://docs.polymarket.com/quickstart/reference/endpoints)
- [Gamma Markets API Overview](https://docs.polymarket.com/developers/gamma-markets-api/overview)
- [Get Markets](https://docs.polymarket.com/developers/gamma-markets-api/get-markets)
- [Trades Endpoint](https://docs.polymarket.com/api-reference/core/get-trades-for-a-user-or-markets)
