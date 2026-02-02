-- dim_outcome: Outcome dimension derived from markets token data.
CREATE TABLE IF NOT EXISTS prediction_gold.dim_outcome
(
    platform        String,
    market_id       String,
    outcome_id      String,
    token_id        String,
    side            String,
    outcome_label   String,
    version         UInt64 DEFAULT toUnixTimestamp(now())
)
ENGINE = ReplacingMergeTree(version)
ORDER BY (platform, market_id, outcome_id);
