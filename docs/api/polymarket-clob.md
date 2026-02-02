# Polymarket CLOB API

- **Base URL:** `https://clob.polymarket.com`
- **Docs:** https://docs.polymarket.com/developers/CLOB/introduction.md
- **Auth:** Two-tier (L1 = EIP-712 wallet signing, L2 = HMAC-SHA256 API credentials)
- **Rate limits:** 9,000 req/10s overall. `/data/trades`: 500/10s.
- **WebSocket:** `wss://ws-subscriptions-clob.polymarket.com/ws/`

---

## Authentication

**Docs:** https://docs.polymarket.com/developers/CLOB/authentication.md

### L1 Authentication (Private Key)

Used to create/derive API credentials. Signs EIP-712 messages.

**Required headers:**
| Header | Description |
|---|---|
| `POLY_ADDRESS` | Signer's Polygon address |
| `POLY_SIGNATURE` | EIP-712 signed message |
| `POLY_TIMESTAMP` | Unix timestamp |
| `POLY_NONCE` | Default 0 |

### L2 Authentication (API Credentials)

Used for trading operations. HMAC-SHA256 signing of `timestamp + method + path` (query params excluded).

**Required headers:**
| Header | Description |
|---|---|
| `POLY_ADDRESS` | Polygon signer address |
| `POLY_SIGNATURE` | HMAC-SHA256 signature |
| `POLY_TIMESTAMP` | Unix timestamp |
| `POLY_API_KEY` | API key value |
| `POLY_PASSPHRASE` | API passphrase value |

### Wallet/Signature Types

| Type | Value | Description |
|---|---|---|
| EOA | 0 | Standard Ethereum wallet |
| POLY_PROXY | 1 | Magic Link / Google login proxy |
| GNOSIS_SAFE | 2 | Multisig proxy (most common for new users) |

### Credential Management

- **Create new:** `POST /auth/api-key` (L1-authenticated)
- **Derive existing:** `GET /auth/derive-api-key` (L1-authenticated)
- Response: `{ "apiKey": "...", "secret": "base64...", "passphrase": "..." }`

---

## GET /data/trades

**Docs:** https://docs.polymarket.com/developers/CLOB/trades/trades.md

Fetch trades from the CLOB. Requires L2 authentication.

### Query Parameters

| Parameter | Type | Description |
|---|---|---|
| `id` | string | Retrieve a specific trade by ID |
| `taker` | string | Filter by taker address |
| `maker` | string | Filter by maker address |
| `market` | string | Filter by condition ID |
| `before` | string | Unix timestamp — trades before this time |
| `after` | string | Unix timestamp — trades after this time |

### Pagination

Cursor-based using `next_cursor` field in response. End sentinel: `LTE=`. No offset limit.
Default page size: 500 trades.

### Response

Returns array of Trade objects:

| Field | Type | Description |
|---|---|---|
| `id` | string | Trade ID |
| `taker_order_id` | string | Taker order ID |
| `market` | string | Condition ID |
| `asset_id` | string | Token ID |
| `side` | string | BUY or SELL |
| `size` | string | Trade size |
| `fee_rate_bps` | string | Fee rate in basis points |
| `price` | string | Trade price |
| `status` | string | Trade status |
| `match_time` | string | Match timestamp |
| `last_update` | string | Last update timestamp |
| `outcome` | string | Outcome name |
| `maker_address` | string | Maker address |
| `owner` | string | Owner address |
| `transaction_hash` | string | On-chain tx hash |
| `bucket_index` | integer | Bucket index |
| `type` | string | Trade type |
| `maker_orders` | array | Nested maker order details |

**MakerOrder fields:** order_id, maker_address, owner, matched_amount, fee_rate_bps, price, asset_id, outcome, side

---

## Other Endpoints (Reference)

| Endpoint | Method | Description |
|---|---|---|
| `/price` | GET | Current token pricing |
| `/book` | GET | Token orderbook data |
| `/midpoint` | GET | Midpoint price |
| `/order` | POST | Place order (L2 auth) |
| `/order` | DELETE | Cancel order (L2 auth) |

---

## Fee Structure

Currently zero fees for both makers and takers across all volume levels.
