CREATE TABLE IF NOT EXISTS prediction_gold.market_mark_daily
(
    platform           String,
    market_id          String,
    outcome_id         String,
    day_utc            Date,
    mark_price         Float64,
    last_trade_price   Float64,
    volume_usd_24h     Float64,
    trades_count_24h   UInt64,
    active_wallets_24h UInt64,
    liquidity_metric   Float64,
    version            UInt64 DEFAULT toUnixTimestamp(now())
)
ENGINE = ReplacingMergeTree(version)
PARTITION BY toYYYYMM(day_utc)
ORDER BY (platform, market_id, outcome_id, day_utc)
TTL day_utc + INTERVAL 90 DAY;
