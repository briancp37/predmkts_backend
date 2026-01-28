"""Manifest schema for Bronze layer storage contract."""

from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


class FileReference(BaseModel):
    """Reference to a file stored in S3.

    Attributes:
        bucket: S3 bucket name.
        key: S3 object key (path).
    """

    model_config = ConfigDict(frozen=True)

    bucket: str = Field(..., min_length=1, description="S3 bucket name")
    key: str = Field(..., min_length=1, description="S3 object key")


class Source(BaseModel):
    """Source metadata for ingested data.

    Tracks the API source and pagination state for the ingestion run.

    Attributes:
        api_base_url: Base URL of the source API.
        pagination: Pagination method used (e.g., "cursor", "offset", "none").
        cursor: Final cursor value after pagination completed, if applicable.
    """

    model_config = ConfigDict(frozen=True)

    api_base_url: str = Field(..., min_length=1, description="Base URL of the source API")
    pagination: str = Field(..., description="Pagination method used")
    cursor: str | None = Field(default=None, description="Final cursor value, if applicable")


class Manifest(BaseModel):
    """Manifest for a Bronze layer data partition.

    The manifest.json file is written alongside data files in each partition
    and provides metadata about the ingestion run, including the source,
    files written, and row counts.

    Attributes:
        run_id: Unique identifier for the ingestion run (UUID4).
        platform: Prediction market platform (e.g., "polymarket", "kalshi").
        entity: Entity type ingested (e.g., "markets", "trades").
        dt: Data partition date in YYYY-MM-DD format.
        generated_at: Timestamp when the manifest was generated (UTC).
        files: List of data files written in this partition.
        row_count: Total number of rows across all files.
        source: Source metadata for the ingestion.
    """

    model_config = ConfigDict(frozen=True)

    run_id: str = Field(..., min_length=1, description="Unique run identifier (UUID4)")
    platform: str = Field(..., min_length=1, description="Prediction market platform")
    entity: str = Field(..., min_length=1, description="Entity type ingested")
    dt: str = Field(..., pattern=r"^\d{4}-\d{2}-\d{2}$", description="Data partition date")
    generated_at: datetime = Field(..., description="Manifest generation timestamp (UTC)")
    files: list[FileReference] = Field(..., description="Data files in this partition")
    row_count: int = Field(..., ge=0, description="Total row count across all files")
    source: Source = Field(..., description="Source metadata")

    @field_validator("generated_at", mode="before")
    @classmethod
    def parse_datetime(cls, value: Any) -> datetime:
        """Parse datetime from string or return as-is if already datetime."""
        if isinstance(value, str):
            # Parse ISO-8601 format
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        if isinstance(value, datetime):
            return value
        raise ValueError(f"Expected datetime or ISO-8601 string, got {type(value)}")

    @field_validator("generated_at", mode="after")
    @classmethod
    def ensure_utc(cls, value: datetime) -> datetime:
        """Ensure generated_at has UTC timezone."""
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value

    def to_json(self) -> str:
        """Serialize manifest to JSON with ISO-8601 timestamps.

        Returns:
            JSON string representation of the manifest.
        """
        return self.model_dump_json(indent=2)

    def to_dict(self) -> dict[str, Any]:
        """Convert manifest to dictionary with ISO-8601 formatted timestamps.

        Returns:
            Dictionary representation suitable for JSON serialization.
        """
        data = self.model_dump(mode="json")
        return data

    @classmethod
    def from_json(cls, json_str: str) -> "Manifest":
        """Load and validate a manifest from JSON string.

        Args:
            json_str: JSON string to parse.

        Returns:
            Validated Manifest instance.

        Raises:
            pydantic.ValidationError: If the JSON is invalid or fails validation.
        """
        return cls.model_validate_json(json_str)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Manifest":
        """Load and validate a manifest from dictionary.

        Args:
            data: Dictionary to validate.

        Returns:
            Validated Manifest instance.

        Raises:
            pydantic.ValidationError: If the data fails validation.
        """
        return cls.model_validate(data)


def create_manifest(
    *,
    run_id: str,
    platform: str,
    entity: str,
    dt: str,
    bucket: str,
    key: str,
    row_count: int,
    api_base_url: str,
    pagination: str = "none",
    cursor: str | None = None,
    generated_at: datetime | None = None,
) -> Manifest:
    """Create a new manifest with a single data file.

    This is a convenience function for the common case of writing
    a single data file per partition.

    Args:
        run_id: Unique identifier for the ingestion run.
        platform: Prediction market platform.
        entity: Entity type ingested.
        dt: Data partition date in YYYY-MM-DD format.
        bucket: S3 bucket name.
        key: S3 object key for the data file.
        row_count: Number of rows in the data file.
        api_base_url: Base URL of the source API.
        pagination: Pagination method used.
        cursor: Final cursor value, if applicable.
        generated_at: Manifest generation timestamp (defaults to now).

    Returns:
        New Manifest instance.
    """
    if generated_at is None:
        generated_at = datetime.now(timezone.utc)

    return Manifest(
        run_id=run_id,
        platform=platform,
        entity=entity,
        dt=dt,
        generated_at=generated_at,
        files=[FileReference(bucket=bucket, key=key)],
        row_count=row_count,
        source=Source(
            api_base_url=api_base_url,
            pagination=pagination,
            cursor=cursor,
        ),
    )
