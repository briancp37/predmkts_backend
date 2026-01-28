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
    )

    bronze_bucket: str
    aws_region: str = "us-east-1"
    log_level: str = "INFO"

    # Polymarket CLOB API settings (optional - only required for CLOB trades backfill)
    polygon_wallet_public_key: str | None = None
    polygon_wallet_private_key: str | None = None
    polymarket_builder_api_key: str | None = None
    polymarket_builder_secret: str | None = None
    polymarket_builder_passphrase: str | None = None

    # Kalshi API settings (optional - only required for Kalshi ingestion)
    kalshi_api_key_id: str | None = None
    kalshi_private_key_path: str | None = None
    kalshi_api_base_url: str = "https://api.elections.kalshi.com/trade-api/v2"


@lru_cache
def get_settings() -> Settings:
    """Get cached application settings.

    Returns:
        Settings instance loaded from environment variables.
    """
    return Settings()  # type: ignore[call-arg]
