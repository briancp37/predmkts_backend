"""Silver processing state management.

Tracks which Bronze manifests have been processed to Silver, enabling
idempotent reprocessing. State is stored as a JSONL log in S3 at:

    silver/_state/{platform}/{entity}/processed.jsonl

Each line is a JSON object recording a processed manifest.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

import structlog

if TYPE_CHECKING:
    from prediction_data.storage.s3 import S3Client

logger = structlog.stdlib.get_logger(__name__)


@dataclass(frozen=True, slots=True)
class ProcessedEntry:
    """Record of a processed Bronze manifest."""

    run_id: str
    platform: str
    entity: str
    dt: str
    processed_at: str  # ISO-8601

    def to_json_line(self) -> str:
        return json.dumps(
            {
                "run_id": self.run_id,
                "platform": self.platform,
                "entity": self.entity,
                "dt": self.dt,
                "processed_at": self.processed_at,
            },
            separators=(",", ":"),
        )

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> ProcessedEntry:
        return cls(
            run_id=d["run_id"],
            platform=d["platform"],
            entity=d["entity"],
            dt=d["dt"],
            processed_at=d["processed_at"],
        )


def _state_key(platform: str, entity: str) -> str:
    """Build the S3 key for the state log."""
    return f"silver/_state/{platform}/{entity}/processed.jsonl"


class SilverStateStore:
    """Track which Bronze manifests have been processed to Silver.

    Reads the full state log on init, then supports append-only writes.
    """

    def __init__(
        self,
        s3_client: S3Client,
        platform: str,
        entity: str,
    ) -> None:
        self._s3 = s3_client
        self._platform = platform
        self._entity = entity
        self._key = _state_key(platform, entity)
        self._processed_run_ids: set[str] = set()
        self._loaded = False

    async def load(self) -> None:
        """Load existing state from S3."""
        try:
            client = self._s3._get_client()
            response = client.get_object(Bucket=self._s3.bucket, Key=self._key)
            body = response["Body"].read().decode("utf-8")
            for line in body.strip().splitlines():
                if line.strip():
                    entry = json.loads(line)
                    self._processed_run_ids.add(entry["run_id"])
        except client.exceptions.NoSuchKey:
            pass
        except Exception:
            # If the key doesn't exist, botocore raises ClientError
            # with Code='NoSuchKey'. Handle both.
            logger.debug("state_load_no_file", key=self._key)

        self._loaded = True
        logger.info(
            "state_loaded",
            platform=self._platform,
            entity=self._entity,
            processed_count=len(self._processed_run_ids),
        )

    def is_processed(self, run_id: str) -> bool:
        """Check if a manifest run_id has already been processed."""
        if not self._loaded:
            raise RuntimeError("State not loaded. Call load() first.")
        return run_id in self._processed_run_ids

    async def mark_processed(
        self,
        run_id: str,
        platform: str,
        entity: str,
        dt: str,
    ) -> None:
        """Append a processed entry to the state log in S3.

        This reads the current file, appends the new entry, and writes
        back. This is safe for single-writer scenarios.
        """
        entry = ProcessedEntry(
            run_id=run_id,
            platform=platform,
            entity=entity,
            dt=dt,
            processed_at=datetime.now(UTC).isoformat(),
        )

        # Read existing content
        existing = ""
        try:
            client = self._s3._get_client()
            response = client.get_object(Bucket=self._s3.bucket, Key=self._key)
            existing = response["Body"].read().decode("utf-8")
        except Exception:
            pass

        # Append new entry
        new_content = existing.rstrip("\n")
        if new_content:
            new_content += "\n"
        new_content += entry.to_json_line() + "\n"

        # Write back
        client = self._s3._get_client()
        client.put_object(
            Bucket=self._s3.bucket,
            Key=self._key,
            Body=new_content.encode("utf-8"),
            ContentType="application/x-ndjson",
        )

        self._processed_run_ids.add(run_id)

        logger.info(
            "state_marked_processed",
            run_id=run_id,
            platform=platform,
            entity=entity,
            dt=dt,
        )
