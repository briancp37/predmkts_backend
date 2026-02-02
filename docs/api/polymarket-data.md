# Polymarket Data API

- **Base URL:** `https://data-api.polymarket.com`
- **Docs:** https://docs.polymarket.com/api-reference/core/get-trades-for-a-user-or-markets
- **Auth:** None documented (public endpoints)
- **Rate limits:** 1,000 req/10s overall. `/trades`: 200/10s.
- **Pagination:** Offset-based with **10,000 record limit** on both `limit` and `offset`.

---

## GET /trades

**Docs:** https://docs.polymarket.com/api-reference/core/get-trades-for-a-user-or-markets

### Query Parameters

| Parameter | Type | Default | Description |
|---|---|---|---|
| `limit` | integer | 100 | Results per request (max: 10,000) |
| `offset` | integer | 0 | Starting position (max: 10,000) |
| `user` | Address | — | Filter by trader wallet address |
| `side` | enum (BUY, SELL) | — | Trade direction |
| `market` | comma-separated Hash64[] | — | Condition IDs (mutually exclusive with eventId) |
| `eventId` | comma-separated integer[] | — | Event IDs (mutually exclusive with market) |
| `takerOnly` | boolean | true | Include taker-side trades only |
| `filterType` | enum (CASH, TOKENS) | — | Asset type filter (requires filterAmount) |
| `filterAmount` | number (min: 0) | — | Threshold value (requires filterType) |

### Response (200 OK)

Returns array of Trade objects:

| Field | Type | Description |
|---|---|---|
| `proxyWallet` | string | Trader proxy wallet address |
| `side` | string | BUY or SELL |
| `asset` | string | Asset identifier |
| `conditionId` | string | Market condition ID |
| `size` | string | Trade size |
| `price` | string | Trade price |
| `timestamp` | integer | Unix milliseconds |
| `transactionHash` | string | On-chain tx hash |
| `title` | string | Market title |
| `slug` | string | Market slug |
| `icon` | string | Market icon URL |
| `eventSlug` | string | Event slug |
| `outcome` | string | Outcome name |
| `outcomeIndex` | integer | Outcome index |
| `name` | string | User display name |
| `pseudonym` | string | User pseudonym |
| `bio` | string | User bio |
| `profileImage` | string | Profile image URL |

### Error Responses

| Status | Description |
|---|---|
| 400 | Bad request |
| 401 | Unauthorized |
| 500 | Server error |

### Important Limitations

The offset limit of 10,000 means you can only access up to `10,000 + limit` records through offset pagination. For high-volume data, this requires filtering by time ranges or using the CLOB API instead.

---

## Other Data API Endpoints

| Endpoint | Method | Description |
|---|---|---|
| `/positions` | GET | User positions |
| `/activity` | GET | User activity logs |

**Health check:** https://docs.polymarket.com/api-reference/data-api-status/data-api-health-check
