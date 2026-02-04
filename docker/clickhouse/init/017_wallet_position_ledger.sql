CREATE TABLE IF NOT EXISTS prediction_gold.wallet_position_ledger
(
    ts                          DateTime64(6, 'UTC'),
    wallet                      String,
    platform                    String,
    market_id                   String,
    outcome_id                  String,
    side                        String,
    qty_delta                   Float64,
    price                       Float64,
    fees_usd                    Float64,
    qty_before                  Float64,
    qty_after                   Float64,
    avg_cost_before             Float64,
    avg_cost_after              Float64,
    realized_pnl_this_fill_usd Float64
)
ENGINE = MergeTree
ORDER BY (wallet, ts)
TTL toDate(ts) + INTERVAL 30 DAY;
