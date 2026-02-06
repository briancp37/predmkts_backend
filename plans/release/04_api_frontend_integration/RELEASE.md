# Release 04: API & Frontend Integration

## Overview

Add a FastAPI REST API layer to serve the Next.js frontend, unifying the codebase into a single monorepo. This release transforms the data pipeline into a full-stack application.

## Goals

1. **FastAPI REST API** - Serve market, trader, and user data to the frontend
2. **JWT Authentication** - Backend-issued JWTs, frontend becomes pure UI
3. **PostgreSQL User Database** - Store user accounts, watchlists, tracked traders
4. **OpenAPI Contract** - Auto-generated spec for TypeScript type generation
5. **Frontend Integration** - Update frontend to call new backend API

## Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                      FASTAPI BACKEND                                │
│  ┌─────────────────┐    ┌─────────────────────────────────────────┐│
│  │   PostgreSQL    │    │              ClickHouse                 ││
│  │   (user data)   │    │           (market data)                 ││
│  │  - users        │    │  - dim_market, dim_wallet               ││
│  │  - watchlists   │    │  - market_mark_daily                    ││
│  │  - tracked_     │    │  - wallet_position_ledger               ││
│  │    traders      │    │  - wallet_pnl_daily                     ││
│  └─────────────────┘    └─────────────────────────────────────────┘│
│                                                                     │
│  FastAPI: /api/v1/*                                                │
└─────────────────────────────────────────────────────────────────────┘
                                    │
                         JSON + JWT in Authorization header
                                    ▼
┌─────────────────────────────────────────────────────────────────────┐
│                      NEXT.JS FRONTEND (web/)                        │
│  - Pure UI, no database                                             │
│  - Proxies /api/v1/* to FastAPI                                     │
│  - Types generated from OpenAPI spec                                │
└─────────────────────────────────────────────────────────────────────┘
```

## Key Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| API Framework | FastAPI | Auto-generates OpenAPI, async, Pydantic |
| Auth Strategy | Backend-issued JWT | Single source of truth |
| User Database | PostgreSQL | OLTP workload, separate from ClickHouse |
| Production DB Hosting | Supabase (free tier) | $0/mo vs $15/mo AWS RDS, sufficient for 100k+ users |
| Contract Sync | OpenAPI → TypeScript | Generated types ensure consistency |
| Deployment | Same domain via proxy | No CORS complexity |

## Entities

### PostgreSQL Tables (User Data)
- `users` - Authentication and profile
- `watchlists` - User's saved markets
- `tracked_traders` - User's tracked wallet addresses

### API Resources
- Auth (register, login, refresh, me)
- Markets (list, detail, advanced, screener, trades, price-history)
- Traders (list, detail, trades, smart-scores)
- Leaderboard
- Watchlist (CRUD)
- Tracked Traders (CRUD with tier limits)
- Events & Tags

## Sprints

| Sprint | Name | Focus |
|--------|------|-------|
| 01 | foundation_auth | FastAPI setup, Postgres, JWT auth |
| 02 | market_endpoints | Market data API endpoints |
| 03 | trader_endpoints | Trader data API endpoints |
| 04 | user_features | Watchlist, tracked traders |
| 05 | integration_polish | Error handling, testing, cleanup |
| 06 | supabase | Production database migration to Supabase |

## Exit Criteria

- [ ] All API endpoints implemented and tested
- [ ] Frontend pages functional with real data
- [ ] JWT auth working end-to-end
- [ ] OpenAPI spec generates valid TypeScript types
- [ ] Watchlist and tracked traders functional
- [ ] Tier limits enforced (FREE: 6 traders, PRO: 50)
- [ ] docker-compose starts all services (Postgres, ClickHouse)
- [ ] No regressions in existing CLI/pipeline functionality
- [ ] Supabase production database configured and tested

## Deferred

- Jobs/Admin endpoints (use CLI for now)
- Complex alerts system
- Saved searches
- Real-time streaming (WebSockets)
