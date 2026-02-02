CREATE TABLE IF NOT EXISTS prediction_gold.dim_wallet
(
    platform        String,
    wallet_address  String,
    first_trade_ts  DateTime64(6, 'UTC'),
    last_trade_ts   DateTime64(6, 'UTC'),
    trade_count     UInt64,
    updated_at      DateTime DEFAULT now()
)
ENGINE = ReplacingMergeTree(updated_at)
ORDER BY (platform, wallet_address);
