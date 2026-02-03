CREATE TABLE IF NOT EXISTS prediction_gold.wallet_position_snapshot_daily
(
    day_utc              Date,
    wallet               String,
    platform             String,
    market_id            String,
    outcome_id           String,
    qty                  Float64,
    avg_cost             Float64,
    mark_price           Float64,
    position_value_usd   Float64,
    unrealized_pnl_usd   Float64,
    version              UInt64 DEFAULT toUnixTimestamp(now())
)
ENGINE = ReplacingMergeTree(version)
PARTITION BY toYYYYMM(day_utc)
ORDER BY (wallet, day_utc, platform, market_id, outcome_id)
TTL day_utc + INTERVAL 90 DAY;
