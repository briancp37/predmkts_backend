# Polymarket Gamma API

- **Base URL:** `https://gamma-api.polymarket.com`
- **Docs:** https://docs.polymarket.com/developers/gamma-markets-api/overview.md
- **Auth:** None (public API)
- **Rate limits:** 4,000 req/10s overall. `/markets`: 300/10s. `/events`: 500/10s.
- **Pagination:** Offset-based (`limit` + `offset`). Max `limit` per request is **500** (for both `/markets` and `/events`). No hard record limit on total offset (can return 100k+ records across pages).

---

## GET /markets

**Docs:** https://docs.polymarket.com/api-reference/markets/list-markets

### Query Parameters

| Parameter | Type | Description |
|---|---|---|
| `limit` | integer (min: 0, max: 500) | Results per page |
| `offset` | integer (min: 0) | Starting position for pagination |
| `order` | string | Comma-separated fields to order by |
| `ascending` | boolean | Sort direction |
| `id` | array[integer] | Filter by market IDs |
| `slug` | array[string] | Filter by market slugs |
| `clob_token_ids` | array[string] | Filter by CLOB token identifiers |
| `condition_ids` | array[string] | Filter by condition identifiers |
| `question_ids` | array[string] | Filter by question identifiers |
| `market_maker_address` | array[string] | Filter by creator addresses |
| `closed` | boolean | Filter by closed status |
| `tag_id` | integer | Filter by tag ID |
| `related_tags` | boolean | Include related tags |
| `include_tag` | boolean | Include tag data in response |
| `cyom` | boolean | Create-Your-Own-Market filter |
| `uma_resolution_status` | string | UMA resolution status filter |
| `game_id` | string | Sports game identifier |
| `sports_market_types` | array[string] | Sports market type filters |
| `liquidity_num_min` | number | Minimum liquidity threshold |
| `liquidity_num_max` | number | Maximum liquidity threshold |
| `volume_num_min` | number | Minimum volume threshold |
| `volume_num_max` | number | Maximum volume threshold |
| `rewards_min_size` | number | Minimum reward size |
| `start_date_min` | datetime (ISO 8601) | Earliest market start date |
| `start_date_max` | datetime (ISO 8601) | Latest market start date |
| `end_date_min` | datetime (ISO 8601) | Earliest market end date |
| `end_date_max` | datetime (ISO 8601) | Latest market end date |

### Response (200 OK)

Returns JSON array of Market objects. Key fields:

- **Identifiers:** id, question, slug, conditionId, category
- **Pricing:** liquidity, liquidityNum, volume, volumeNum, outcomePrices, bestBid, bestAsk, lastTradePrice, spread
- **Dates:** startDate, endDate, createdAt, updatedAt, closedTime
- **Status:** active, closed, archived, restricted, acceptingOrders
- **Volume metrics:** volume24hr, volume1wk, volume1mo, volume1yr (AMM and CLOB variants)
- **Trading config:** ammType, orderPriceMinTickSize, orderMinSize, makerBaseFee, takerBaseFee
- **Sports:** gameId, teamAID, teamBID, sportsMarketType, line
- **Nested:** events[], categories[], tags[]

### Incremental fetch note

**No `updated_since` filter exists.** Use `start_date_min` to fetch only markets that started after a given date. This misses metadata updates (price, volume, resolution) on older markets.

---

## GET /markets/{id}

**Docs:** https://docs.polymarket.com/api-reference/markets/get-market-by-id

### Path Parameters

| Parameter | Type | Description |
|---|---|---|
| `id` | integer (required) | Market ID |

### Query Parameters

| Parameter | Type | Description |
|---|---|---|
| `include_tag` | boolean | Include tag data |

### Response

Returns a single Market object (same schema as list). 404 if not found.

---

## GET /markets/{slug} (by slug)

**Docs:** https://docs.polymarket.com/api-reference/markets/get-market-by-slug

---

## GET /events

**Docs:** https://docs.polymarket.com/api-reference/events/list-events

### Query Parameters

| Parameter | Type | Description |
|---|---|---|
| `limit` | integer (min: 0, max: 500) | Results per page |
| `offset` | integer (min: 0) | Starting position for pagination |
| `order` | string | Comma-separated fields to order by |
| `ascending` | boolean | Sort direction |
| `id` | array[integer] | Filter by event IDs |
| `slug` | array[string] | Filter by event slugs |
| `tag_id` | integer | Filter by tag ID |
| `tag_slug` | string | Filter by tag slug |
| `exclude_tag_id` | array[integer] | Exclude events with these tags |
| `related_tags` | boolean | Include related tags |
| `active` | boolean | Filter active events only |
| `archived` | boolean | Filter archived events |
| `closed` | boolean | Filter by closed status |
| `featured` | boolean | Featured events only |
| `cyom` | boolean | Create-Your-Own-Market filter |
| `include_chat` | boolean | Include chat data |
| `include_template` | boolean | Include template data |
| `recurrence` | string | Filter by recurrence pattern |
| `liquidity_min` | number | Minimum liquidity threshold |
| `liquidity_max` | number | Maximum liquidity threshold |
| `volume_min` | number | Minimum volume threshold |
| `volume_max` | number | Maximum volume threshold |
| `start_date_min` | datetime (ISO 8601) | Earliest event start date |
| `start_date_max` | datetime (ISO 8601) | Latest event start date |
| `end_date_min` | datetime (ISO 8601) | Earliest event end date |
| `end_date_max` | datetime (ISO 8601) | Latest event end date |

### Response (200 OK)

Returns JSON array of Event objects. Key fields:

- **Core:** id, ticker, slug, title, subtitle, description, resolutionSource
- **Dates:** startDate, endDate, creationDate, closedTime, createdAt, updatedAt
- **Market data:** liquidity, volume, openInterest, volume24hr, volume1wk, volume1mo, volume1yr
- **Status:** active, closed, archived, new, featured, restricted, cyom, commentsEnabled
- **Content:** image, icon, featuredImage, category, subcategory, parentEvent
- **Sports:** score, elapsed, period, live, ended, seriesSlug, eventDate, eventWeek
- **Config:** negRisk, negRiskMarketID, enableOrderBook
- **Nested:** markets[], series[], tags[], categories[], collections[], eventCreators[], templates[], chats[]

---

## GET /events/{id}

**Docs:** https://docs.polymarket.com/api-reference/events/get-event-by-id

### Path Parameters

| Parameter | Type | Description |
|---|---|---|
| `id` | integer (required) | Event ID |

### Query Parameters

| Parameter | Type | Description |
|---|---|---|
| `include_chat` | boolean | Include chat data |
| `include_template` | boolean | Include template data |

### Response

Returns a single Event object (same schema as list). 404 if not found.

---

## GET /events/{slug} (by slug)

**Docs:** https://docs.polymarket.com/api-reference/events/get-event-by-slug

---

## GET /events/{id}/tags

**Docs:** https://docs.polymarket.com/api-reference/events/get-event-tags

---

## Pagination

Offset-based. Example:
```
Page 1: GET /markets?limit=500&offset=0
Page 2: GET /markets?limit=500&offset=500
Page 3: GET /markets?limit=500&offset=1000
```
Continue until fewer results than `limit` are returned.

No documented hard limit on offset for markets/events (unlike Data API which caps at 10,000).
