CREATE TABLE IF NOT EXISTS prediction_gold.gold_watchlist
(
    wallet_address String,
    added_at       DateTime DEFAULT now(),
    notes          String DEFAULT '',
    active         Bool DEFAULT true
)
ENGINE = ReplacingMergeTree(added_at)
ORDER BY wallet_address;
