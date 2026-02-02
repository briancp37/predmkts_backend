-- dim_market: Market dimension table from Silver markets with canonical IDs.
CREATE TABLE IF NOT EXISTS prediction_gold.dim_market
(
    platform            String,
    platform_market_id  String,
    canonical_market_id String,
    question            String,
    description         String,
    market_slug         String,
    status              String,
    event_id            String,
    tokens              String,
    updated_at          DateTime DEFAULT now()
)
ENGINE = ReplacingMergeTree(updated_at)
ORDER BY (platform, platform_market_id);
