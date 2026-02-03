CREATE TABLE IF NOT EXISTS prediction_gold.pipeline_runs
(
    run_id              String,
    stage               LowCardinality(String),  -- bronze, silver, gold
    started_at          DateTime64(3, 'UTC'),
    ended_at            Nullable(DateTime64(3, 'UTC')),
    status              LowCardinality(String),  -- success, failed, running
    input_snapshot_id   Nullable(String),
    output_snapshot_id  Nullable(String),
    rows_written        UInt64        DEFAULT 0,
    bytes_written       UInt64        DEFAULT 0,
    error               Nullable(String)
)
ENGINE = MergeTree
ORDER BY (stage, started_at);
