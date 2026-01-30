"""AWS Glue Catalog connection factory for Silver Iceberg tables."""

from __future__ import annotations

import time
from functools import lru_cache
from typing import TYPE_CHECKING

from pyiceberg.catalog.glue import GlueCatalog

from prediction_data.core.logging import get_logger

if TYPE_CHECKING:
    from pyiceberg.catalog import Catalog

logger = get_logger(__name__)

CATALOG_NAME = "glue"
SILVER_DATABASE = "prediction_silver"
DEFAULT_WAREHOUSE = "s3://{bucket}/silver/"

MAX_RETRIES = 3
RETRY_BASE_DELAY_S = 1.0


class CatalogConnectionError(Exception):
    """Raised when the Glue Catalog connection cannot be established."""


def _build_catalog_properties(
    *,
    warehouse: str,
    region: str,
) -> dict[str, str]:
    """Build catalog properties for Glue Catalog connection.

    Args:
        warehouse: S3 warehouse path (e.g., s3://bucket/silver/).
        region: AWS region for the Glue Catalog.

    Returns:
        Dictionary of catalog configuration properties.
    """
    return {
        "type": "glue",
        "s3.region": region,
        "glue.region": region,
        "warehouse": warehouse,
    }


def load_catalog(
    *,
    warehouse: str | None = None,
    region: str | None = None,
) -> Catalog:
    """Create a PyIceberg Glue Catalog instance with retry logic.

    Attempts to connect to the AWS Glue Catalog, retrying on transient
    failures with exponential backoff.

    Args:
        warehouse: S3 warehouse path. If None, uses settings.
        region: AWS region. If None, uses settings.

    Returns:
        A configured PyIceberg Catalog instance.

    Raises:
        CatalogConnectionError: If the connection fails after all retries.
    """
    from prediction_data.core.config import get_settings

    settings = get_settings()
    resolved_region = region or settings.aws_region
    resolved_warehouse = warehouse or DEFAULT_WAREHOUSE.format(
        bucket=settings.silver_bucket
    )

    properties = _build_catalog_properties(
        warehouse=resolved_warehouse,
        region=resolved_region,
    )

    last_exc: Exception | None = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            catalog = GlueCatalog(CATALOG_NAME, **properties)
            logger.info(
                "Glue Catalog connected",
                warehouse=resolved_warehouse,
                region=resolved_region,
            )
            return catalog
        except Exception as exc:
            last_exc = exc
            if attempt < MAX_RETRIES:
                delay = RETRY_BASE_DELAY_S * (2 ** (attempt - 1))
                logger.warning(
                    "Glue Catalog connection failed, retrying",
                    attempt=attempt,
                    max_retries=MAX_RETRIES,
                    delay_s=delay,
                    error=str(exc),
                )
                time.sleep(delay)

    msg = f"Failed to connect to Glue Catalog after {MAX_RETRIES} attempts"
    raise CatalogConnectionError(msg) from last_exc


@lru_cache
def get_catalog() -> Catalog:
    """Get a cached Glue Catalog instance using default settings.

    Returns:
        A configured PyIceberg Catalog instance.
    """
    return load_catalog()
