"""Configuration management via environment variables."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables.

    Attributes:
        bronze_bucket: S3 bucket name for bronze layer data (required).
        aws_region: AWS region for S3 operations.
        log_level: Logging level for the application.
        kalshi_api_key_id: Kalshi API key ID for authentication.
        kalshi_private_key_path: Path to Kalshi RSA private key PEM file.
        kalshi_api_base_url: Kalshi API base URL (production or demo).
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    bronze_bucket: str
    silver_bucket: str = ""
    aws_region: str = "us-east-1"
    log_level: str = "INFO"

    # Polymarket CLOB API settings (optional - only required for CLOB trades backfill)
    polygon_wallet_address: str | None = None
    polygon_wallet_public_key: str | None = None
    polygon_wallet_private_key: str | None = None
    polymarket_builder_api_key: str | None = None
    polymarket_builder_secret: str | None = None
    polymarket_builder_passphrase: str | None = None

    # Gold layer settings
    gold_bucket: str = ""

    # ClickHouse settings (optional - only required for Gold layer)
    clickhouse_host: str = "localhost"
    clickhouse_port: int = 8123
    clickhouse_user: str = "default"
    clickhouse_password: str = ""
    clickhouse_database: str = "prediction_gold"

    # Kalshi API settings (optional - only required for Kalshi ingestion)
    kalshi_api_key_id: str | None = None
    kalshi_private_key_path: str | None = None
    kalshi_api_base_url: str = "https://api.elections.kalshi.com/trade-api/v2"

    # Polymarket proxy layer settings
    polymarket_clob_url: str = "https://clob.polymarket.com"
    polymarket_gamma_url: str = "https://gamma-api.polymarket.com"
    polymarket_data_url: str = "https://data-api.polymarket.com"
    polymarket_proxy_cache_ttl: int = 30  # Default cache TTL in seconds
    polymarket_proxy_timeout: float = 10.0  # Request timeout in seconds

    # PostgreSQL settings (for API user data)
    postgres_host: str = "localhost"
    postgres_port: int = 5432
    postgres_user: str = "predmkts"
    postgres_password: str = "predmkts"
    postgres_database: str = "predmkts"

    # JWT settings
    jwt_secret: str = "change-me-in-production"
    jwt_algorithm: str = "HS256"
    jwt_access_token_expire_minutes: int = 30
    jwt_refresh_token_expire_days: int = 30

    # API debug mode (exposes stack traces in error responses)
    debug: bool = False

    # CORS settings (comma-separated list of allowed origins)
    # Use "*" for development, specific origins for production
    cors_origins: str = "*"

    @property
    def cors_origin_list(self) -> list[str]:
        """Parse CORS origins from comma-separated string."""
        if self.cors_origins == "*":
            return ["*"]
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    def validate_jwt_secret(self) -> None:
        """Validate JWT secret is strong enough for production.

        Raises ValueError if not in debug mode and secret is weak.
        """
        if self.debug:
            return  # Allow weak secrets in debug mode

        if self.jwt_secret == "change-me-in-production":
            raise ValueError(
                "JWT_SECRET must be changed from default value in production. "
                "Use a random string of at least 32 characters."
            )

        if len(self.jwt_secret) < 32:
            raise ValueError(
                "JWT_SECRET must be at least 32 characters in production. "
                f"Current length: {len(self.jwt_secret)}"
            )

    @property
    def postgres_url(self) -> str:
        """Get async PostgreSQL connection URL."""
        return (
            f"postgresql+asyncpg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_database}"
        )


@lru_cache
def get_settings() -> Settings:
    """Get cached application settings.

    Returns:
        Settings instance loaded from environment variables.
    """
    return Settings()  # type: ignore[call-arg]
