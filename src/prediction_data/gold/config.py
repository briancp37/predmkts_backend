"""Gold-specific configuration constants."""

# Default TTL for ClickHouse hot data (days).
DEFAULT_TTL_DAYS: int = 90

# Default lookback window for incremental Gold processing (days).
DEFAULT_LOOKBACK_DAYS: int = 7

# S3 Gold path convention: gold/<table_name>/day=YYYY-MM-DD/part-NNN.parquet
GOLD_PATH_TEMPLATE: str = "gold/{table_name}/day={day}/{filename}"
