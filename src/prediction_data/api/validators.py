"""Reusable Pydantic validators for API schemas."""

import re
from datetime import date, datetime
from typing import Annotated

from pydantic import AfterValidator, Field

# Ethereum address pattern: 0x followed by 40 hex characters
ETHEREUM_ADDRESS_PATTERN = re.compile(r"^0x[a-fA-F0-9]{40}$")

# Polymarket market ID pattern (condition ID format): 0x followed by 64 hex characters
# This is the keccak256 hash format used by Polymarket
MARKET_ID_PATTERN = re.compile(r"^0x[a-fA-F0-9]{64}$")

# ISO 8601 date pattern (YYYY-MM-DD)
DATE_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def validate_ethereum_address(value: str) -> str:
    """Validate Ethereum wallet address format.

    Args:
        value: Address string to validate

    Returns:
        Lowercase address if valid

    Raises:
        ValueError: If address format is invalid
    """
    if not ETHEREUM_ADDRESS_PATTERN.match(value):
        raise ValueError(
            "Invalid wallet address format. Must start with '0x' followed by 40 hex characters."
        )
    # Normalize to lowercase for consistency
    return value.lower()


def validate_market_id(value: str) -> str:
    """Validate Polymarket market/condition ID format.

    Args:
        value: Market ID string to validate

    Returns:
        Lowercase market ID if valid

    Raises:
        ValueError: If market ID format is invalid
    """
    if not MARKET_ID_PATTERN.match(value):
        raise ValueError(
            "Invalid market ID format. Must start with '0x' followed by 64 hex characters."
        )
    # Normalize to lowercase for consistency
    return value.lower()


def validate_date_string(value: str) -> str:
    """Validate ISO 8601 date string format (YYYY-MM-DD).

    Args:
        value: Date string to validate

    Returns:
        The validated date string

    Raises:
        ValueError: If date format is invalid or date is invalid
    """
    if not DATE_PATTERN.match(value):
        raise ValueError("Invalid date format. Expected YYYY-MM-DD.")

    # Validate it's an actual valid date
    try:
        datetime.strptime(value, "%Y-%m-%d")
    except ValueError:
        raise ValueError(f"Invalid date: {value}")

    return value


def validate_password_strength(value: str) -> str:
    """Validate password meets minimum strength requirements.

    Requirements:
    - Minimum 8 characters

    Args:
        value: Password to validate

    Returns:
        The password if valid

    Raises:
        ValueError: If password doesn't meet requirements
    """
    if len(value) < 8:
        raise ValueError("Password must be at least 8 characters long.")
    return value


def validate_date_range(start_date: str | None, end_date: str | None) -> bool:
    """Validate that start_date <= end_date when both are provided.

    Args:
        start_date: Start date string (YYYY-MM-DD)
        end_date: End date string (YYYY-MM-DD)

    Returns:
        True if valid

    Raises:
        ValueError: If start_date > end_date
    """
    if start_date is None or end_date is None:
        return True

    start = date.fromisoformat(start_date)
    end = date.fromisoformat(end_date)

    if start > end:
        raise ValueError("startDate must be before or equal to endDate.")

    return True


# Annotated types for reuse in schemas
EthereumAddress = Annotated[str, AfterValidator(validate_ethereum_address)]
MarketId = Annotated[str, AfterValidator(validate_market_id)]
DateString = Annotated[str, AfterValidator(validate_date_string)]
Password = Annotated[str, AfterValidator(validate_password_strength)]

# Field shortcuts with common constraints
PaginationLimit = Annotated[int, Field(ge=1, le=500)]
PaginationOffset = Annotated[int, Field(ge=0)]
