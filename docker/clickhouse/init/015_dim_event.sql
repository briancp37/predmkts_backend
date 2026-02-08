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
    image_url           String DEFAULT '',
    tags                Array(String) DEFAULT [],
    updated_at          DateTime DEFAULT now()
)
ENGINE = ReplacingMergeTree(updated_at)
ORDER BY (platform, platform_event_id);

-- Add image_url column if it doesn't exist (for existing tables)
ALTER TABLE prediction_gold.dim_event ADD COLUMN IF NOT EXISTS image_url String DEFAULT '';

-- Add tags column if it doesn't exist (for existing tables)
ALTER TABLE prediction_gold.dim_event ADD COLUMN IF NOT EXISTS tags Array(String) DEFAULT [];
