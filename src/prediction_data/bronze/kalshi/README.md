# Kalshi API Integration

This module handles ingestion of prediction market data from the Kalshi API.

## API Overview

- **Base URL (Production)**: `https://api.elections.kalshi.com/trade-api/v2`
- **Base URL (Demo)**: `https://demo-api.kalshi.co/trade-api/v2`
- **API Version**: v2

## Authentication

Kalshi uses RSA-PSS signature-based authentication. Every request requires three headers:

| Header | Description |
|--------|-------------|
| `KALSHI-ACCESS-KEY` | Your API Key ID |
| `KALSHI-ACCESS-TIMESTAMP` | Request timestamp in milliseconds |
| `KALSHI-ACCESS-SIGNATURE` | Base64-encoded RSA-PSS signature |

### Signature Generation

The signature is computed by:

1. Concatenating: `{timestamp_ms}{HTTP_METHOD}{path_without_query_params}`
2. Signing with RSA-PSS using SHA-256 and PSS padding (salt length = digest length)
3. Base64-encoding the result

Example message to sign for `GET /trade-api/v2/markets?limit=100`:
```
1706467200000GET/trade-api/v2/markets
```

### Required Environment Variables

- `KALSHI_API_KEY_ID`: Your Kalshi API Key ID
- `KALSHI_PRIVATE_KEY_PATH`: Path to your RSA private key PEM file

### Generating API Keys

1. Log in to Kalshi and go to Profile Settings
2. Navigate to the API Keys section
3. Click "Create New API Key"
4. Save the private key immediately (it cannot be retrieved later)

## Endpoints

### Get Trades

Fetches historical trade data from all markets.

**Endpoint**: `GET /markets/trades`

**Query Parameters**:

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `limit` | int | 100 | Results per page (1-1000) |
| `cursor` | string | - | Pagination cursor from previous response |
| `ticker` | string | - | Filter by market ticker |
| `min_ts` | int | - | Filter trades after this Unix timestamp |
| `max_ts` | int | - | Filter trades before this Unix timestamp |

**Response Schema**:

```json
{
  "trades": [
    {
      "trade_id": "string",
      "ticker": "string",
      "count": 123,
      "count_fp": "123.00",
      "yes_price": 55,
      "no_price": 45,
      "yes_price_dollars": "0.5500",
      "no_price_dollars": "0.4500",
      "taker_side": "yes",
      "created_time": "2024-01-15T10:30:00Z"
    }
  ],
  "cursor": "string"
}
```

**Trade Object Fields**:

| Field | Type | Description |
|-------|------|-------------|
| `trade_id` | string | Unique trade identifier |
| `ticker` | string | Market ticker where trade occurred |
| `count` | int | Number of contracts traded |
| `count_fp` | string | Fixed-point contract count (2 decimals) |
| `yes_price` | int | YES contract price in cents (0-100) |
| `no_price` | int | NO contract price in cents (0-100) |
| `yes_price_dollars` | string | YES price in dollars (4 decimals) |
| `no_price_dollars` | string | NO price in dollars (4 decimals) |
| `taker_side` | string | "yes" or "no" - which side the taker bought |
| `created_time` | string | ISO 8601 timestamp of trade execution |

### Get Markets

Fetches market metadata and current state.

**Endpoint**: `GET /markets`

**Query Parameters**:

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `limit` | int | 100 | Results per page (1-1000) |
| `cursor` | string | - | Pagination cursor |
| `event_ticker` | string | - | Filter by event (up to 10 comma-separated) |
| `series_ticker` | string | - | Filter by series |
| `status` | string | - | Market status: `unopened`, `open`, `paused`, `closed`, `settled` |
| `tickers` | string | - | Comma-separated market tickers |
| `min_created_ts` | int | - | Markets created after this timestamp |
| `max_created_ts` | int | - | Markets created before this timestamp |
| `min_updated_ts` | int | - | Markets updated after this timestamp |
| `min_close_ts` | int | - | Markets closing after this timestamp |
| `max_close_ts` | int | - | Markets closing before this timestamp |
| `min_settled_ts` | int | - | Markets settled after this timestamp |
| `max_settled_ts` | int | - | Markets settled before this timestamp |
| `mve_filter` | string | - | Multivariate filter: `only` or `exclude` |

**Response Schema**:

```json
{
  "markets": [
    {
      "ticker": "string",
      "event_ticker": "string",
      "market_type": "binary",
      "yes_sub_title": "string",
      "no_sub_title": "string",
      "status": "open",
      "result": "string",
      "created_time": "2024-01-15T10:00:00Z",
      "updated_time": "2024-01-15T12:00:00Z",
      "open_time": "2024-01-15T10:00:00Z",
      "close_time": "2024-02-15T10:00:00Z",
      "latest_expiration_time": "2024-02-15T10:00:00Z",
      "yes_bid_dollars": "0.4500",
      "yes_ask_dollars": "0.5500",
      "no_bid_dollars": "0.4500",
      "no_ask_dollars": "0.5500",
      "last_price_dollars": "0.5000",
      "volume_fp": "12345.00",
      "volume_24h_fp": "1234.00",
      "liquidity_dollars": "5000.00",
      "open_interest_fp": "6789.00",
      "settlement_value_dollars": "1.0000",
      "settlement_ts": 1706467200,
      "rules_primary": "string",
      "rules_secondary": "string"
    }
  ],
  "cursor": "string"
}
```

**Market Object Fields**:

| Field | Type | Description |
|-------|------|-------------|
| `ticker` | string | Unique market identifier |
| `event_ticker` | string | Parent event identifier |
| `market_type` | string | "binary" or "scalar" |
| `yes_sub_title` | string | YES outcome description |
| `no_sub_title` | string | NO outcome description |
| `status` | string | Market status |
| `result` | string | Settlement result (if settled) |
| `created_time` | string | ISO 8601 creation timestamp |
| `updated_time` | string | ISO 8601 last update timestamp |
| `open_time` | string | When trading opened |
| `close_time` | string | When trading closes |
| `yes_bid_dollars` | string | Best YES bid price |
| `yes_ask_dollars` | string | Best YES ask price |
| `no_bid_dollars` | string | Best NO bid price |
| `no_ask_dollars` | string | Best NO ask price |
| `last_price_dollars` | string | Last traded price |
| `volume_fp` | string | Total volume (fixed-point) |
| `volume_24h_fp` | string | 24-hour volume (fixed-point) |
| `liquidity_dollars` | string | Market liquidity |
| `open_interest_fp` | string | Open interest (fixed-point) |

## Pagination

All list endpoints use cursor-based pagination:

1. Make initial request without `cursor` parameter
2. Check response for `cursor` field
3. If `cursor` is non-empty, pass it in the next request
4. If `cursor` is empty, you've reached the end

Example pagination flow:
```python
cursor = None
while True:
    params = {"limit": 1000}
    if cursor:
        params["cursor"] = cursor
    response = client.get("/markets/trades", params=params)
    data = response.json()

    yield from data["trades"]

    cursor = data.get("cursor")
    if not cursor:
        break
```

## Rate Limits

Rate limits vary by account tier:

| Tier | Read Ops/sec | Write Ops/sec | Qualification |
|------|--------------|---------------|---------------|
| Basic | 20 | 10 | Account signup |
| Advanced | 30 | 30 | Application form |
| Premier | 100 | 100 | 3.75% monthly volume + tech competency |
| Prime | 400 | 400 | 7.5% monthly volume + tech competency |

### Best Practices

- Use exponential backoff when receiving 429 responses
- Cache frequently accessed data
- Use the maximum `limit` (1000) to reduce API calls
- Check your current limits via `GET /account/limits`

## Error Handling

Common HTTP status codes:

| Status | Meaning |
|--------|---------|
| 200 | Success |
| 400 | Bad request (invalid parameters) |
| 401 | Unauthorized (invalid/expired signature) |
| 403 | Forbidden (insufficient permissions) |
| 404 | Resource not found |
| 429 | Rate limit exceeded |
| 500 | Internal server error |

Error responses include a JSON body with error details.

## References

- [Kalshi API Documentation](https://docs.kalshi.com/welcome)
- [API Keys Guide](https://docs.kalshi.com/getting_started/api_keys)
- [Rate Limits](https://docs.kalshi.com/getting_started/rate_limits)
- [Get Trades Endpoint](https://docs.kalshi.com/api-reference/market/get-trades)
- [Get Markets Endpoint](https://docs.kalshi.com/api-reference/market/get-markets)
- [Python Starter Code](https://github.com/Kalshi/kalshi-starter-code-python)
