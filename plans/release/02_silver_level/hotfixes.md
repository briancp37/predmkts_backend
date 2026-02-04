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
