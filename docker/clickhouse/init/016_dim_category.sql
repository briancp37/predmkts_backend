CREATE TABLE IF NOT EXISTS prediction_gold.dim_category
(
    platform    String,
    category    String,
    event_count UInt64,
    version     UInt64 DEFAULT toUnixTimestamp(now())
)
ENGINE = ReplacingMergeTree(version)
ORDER BY (platform, category);
