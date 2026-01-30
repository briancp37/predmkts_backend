Below is a **full, production-grade `RELEASE_3.md`** at the same level of detail as Releases 1 and 2, followed by a **clear answer** to whether this is the final release or if another one should exist.

---

````md
# RELEASE_3.md
## Release 3 — Gold Serving Layer (ClickHouse) Fully Working  
### Silver → Gold Analytics, APIs, Rollups, SLAs

**Scope:** Everything required to go from **trusted Silver (Iceberg)** to a **production-ready Gold layer** in **ClickHouse** that supports APIs, analytics, dashboards, and downstream products.  
**Non-Goals:** End-user UI, trading strategies, ML models, alerting products (those are Release 4+).

---

## 1) Objective

Release 3 establishes **Gold as the serving and analytics layer**:

- Fast, query-optimized ClickHouse tables
- Clear separation between **facts**, **dimensions**, and **rollups**
- Deterministic, rebuildable aggregates
- Stable schemas suitable for APIs and frontends
- Operational observability and SLAs

At the end of Release 3:
> Gold is the only layer most applications ever need to touch.

---

## 2) Definition of Done (Exit Criteria)

Release 3 is complete when:

1. ✅ ClickHouse cluster is deployed and reachable
2. ✅ Dimension tables are populated from Silver
3. ✅ Fact tables are populated from Silver
4. ✅ Time-based rollups are computed and correct
5. ✅ Rebuilds from Silver are deterministic and documented
6. ✅ Query latency meets target SLAs
7. ✅ Operational metadata is queryable in ClickHouse
8. ✅ API consumers can rely on Gold without custom joins

---

## 3) Inputs & Outputs

### Inputs
- Silver Iceberg tables (Release 2)
- Canonical schemas (where applicable)

### Outputs
- ClickHouse **dimension tables**
- ClickHouse **fact tables**
- ClickHouse **rollup tables / materialized views**
- API-ready datasets

---

## 4) Gold Table Taxonomy (Critical)

Gold tables are split into **three explicit categories**.

### 4.1 Dimensions (mostly mutable, low volume)
- `dim_platform`
- `dim_market`
- `dim_outcome`
- `dim_wallet`
- `dim_category` (optional)

Characteristics:
- Slowly changing
- Use `ReplacingMergeTree(version)`
- Queried constantly by APIs

---

### 4.2 Facts (append-heavy, immutable-ish)
- `fact_trades`
- `fact_order_fills` (if available)
- `fact_market_updates`

Characteristics:
- High volume
- Append-only
- Never updated in place
- Use `MergeTree`

---

### 4.3 Rollups / Aggregates
- `market_stats_hourly`
- `market_price_timeseries_minute`
- `wallet_positions_daily`
- `wallet_pnl_daily`
- `leaderboard_daily`
- `smart_scores_daily`
- `flow_metrics_hourly`

Characteristics:
- Derived
- Rebuildable
- Query-optimized
- Deterministic

---

## 5) ClickHouse Engine Choices (Non-Negotiable)

### 5.1 Dimensions
```sql
ENGINE = ReplacingMergeTree(version)
ORDER BY (primary_key)
````

Rules:

* Always include a `version` or `updated_at`
* Latest record wins
* Never delete; replace

---

### 5.2 Facts

```sql
ENGINE = MergeTree
PARTITION BY toYYYYMM(event_ts)
ORDER BY (platform, market_id, event_ts)
```

Rules:

* Append-only
* No updates
* No deletes
* Event-time ordering

---

### 5.3 Rollups

Two allowed patterns:

1. **Scheduled rebuild tables**
2. **Materialized views** (only if logic is simple and stable)

Rebuildable tables are preferred for correctness.

---

## 6) Silver → Gold Loading Model

### 6.1 Load Order

1. Dimensions
2. Facts
3. Rollups

This order is mandatory to maintain referential sanity.

---

### 6.2 Idempotency Rules

* Gold loads are **partition-scoped**
* Re-running a load for the same time range:

  * overwrites that partition (or truncates + reloads)
* No cross-partition side effects

---

### 6.3 Example Load Units

* Facts: `(platform, date range)`
* Rollups: `(market_id, hour/day)`
* Wallet metrics: `(wallet_id, day)`

---

## 7) Canonicalization in Gold

By Release 3:

* Gold tables **must** expose:

  * `canonical_market_id`
  * `canonical_outcome_id`
* Platform-specific IDs remain available
* Cross-platform analytics rely on canonical IDs

Canonical mapping sources:

* `mappings/market_links.yaml`
* Silver canonical tables (if created in R2)

---

## 8) Rollups & Metrics (Required)

### 8.1 Market Metrics

* Volume (total, buy, sell)
* VWAP
* Last price
* High/low
* Volatility proxy
* Liquidity proxies (if available)

### 8.2 Wallet Metrics

* Positions (net, gross)
* Realized P&L
* Unrealized P&L
* Win rate
* Turnover
* Size buckets

### 8.3 Leaderboards

* By volume
* By P&L
* By Sharpe-like score
* Time-windowed (7d / 30d / all-time)

---

## 9) Query SLAs (Target)

| Query Type   | Target   |
| ------------ | -------- |
| Market stats | < 100 ms |
| Leaderboards | < 200 ms |
| Wallet page  | < 300 ms |
| Time series  | < 500 ms |

Gold exists to **guarantee performance**, not flexibility.

---

## 10) Rebuild & Recovery Strategy

### 10.1 When Rebuilds Are Expected

* Bug in Silver logic
* Canonical mapping changes
* Metric definition changes
* Late corrections discovered

### 10.2 Rebuild Rules

* Always rebuild from Silver
* Never mutate facts in place
* Rollups are disposable

Gold correctness is derived, not sacred.

---

## 11) Orchestration (Release 3)

### 11.1 Triggering Model

| Stage        | Trigger                          |
| ------------ | -------------------------------- |
| Bronze       | EventBridge                      |
| Silver       | Manifest-driven (Dagster sensor) |
| Gold facts   | Silver success                   |
| Gold rollups | Scheduled + dependency-aware     |

### 11.2 Recommended Orchestrator

**Dagster** is strongly recommended starting in Release 3:

* Asset graph clarity
* Partitioned backfills
* Rebuild orchestration
* Clear lineage (Bronze → Silver → Gold)

---

## 12) Observability & Ops (Mandatory)

Gold must expose:

* Load durations
* Rows read / written
* Partition coverage
* Rollup freshness
* Query performance (p95)

Recommended tables:

* `gold_load_runs`
* `gold_rollup_runs`
* `gold_freshness_metrics`

---

## 13) API Readiness Contract

Gold schemas must:

* Be stable and documented
* Avoid nested JSON
* Avoid nullable surprises
* Support pagination & filtering
* Avoid joins across large fact tables at query time

If an API needs a join, it should already exist in Gold.

---

## 14) Explicit Non-Goals (Still Not Built)

* Frontend UI
* Alerts / notifications
* Strategy signals
* ML models
* User auth / permissions

Gold is a **data product**, not a user product.

---

## 15) Is This the Final Release?

**No — this is the final *data platform* release, but not the final product release.**

### You should plan **one more formal release**:

---

## 16) Release 4 (Recommended, but Optional)

### Release 4 — Productization & Intelligence Layer

This is where you add:

* APIs
* Frontend
* Alerts
* Strategy signals
* ML features
* Permissions / auth
* SLAs for external users

Think of it as:

* Releases 1–3 = **data infrastructure**
* Release 4 = **business/product layer**

You *can* stop at Release 3 if this is purely an internal data platform — but most successful systems don’t.

---

## 17) Final Rule

> **Gold is convenience, not truth.**
> Silver is truth.
> Bronze is history.

Release 3 exists to make truth *fast and usable*.

```

---

## Direct answer to your question

**Is Release 3 the final release?**

- ✅ **Final release for the *data platform*** → **Yes**
- ❌ **Final release for the *product*** → **No**

A clean roadmap is:

1. **Release 1** — Bronze (immutability, correctness)
2. **Release 2** — Silver (truth, contracts)
3. **Release 3** — Gold (performance, APIs)
4. **Release 4 (optional but recommended)** — Productization (alerts, UI, strategies, ML)

If you want, next I can:
- collapse all four into a single **ROADMAP.md**
- generate **Dagster asset graphs** for R2/R3
- or produce **ClickHouse DDL** that exactly matches Release 3’s guarantees
```
