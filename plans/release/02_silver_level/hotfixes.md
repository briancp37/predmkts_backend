# Silver Level Hotfixes

## 2026-02-04: Stream entities default to append instead of merge/upsert

**Problem:** Silver processing for stream entities (trades, order_filled) used
`table.upsert()` by default, which performs a full-table scan to match on join
keys before writing.  As the Iceberg table grew (1,100+ manifests / billions of
rows), each day's upsert took 30-60+ minutes — making near-continuous
processing impractical.

**Root cause:** `processor.py` treated all entities the same way: merge/upsert
by default, with `--append-only` as an opt-in CLI flag.  Stream entities are
immutable events that never need updating, so the upsert scan was pure waste.

**Fix:** The processor now auto-detects entity type and chooses the write
strategy accordingly:

- **Stream entities** (trades, order_filled): default to `write_to_iceberg()`
  (fast append — just writes new Parquet files, no table scan).
- **Catalog entities** (markets, events): continue to default to
  `merge_to_iceberg()` (upsert) since records may be updated.
- `--overwrite` takes highest precedence (any entity type).
- `--append-only` can still force append for catalog entities when needed.

Entity classification reuses the existing `CATALOG_ENTITIES` frozenset from
`discovery.py`, which already distinguishes catalog vs stream entities for
manifest selection logic.

**Files changed:**

| File | Change |
|---|---|
| `src/prediction_data/silver/processor.py` | Import `CATALOG_ENTITIES`; reorder write decision: overwrite > append/stream > merge |
| `src/prediction_data/cli/silver.py` | Updated `--append-only` help text to note stream entities already default to append |
| `tests/test_silver_processor.py` | Added `test_stream_entity_defaults_to_append`; renamed `test_default_uses_merge` to `test_catalog_entity_defaults_to_merge`; updated 3 trades tests to mock `write_to_iceberg` |

**Test results:** 1,128 passed, 0 failed.

**Performance impact:** Append writes complete in seconds vs 30-60+ minutes per
day for upsert.  The idempotency guarantee is preserved by `SilverStateStore`
(skips already-processed manifests).  Periodic compaction
(`silver maintain --op compact`) merges small append files.

---

## 2026-02-06: Fix Polymarket status field derivation (markets & events)

**Problem:** The frontend was showing stale markets (ended 6+ days ago) because
the API filter `status != 'resolved'` was not working correctly. All 386,588
markets in `dim_market` had `status = 'True'` (string) instead of meaningful
values like "active", "closed", or "resolved".

**Root cause:** In `normalize.py`, the markets normalizer had:
```python
"status": _safe_str(record.get("status") or record.get("active")),
```

The Polymarket API does not return a `status` field. It returns:
- `active`: boolean (True if market is tradeable)
- `closed`: boolean (True if market is closed)
- `umaResolutionStatus`: string ("resolved", "proposed", etc.)

Since `record.get("status")` returned `None`, the code fell back to
`record.get("active")` which was boolean `True`. Then `_safe_str(True)`
converted it to the string `"True"`.

The same issue affected the events normalizer, which only checked for a
non-existent `status` field.

**Fix:** Added `_derive_polymarket_status()` helper that properly derives
status from Polymarket API fields:

```python
def _derive_polymarket_status(record: dict[str, Any]) -> str:
    # Check for explicit resolution status first
    uma_status = record.get("umaResolutionStatus")
    if uma_status and isinstance(uma_status, str) and uma_status.strip():
        return uma_status.strip().lower()

    # Derive from boolean flags
    closed = record.get("closed")
    active = record.get("active")

    if closed is True:
        return "closed"
    if active is True:
        return "active"
    if active is False:
        return "inactive"

    return "unknown"
```

Updated both `PolymarketMarketsNormalizer` and `PolymarketEventsNormalizer`
to use this helper.

**Files changed:**

| File | Change |
|---|---|
| `src/prediction_data/silver/normalize.py` | Added `_derive_polymarket_status()` helper; updated markets normalizer (line 285); updated events normalizer (line 351) |

**Recovery steps:**

After deploying this fix, ALL Silver data must be reprocessed to populate
correct status values. Polymarket data goes back to 2013, so this is a large
job that should run on ECS (not locally).

**Full all-time reprocessing (run on ECS):**

```bash
# Reprocess ALL markets from 2013 to present
prediction-data silver process --platform polymarket --entity markets \
    --start-date 2013-01-01 --end-date 2026-02-06 --force-reprocess

# Reprocess ALL events from 2013 to present
prediction-data silver process --platform polymarket --entity events \
    --start-date 2013-01-01 --end-date 2026-02-06 --force-reprocess

# Reload Gold dimension tables
prediction-data gold load-dims
```

**Running on ECS:**

Use the ECS task definition to run the reprocessing job:

```bash
# Run markets reprocessing on ECS
aws ecs run-task \
    --cluster prediction-data \
    --task-definition prediction-data-silver \
    --launch-type FARGATE \
    --network-configuration "awsvpcConfiguration={subnets=[subnet-xxx],securityGroups=[sg-xxx],assignPublicIp=ENABLED}" \
    --overrides '{
        "containerOverrides": [{
            "name": "silver",
            "command": ["silver", "process", "--platform", "polymarket", "--entity", "markets", "--start-date", "2013-01-01", "--end-date", "2026-02-06", "--force-reprocess"]
        }]
    }'

# Run events reprocessing on ECS (after markets complete)
aws ecs run-task \
    --cluster prediction-data \
    --task-definition prediction-data-silver \
    --launch-type FARGATE \
    --network-configuration "awsvpcConfiguration={subnets=[subnet-xxx],securityGroups=[sg-xxx],assignPublicIp=ENABLED}" \
    --overrides '{
        "containerOverrides": [{
            "name": "silver",
            "command": ["silver", "process", "--platform", "polymarket", "--entity", "events", "--start-date", "2013-01-01", "--end-date", "2026-02-06", "--force-reprocess"]
        }]
    }'
```

**Warning:** Do NOT run full reprocessing locally — it will consume significant
memory and CPU. Always use ECS for large backfill jobs.

**Impact:** Once reprocessed, the API will correctly filter markets by status,
showing only active/tradeable markets instead of stale resolved ones.
