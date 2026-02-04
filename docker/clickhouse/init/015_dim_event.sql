-- dim_event: Event dimension table from Silver events with category and hierarchy.
CREATE TABLE IF NOT EXISTS prediction_gold.dim_event
(
    platform            String,
    platform_event_id   String,
    title               String,
    description         String,
    slug                String,
    status              String,
    category            String,
    updated_at          DateTime DEFAULT now()
)
ENGINE = ReplacingMergeTree(updated_at)
ORDER BY (platform, platform_event_id);
