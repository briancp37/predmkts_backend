# Release 05: Event Detail Page

## Overview

Build a comprehensive event detail page replicating core Polymarket functionality. This release adds event/market detail views with outcome display, trading UI (dummy buttons initially), price charts, activity feeds, and related markets discovery. The goal is a pixel-approximate clone of Polymarket's event page optimized for our data pipeline.

**Architecture Decision:** This release uses a **Polymarket API Proxy** pattern - our FastAPI backend proxies Polymarket's public APIs (CLOB, Data API) with caching and rate limiting. This enables real-time data without building complex pipelines, while keeping API keys server-side and avoiding CORS issues.

## Goals

1. **Polymarket Proxy Layer** - Backend proxy for timeseries, order book, top holders, trades
2. **Event Detail Page** - Full-featured event page with market outcomes, probabilities, and metadata
3. **Trading Panel UI** - Buy/Sell interface with outcome selection (dummy buttons, no real trading)
4. **Price Visualization** - Historical price charts and order book display (via proxy)
5. **Activity Feed** - Comments placeholder, top holders, and recent activity tabs
6. **Related Markets** - Sidebar with related/similar markets discovery
7. **Responsive Design** - Mobile-first responsive layout matching Polymarket UX

## Reference: Polymarket Event Page Analysis

### Page Structure (from https://polymarket.com/event/tesla-and-spacex-merger-officially-announced-by-june-30)

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│  HEADER NAVIGATION                                                               │
│  Browse: New | Trending | Popular | Liquid | Ending Soon | Competitive          │
│  Categories: Politics | Crypto | Sports | Pop Culture | Tech | AI               │
├─────────────────────────────────────────────────────────────────────────────────┤
│                                                                                  │
│  ┌──────────────────────────────────────────┬──────────────────────────────────┐│
│  │  MAIN CONTENT                            │  SIDEBAR                          ││
│  │                                          │                                   ││
│  │  ┌────────────────────────────────────┐  │  ┌─────────────────────────────┐ ││
│  │  │ EVENT HEADER                       │  │  │ TRADING PANEL               │ ││
│  │  │ - Title + Category Tags            │  │  │ - Outcome Selection         │ ││
│  │  │ - Probability: "12% chance"        │  │  │ - Yes (12¢) / No (88¢)      │ ││
│  │  │ - Volume: $66,109                  │  │  │ - Amount Input              │ ││
│  │  │ - End Date: Jun 30, 2026           │  │  │ - Buy/Sell Buttons          │ ││
│  │  └────────────────────────────────────┘  │  │ - Potential Return Display  │ ││
│  │                                          │  └─────────────────────────────┘ ││
│  │  ┌────────────────────────────────────┐  │                                   ││
│  │  │ OUTCOME CARDS (if multi-outcome)   │  │  ┌─────────────────────────────┐ ││
│  │  │ - Yes: 12% (↑2.3%)                 │  │  │ MARKET DETAILS              │ ││
│  │  │ - No: 88% (↓2.3%)                  │  │  │ - Volume: $66,109           │ ││
│  │  └────────────────────────────────────┘  │  │ - End Date: Jun 30, 2026    │ ││
│  │                                          │  │ - Created: Jan 29, 2026     │ ││
│  │  ┌────────────────────────────────────┐  │  │ - Resolver: 0x65070...      │ ││
│  │  │ PRICE CHART                        │  │  │ - Market ID: 192962         │ ││
│  │  │ - Time range selector              │  │  └─────────────────────────────┘ ││
│  │  │ - Candlestick/Line chart           │  │                                   ││
│  │  │ - Volume bars overlay              │  │  ┌─────────────────────────────┐ ││
│  │  └────────────────────────────────────┘  │  │ RELATED MARKETS             │ ││
│  │                                          │  │ - Tesla/xAI merger (11%)    │ ││
│  │  ┌────────────────────────────────────┐  │  │ - SpaceX IPO (6%)           │ ││
│  │  │ ORDER BOOK                         │  │  │ - ...more                   │ ││
│  │  │ - Bid/Ask depth visualization      │  │  └─────────────────────────────┘ ││
│  │  └────────────────────────────────────┘  │                                   ││
│  │                                          │                                   ││
│  │  ┌────────────────────────────────────┐  │                                   ││
│  │  │ RESOLUTION RULES                   │  │                                   ││
│  │  │ - Detailed resolution criteria     │  │                                   ││
│  │  │ - Primary sources                  │  │                                   ││
│  │  │ - Propose Resolution button        │  │                                   ││
│  │  └────────────────────────────────────┘  │                                   ││
│  │                                          │                                   ││
│  │  ┌────────────────────────────────────┐  │                                   ││
│  │  │ ACTIVITY TABS                      │  │                                   ││
│  │  │ [Comments] [Top Holders] [Activity]│  │                                   ││
│  │  │ - Comment list with post input     │  │                                   ││
│  │  │ - Top holder addresses + positions │  │                                   ││
│  │  │ - Recent trades activity feed      │  │                                   ││
│  │  └────────────────────────────────────┘  │                                   ││
│  └──────────────────────────────────────────┴──────────────────────────────────┘│
└─────────────────────────────────────────────────────────────────────────────────┘
```

### Key Data Points Displayed

| Data | Source | Notes |
|------|--------|-------|
| Event Title | dim_event (ClickHouse) | title field |
| Probability | Polymarket CLOB proxy | Real-time price |
| Volume | Polymarket CLOB proxy | 24h volume |
| End Date | dim_market (ClickHouse) | end_date_iso |
| Category Tags | dim_event (ClickHouse) | category field |
| Resolution Rules | dim_event (ClickHouse) | description field |
| Outcome Prices | Polymarket CLOB proxy | Real-time Yes/No prices |
| Price History | Polymarket timeseries proxy | `/prices-history` endpoint |
| Order Book | Polymarket CLOB proxy | `/book` endpoint |
| Top Holders | Polymarket Data API proxy | `/top-holders` endpoint |
| Recent Activity | Polymarket Data API proxy | `/trades` endpoint |
| Related Markets | dim_event (ClickHouse) | Same category query |

### Interactive Elements

1. **Trading Panel**
   - Outcome toggle (Yes/No or multi-outcome selection)
   - Buy/Sell mode toggle
   - Amount input with validation
   - Shares display (amount / price)
   - Potential return calculation
   - Submit button (dummy - shows toast)

2. **Price Chart**
   - Time range: 1H, 6H, 1D, 1W, 1M, ALL
   - Chart type: Line (default), Candlestick
   - Hover tooltip with OHLC data

3. **Activity Tabs**
   - Comments (placeholder/coming soon)
   - Top Holders (wallet addresses, position size)
   - Activity (recent trades feed)

4. **Related Markets**
   - Click to navigate to another event
   - Shows probability and 24h change

## Architecture

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                           NEXT.JS FRONTEND                                       │
│                                                                                  │
│  /event/[slug]/page.tsx                                                         │
│  ├── EventHeader (title, probability, volume, dates)                            │
│  ├── OutcomeCards (Yes/No probability display)                                  │
│  ├── TradingPanel (sidebar, dummy buttons)                                      │
│  ├── PriceChart (recharts, time-series)                                         │
│  ├── OrderBook (depth visualization)                                            │
│  ├── ResolutionRules (description, sources)                                     │
│  ├── ActivityTabs (Comments, TopHolders, Activity)                              │
│  ├── MarketDetails (volume, dates, IDs)                                         │
│  └── RelatedMarkets (similar events sidebar)                                    │
│                                                                                  │
│  React Query Hooks:                                                              │
│  ├── useEvent(slug) ─────────────────► GET /api/v1/events/{slug}               │
│  ├── useTimeseries(tokenId) ─────────► GET /api/v1/proxy/markets/.../timeseries│
│  ├── useOrderbook(tokenId) ──────────► GET /api/v1/proxy/markets/.../orderbook │
│  ├── useTopHolders(tokenId) ─────────► GET /api/v1/proxy/markets/.../top-holders│
│  ├── useMarketTrades(tokenId) ───────► GET /api/v1/proxy/markets/.../trades    │
│  └── useRelatedEvents(eventId) ──────► GET /api/v1/events/{id}/related         │
│                                                                                  │
└─────────────────────────────────────────────────────────────────────────────────┘
                                         │
                              JSON via /api/v1/*
                                         ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│                           FASTAPI BACKEND                                        │
│                                                                                  │
│  ┌───────────────────────────────────────────────────────────────────────────┐  │
│  │  POLYMARKET PROXY LAYER (Sprint 00)                                       │  │
│  │                                                                           │  │
│  │  GET /api/v1/proxy/markets/{token_id}/timeseries                          │  │
│  │       └──► https://clob.polymarket.com/prices-history                     │  │
│  │                                                                           │  │
│  │  GET /api/v1/proxy/markets/{token_id}/orderbook                           │  │
│  │       └──► https://clob.polymarket.com/book                               │  │
│  │                                                                           │  │
│  │  GET /api/v1/proxy/markets/{token_id}/top-holders                         │  │
│  │       └──► https://data-api.polymarket.com/top-holders                    │  │
│  │                                                                           │  │
│  │  GET /api/v1/proxy/markets/{token_id}/trades                              │  │
│  │       └──► https://data-api.polymarket.com/trades                         │  │
│  │                                                                           │  │
│  │  Features: Caching (Redis/in-memory), Rate limiting, Error handling       │  │
│  └───────────────────────────────────────────────────────────────────────────┘  │
│                                                                                  │
│  Internal Endpoints (ClickHouse):                                                │
│  ├── GET /api/v1/events/{slug}         - Event + markets from dim_event/market │
│  └── GET /api/v1/events/{id}/related   - Related events by category            │
│                                                                                  │
└─────────────────────────────────────────────────────────────────────────────────┘
                    │                                    │
                    ▼                                    ▼
        ┌───────────────────────┐           ┌───────────────────────┐
        │     ClickHouse        │           │   Polymarket APIs     │
        │  (our data pipeline)  │           │  (real-time data)     │
        │                       │           │                       │
        │  - dim_event          │           │  - CLOB API           │
        │  - dim_market         │           │  - Data API           │
        │  - dim_outcome        │           │  - Gamma API          │
        └───────────────────────┘           └───────────────────────┘
```

## Sprints

| Sprint | Name | Focus | Dependencies |
|--------|------|-------|--------------|
| 00 | polymarket_proxy_layer | Backend proxy for Polymarket APIs | None (first) |
| 01 | event_page_foundation | Routing, page layout, event data fetching | 00 |
| 02 | market_display_components | Outcome cards, probability display, header | 01 |
| 03 | trading_panel_ui | Trade form, outcome selection, dummy buttons | 01 |
| 04 | data_visualization | Price chart, order book display | 00, 01 |
| 05 | activity_and_social | Comments placeholder, top holders, activity feed | 00, 01 |
| 06 | related_markets_polish | Related markets sidebar, responsive, loading states | 01-05 |

### Sprint Dependency Graph

```
                    ┌─────────────────────────────────────────────┐
                    │     Sprint 00: Polymarket Proxy Layer       │
                    │     (MUST BE FIRST - backend foundation)    │
                    └─────────────────────┬───────────────────────┘
                                          │
                                          ▼
                    ┌─────────────────────────────────────────────┐
                    │     Sprint 01: Event Page Foundation        │
                    │     (routing, layout, basic data)           │
                    └─────────────────────┬───────────────────────┘
                                          │
            ┌─────────────────────────────┼─────────────────────────┐
            │                             │                         │
            ▼                             ▼                         ▼
  ┌─────────────────┐         ┌─────────────────┐       ┌─────────────────┐
  │ Sprint 02       │         │ Sprint 03       │       │ Sprint 04       │
  │ Market Display  │         │ Trading Panel   │       │ Charts/Orderbook│
  │ (UI components) │         │ (sidebar UI)    │       │ (uses proxy)    │
  └────────┬────────┘         └────────┬────────┘       └────────┬────────┘
           │                           │                         │
           │                  ┌────────┴─────────────────────────┘
           │                  │
           │                  ▼
           │        ┌─────────────────┐
           │        │ Sprint 05       │
           │        │ Activity/Social │
           │        │ (uses proxy)    │
           │        └────────┬────────┘
           │                 │
           └─────────────────┼─────────────────────────────────────┐
                             │                                     │
                             ▼                                     │
              ┌─────────────────────┐                              │
              │ Sprint 06: Polish   │◄─────────────────────────────┘
              │ (responsive, a11y)  │
              │ MUST BE LAST        │
              └─────────────────────┘
```

**Parallelization:**
- Sprints 02, 03, 04, 05 can run in parallel after 01 is complete
- Sprint 06 must be last (depends on all others)

## Key Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Data Strategy | Polymarket API Proxy | Real-time data, faster to ship, no pipeline changes |
| Routing | /event/[slug] | SEO-friendly, matches Polymarket URL structure |
| Trading Buttons | Dummy (toast notification) | Phase 1 - no real trading integration |
| Chart Library | Recharts | Already in use, good for financial data |
| Order Book | Live L2 via proxy | Polymarket `/book` endpoint provides real data |
| Comments | Placeholder | Full comment system deferred to future release |
| Related Markets | Category-based (ClickHouse) | Simple heuristic; ML similarity deferred |
| Caching | Redis if available, else in-memory | Docker profile `cache` for Redis |

## Exit Criteria

- [ ] Polymarket proxy endpoints working with caching
- [ ] Event detail page renders with all sections
- [ ] URL routing works: /event/{slug}
- [ ] Event header shows title, probability, volume, dates
- [ ] Outcome cards display Yes/No prices with color coding
- [ ] Trading panel shows outcome selection and amount input
- [ ] Buy/Sell buttons show toast notification (dummy)
- [ ] Price chart renders with time range selection
- [ ] Order book shows live bid/ask depth
- [ ] Resolution rules display event description
- [ ] Activity tabs switch between Comments/TopHolders/Activity
- [ ] Top holders shows wallet addresses and positions
- [ ] Activity feed shows recent trades
- [ ] Related markets sidebar links to similar events
- [ ] Responsive design works on mobile/tablet/desktop
- [ ] Loading skeletons for all async data
- [ ] Error states handled gracefully
- [ ] Watchlist toggle on event page (authenticated users)

## API Endpoints

### New Proxy Endpoints (Sprint 00)

```
GET /api/v1/proxy/markets/{token_id}/timeseries
  - Proxies: https://clob.polymarket.com/prices-history
  - Query: interval=1m|5m|15m|1h|6h|1d, fidelity=1-60, startTs, endTs
  - Response: { history: [{t, o, h, l, c, v}] }
  - Cache: 30s-1h TTL based on interval

GET /api/v1/proxy/markets/{token_id}/orderbook
  - Proxies: https://clob.polymarket.com/book
  - Query: depth=10 (default)
  - Response: { bids: [{price, size}], asks: [{price, size}], spread }
  - Cache: 5s TTL

GET /api/v1/proxy/markets/{token_id}/top-holders
  - Proxies: https://data-api.polymarket.com/top-holders
  - Query: limit=10
  - Response: { holders: [{address, position, value}] }
  - Cache: 5m TTL

GET /api/v1/proxy/markets/{token_id}/trades
  - Proxies: https://data-api.polymarket.com/trades
  - Query: limit=50, before (cursor)
  - Response: { trades: [{id, price, size, side, timestamp, maker}] }
  - Cache: 30s TTL
```

### Internal Endpoints (ClickHouse)

```
GET /api/v1/events/{slug}
  - Source: dim_event + dim_market + dim_outcome
  - Response: EventDetailResponse with nested markets and outcomes
  - Includes: token_ids for proxy calls

GET /api/v1/events/{event_id}/related
  - Source: dim_event (same category)
  - Query: limit=5
  - Response: { events: [{id, slug, title, probability, volume}] }
```

## Polymarket API Reference

| Endpoint | Rate Limit | Docs |
|----------|------------|------|
| CLOB `/prices-history` | 9000/10s (overall) | https://docs.polymarket.com/developers/CLOB/timeseries |
| CLOB `/book` | 9000/10s (overall) | https://docs.polymarket.com/developers/CLOB/l2-order-book |
| Data `/top-holders` | 1000/10s (overall) | https://docs.polymarket.com/api-reference/core/get-top-holders-for-markets |
| Data `/trades` | 200/10s | https://docs.polymarket.com/api-reference/core/get-trades-for-a-user-or-markets |

## Deferred / Phase 2

- **Migrate to internal data:** Replace proxy endpoints with our pipeline data where available
- Real trading integration (requires CLOB auth)
- WebSocket real-time price updates
- Full comment system with posting
- Advanced related markets (ML-based similarity)
- Social features (following traders, notifications)
- Mobile app-specific optimizations
