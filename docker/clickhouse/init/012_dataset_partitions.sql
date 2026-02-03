CREATE TABLE IF NOT EXISTS prediction_gold.dataset_partitions
(
    dataset             LowCardinality(String),
    partition_day_utc   Date,
    row_count           UInt64        DEFAULT 0,
    max_event_ts        Nullable(DateTime64(3, 'UTC')),
    written_at          DateTime64(3, 'UTC'),
    run_id              Nullable(String)
)
ENGINE = ReplacingMergeTree(written_at)
ORDER BY (dataset, partition_day_utc);
