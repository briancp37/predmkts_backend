CREATE TABLE IF NOT EXISTS prediction_gold.wallet_mtm_daily
(
    day_utc              Date,
    wallet               String,
    equity_usd           Float64,
    unrealized_pnl_usd   Float64,
    exposure_gross_usd   Float64,
    exposure_net_usd     Float64,
    positions_count      UInt64,
    missing_marks_count  UInt64,
    version              UInt64 DEFAULT toUnixTimestamp(now())
)
ENGINE = ReplacingMergeTree(version)
PARTITION BY toYYYYMM(day_utc)
ORDER BY (wallet, day_utc)
TTL day_utc + INTERVAL 90 DAY;
