-- dim_platform: Static platform dimension table.
CREATE TABLE IF NOT EXISTS prediction_gold.dim_platform
(
    platform_id   String,
    platform_name String,
    url           String,
    updated_at    DateTime DEFAULT now()
)
ENGINE = ReplacingMergeTree(updated_at)
ORDER BY platform_id;
