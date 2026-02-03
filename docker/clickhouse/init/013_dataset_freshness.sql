CREATE TABLE IF NOT EXISTS prediction_gold.dataset_freshness
(
    dataset             LowCardinality(String),
    last_success_at     DateTime64(3, 'UTC'),
    expected_lag_seconds UInt32,
    actual_lag_seconds  UInt64,
    state               LowCardinality(String),
    last_run_id         Nullable(String)
)
ENGINE = ReplacingMergeTree(last_success_at)
ORDER BY dataset;
