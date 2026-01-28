"""Run ID generation and tracking for idempotent ingestion."""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from uuid import uuid4

import structlog

from prediction_data.core.logging import bind_context


def _generate_run_id() -> str:
    """Generate a new UUID4 run_id."""
    return str(uuid4())


def _utc_now() -> datetime:
    """Get current UTC timestamp."""
    return datetime.now(timezone.utc)


@dataclass
class RunContext:
    """Context for a single ingestion run.

    Tracks run_id, timestamps, and provides helpers for S3 key formatting
    and structlog binding.

    Attributes:
        run_id: Unique identifier for this run (UUID4).
        platform: The prediction market platform (e.g., "polymarket", "kalshi").
        entity: The entity type being ingested (e.g., "markets", "trades").
        start_time: When the run started (UTC).
        end_time: When the run ended (UTC), None if still running.
    """

    platform: str
    entity: str
    run_id: str = field(default_factory=_generate_run_id)
    start_time: datetime = field(default_factory=_utc_now)
    end_time: datetime | None = field(default=None)

    def format_s3_key_prefix(self, dt: str) -> str:
        """Format the S3 key prefix for Bronze layer storage.

        Args:
            dt: The data timestamp in YYYY-MM-DD format.

        Returns:
            S3 key prefix in format: bronze/{platform}/{entity}/dt={dt}/run_id={run_id}/
        """
        return f"bronze/{self.platform}/{self.entity}/dt={dt}/run_id={self.run_id}/"

    def bind_to_logger(self, dt: str | None = None) -> None:
        """Bind run context to structlog for all subsequent log messages.

        Args:
            dt: Optional data timestamp to include in log context.
        """
        bind_context(
            platform=self.platform,
            entity=self.entity,
            run_id=self.run_id,
            dt=dt,
        )

    def mark_complete(self) -> None:
        """Mark the run as complete by setting end_time."""
        self.end_time = _utc_now()

    @property
    def duration_seconds(self) -> float | None:
        """Get the run duration in seconds, or None if still running."""
        if self.end_time is None:
            return None
        return (self.end_time - self.start_time).total_seconds()

    def log_start(self, logger: structlog.stdlib.BoundLogger | None = None) -> None:
        """Log the start of this run.

        Args:
            logger: Optional logger to use. If None, creates one.
        """
        if logger is None:
            logger = structlog.stdlib.get_logger(__name__)
        logger.info(
            "Run started",
            run_id=self.run_id,
            platform=self.platform,
            entity=self.entity,
            start_time=self.start_time.isoformat(),
        )

    def log_end(self, logger: structlog.stdlib.BoundLogger | None = None) -> None:
        """Log the end of this run.

        Args:
            logger: Optional logger to use. If None, creates one.
        """
        if logger is None:
            logger = structlog.stdlib.get_logger(__name__)
        logger.info(
            "Run completed",
            run_id=self.run_id,
            platform=self.platform,
            entity=self.entity,
            start_time=self.start_time.isoformat(),
            end_time=self.end_time.isoformat() if self.end_time else None,
            duration_seconds=self.duration_seconds,
        )
