CREATE TABLE IF NOT EXISTS prediction_gold.wallet_pnl_daily
(
    day_utc          Date,
    wallet           String,
    realized_pnl_usd Float64,
    fees_usd         Float64,
    volume_usd       Float64,
    trades_count     UInt64,
    wins             UInt64,
    losses           UInt64,
    version          UInt64 DEFAULT toUnixTimestamp(now())
)
ENGINE = ReplacingMergeTree(version)
ORDER BY (wallet, day_utc)
TTL day_utc + INTERVAL 90 DAY;
