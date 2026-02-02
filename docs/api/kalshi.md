# Kalshi API

- **Base URL:** `https://api.elections.kalshi.com/trade-api/v2` (covers ALL markets, not just elections)
- **Docs:** https://docs.kalshi.com
- **Docs index:** https://docs.kalshi.com/llms.txt
- **OpenAPI spec:** https://docs.kalshi.com/openapi.yaml
- **Auth:** RSA-PSS signature (SHA-256) over `timestamp + method + path` (query params excluded)
- **Pagination:** Cursor-based (`cursor` field in response; empty = no more pages)

---

## Authentication

**Docs:** https://docs.kalshi.com/getting_started/api_keys

### Required Headers

| Header | Description |
|---|---|
| `KALSHI-ACCESS-KEY` | API Key ID |
| `KALSHI-ACCESS-TIMESTAMP` | Request timestamp in milliseconds |
| `KALSHI-ACCESS-SIGNATURE` | Base64-encoded RSA-PSS SHA-256 signature |

### Signature Generation

1. Concatenate: `timestamp_ms + method + path` (strip query params from path)
2. Sign with RSA-PSS using SHA-256
3. Base64-encode the result

### Key Management

- Generate keys at https://kalshi.com/account/profile
- Private key is RSA format, never stored server-side — download immediately
- Key ID is the public identifier

---

## Rate Limits

**Docs:** https://docs.kalshi.com/getting_started/rate_limits

| Tier | Read | Write | Qualification |
|---|---|---|---|
| Basic | 20/sec | 10/sec | Signup |
| Advanced | 30/sec | 30/sec | Application form |
| Premier | 100/sec | 100/sec | 3.75% monthly exchange volume + tech competency |
| Prime | 400/sec | 400/sec | 7.5% monthly exchange volume + tech competency |

Write limits apply only to order-related operations. For batch APIs, each item = 1 transaction (except `BatchCancelOrders` where each cancel = 0.2 transactions).

Check your limits: `GET /trade-api/v2/account/limits`

---

## GET /markets/trades

**Docs:** https://docs.kalshi.com/api-reference/market/get-trades

### Query Parameters

| Parameter | Type | Default | Max | Description |
|---|---|---|---|---|
| `limit` | integer | 100 | 1000 | Results per page |
| `cursor` | string | — | — | Pagination cursor from previous response |
| `ticker` | string | — | — | Filter by market ticker |
| `min_ts` | integer | — | — | Unix timestamp — trades after this time |
| `max_ts` | integer | — | — | Unix timestamp — trades before this time |

### Response

| Field | Type | Description |
|---|---|---|
| `trades` | array[Trade] | Trade objects |
| `cursor` | string | Next page token (empty = done) |

### Trade Object

| Field | Type | Description |
|---|---|---|
| `trade_id` | string | Unique trade ID |
| `ticker` | string | Market ticker |
| `count` | integer | Contract quantity (deprecated int) |
| `count_fp` | string | Contract quantity (fixed-point, 2 decimals) |
| `yes_price` | integer | Yes price in cents |
| `no_price` | integer | No price in cents |
| `yes_price_dollars` | string | Yes price (4 decimal places) |
| `no_price_dollars` | string | No price (4 decimal places) |
| `taker_side` | enum | `"yes"` or `"no"` |
| `created_time` | string | ISO 8601 execution timestamp |
| `price` | number | **Deprecated** |

---

## GET /markets

**Docs:** https://docs.kalshi.com/api-reference/market/get-markets

### Query Parameters

| Parameter | Type | Default | Max | Description |
|---|---|---|---|---|
| `limit` | integer | 100 | 1000 | Results per page |
| `cursor` | string | — | — | Pagination cursor |
| `event_ticker` | string | — | — | Filter by event ticker (comma-separated, max 10) |
| `series_ticker` | string | — | — | Filter by series ticker |
| `tickers` | string | — | — | Comma-separated market tickers |
| `status` | enum | — | — | `unopened`, `open`, `paused`, `closed`, `settled` |
| `min_created_ts` | integer | — | — | Markets created after this Unix timestamp |
| `max_created_ts` | integer | — | — | Markets created before this Unix timestamp |
| `min_updated_ts` | integer | — | — | Markets updated after this Unix timestamp (**incompatible with other filters except `mve_filter`**) |
| `min_close_ts` | integer | — | — | Markets closing after this Unix timestamp |
| `max_close_ts` | integer | — | — | Markets closing before this Unix timestamp |
| `min_settled_ts` | integer | — | — | Markets settled after this Unix timestamp |
| `max_settled_ts` | integer | — | — | Markets settled before this Unix timestamp |
| `mve_filter` | enum | — | — | `only` (multivariate only) or `exclude` (exclude multivariate) |

### Incremental fetch note

**`min_updated_ts` enables true incremental ingestion** — fetch only markets modified since last run. This is incompatible with all other filters except `mve_filter=exclude`.

### Response

| Field | Type | Description |
|---|---|---|
| `markets` | array[Market] | Market objects |
| `cursor` | string | Next page token |

### Market Object (key fields)

| Field | Type | Description |
|---|---|---|
| `ticker` | string | Market ticker |
| `event_ticker` | string | Parent event ticker |
| `market_type` | enum | `binary` or `scalar` |
| `status` | string | Lifecycle state |
| `yes_bid_dollars` | FixedPointDollars | Highest YES buy offer |
| `yes_ask_dollars` | FixedPointDollars | Lowest YES sell offer |
| `no_bid_dollars` | FixedPointDollars | Highest NO buy offer |
| `no_ask_dollars` | FixedPointDollars | Lowest NO sell offer |
| `last_price_dollars` | FixedPointDollars | Last traded YES price |
| `volume_fp` | FixedPointCount | Total volume (contracts) |
| `volume_24h_fp` | FixedPointCount | 24h volume |
| `open_interest_fp` | FixedPointCount | Gross open contracts |
| `liquidity_dollars` | FixedPointDollars | Current offer value |
| `notional_value_dollars` | FixedPointDollars | Settlement value per contract |
| `created_time` | datetime | Creation timestamp |
| `updated_time` | datetime | Last stats update |
| `open_time` | datetime | Trading opens |
| `close_time` | datetime | Trading closes |
| `expected_expiration_time` | datetime (nullable) | Anticipated resolution |
| `latest_expiration_time` | datetime | Final possible expiration |
| `settlement_ts` | datetime (nullable) | Settlement timestamp |
| `settlement_value_dollars` | FixedPointDollars (nullable) | YES contract payout |
| `result` | string | Resolution: `yes`, `no`, `scalar`, or empty |
| `rules_primary` | string | Market terms |
| `can_close_early` | boolean | Early closure eligible |

**FixedPointDollars:** String with 4 decimals (e.g., `"0.5600"`)
**FixedPointCount:** String with 2 decimals (e.g., `"10.00"`)

---

## GET /markets/{ticker}

**Docs:** https://docs.kalshi.com/api-reference/market/get-market

### Path Parameters

| Parameter | Type | Description |
|---|---|---|
| `ticker` | string (required) | Market ticker |

### Response

Returns `{ "market": <Market object> }`. Same schema as list endpoint. 404 if not found.

---

## GET /events

**Docs:** https://docs.kalshi.com/api-reference/events/get-events

Retrieves all events excluding multivariate ones. Use `GET /events/multivariate` for those.

### Query Parameters

| Parameter | Type | Default | Max | Description |
|---|---|---|---|---|
| `limit` | integer | 200 | 200 | Results per page |
| `cursor` | string | — | — | Pagination cursor |
| `status` | enum | — | — | `open`, `closed`, `settled` |
| `series_ticker` | string | — | — | Filter by series ticker |
| `with_nested_markets` | boolean | false | — | Include market objects in events |
| `with_milestones` | boolean | false | — | Include milestone objects |
| `min_close_ts` | integer | — | — | Events with markets closing after this Unix timestamp |

### Response

| Field | Type | Description |
|---|---|---|
| `events` | array[EventData] | Event objects |
| `milestones` | array (optional) | Milestone objects |
| `cursor` | string | Next page token |

### EventData Object

| Field | Type | Description |
|---|---|---|
| `event_ticker` | string | Event ticker |
| `series_ticker` | string | Parent series ticker |
| `title` | string | Event title |
| `sub_title` | string | Short title |
| `collateral_return_type` | string | Settlement mechanism (e.g., `binary`) |
| `mutually_exclusive` | boolean | Only one market can resolve YES |
| `category` | string | Classification (deprecated) |
| `strike_date` | datetime (nullable) | Date the event references |
| `strike_period` | string (nullable) | Time period (week, month, etc.) |
| `markets` | array (nullable) | Markets (only with `with_nested_markets=true`) |
| `available_on_brokers` | boolean | Broker availability |
| `product_metadata` | object (nullable) | Additional metadata |

---

## GET /events/{event_ticker}

**Docs:** https://docs.kalshi.com/api-reference/events/get-event

### Path Parameters

| Parameter | Type | Description |
|---|---|---|
| `event_ticker` | string (required) | Event ticker |

### Query Parameters

| Parameter | Type | Default | Description |
|---|---|---|---|
| `with_nested_markets` | boolean | false | Include markets in event object |

### Response

Returns `{ "event": <EventData>, "markets": [<Market>...] }`. 404 if not found.

---

## GET /series/{series_ticker}

**Docs:** https://docs.kalshi.com/api-reference/market/get-series

### Path Parameters

| Parameter | Type | Description |
|---|---|---|
| `series_ticker` | string (required) | Series ticker |

### Query Parameters

| Parameter | Type | Default | Description |
|---|---|---|---|
| `include_volume` | boolean | false | Include total volume |

### Response — Series Object

| Field | Type | Description |
|---|---|---|
| `ticker` | string | Series ticker |
| `frequency` | string | Occurrence (daily, weekly, one-off, etc.) |
| `title` | string | Series title |
| `category` | string | Category |
| `tags` | array[string] | Subject tags |
| `settlement_sources` | array | Official resolution sources |
| `contract_url` | string | Link to original filing |
| `contract_terms_url` | string | Current contract terms |
| `fee_type` | enum | `quadratic`, `quadratic_with_maker_fees`, `flat` |
| `fee_multiplier` | number | Fee calculation multiplier |
| `volume` | integer | Total contracts (when `include_volume=true`) |
| `volume_fp` | string | Volume as fixed-point string |
