CREATE TABLE IF NOT EXISTS prediction_gold.data_quality_metrics
(
    dataset             LowCardinality(String),
    partition           Date,
    check_name          LowCardinality(String),
    status              LowCardinality(String),  -- pass, fail, warn
    observed_value      Nullable(Float64),
    expected            Nullable(String),
    run_id              Nullable(String),
    checked_at          DateTime64(3, 'UTC')
)
ENGINE = MergeTree
ORDER BY (dataset, partition, run_id);
