CREATE TABLE IF NOT EXISTS prediction_gold.wallet_position_state
(
    wallet          String,
    platform        String,
    market_id       String,
    outcome_id      String,
    qty             Float64,
    avg_cost        Float64,
    cost_basis_usd  Float64,
    last_fill_ts    DateTime64(6, 'UTC'),
    first_open_ts   DateTime64(6, 'UTC')
)
ENGINE = ReplacingMergeTree(last_fill_ts)
ORDER BY (wallet, platform, market_id, outcome_id)
TTL toDate(last_fill_ts) + INTERVAL 90 DAY;
