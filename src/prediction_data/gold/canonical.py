"""Cross-platform canonical market ID resolution.

Loads ``mappings/market_links.yaml`` and provides a lookup from
(platform, platform_market_id) → canonical_market_id.  When no explicit
mapping exists the platform-native ID is returned as-is (passthrough).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

_DEFAULT_YAML = Path(__file__).resolve().parents[3] / "mappings" / "market_links.yaml"


class CanonicalResolver:
    """Resolve platform market IDs to canonical IDs.

    Parameters
    ----------
    yaml_path:
        Path to the market_links.yaml file.  Defaults to the repo-root
        ``mappings/market_links.yaml``.
    """

    def __init__(self, yaml_path: Path | None = None) -> None:
        self._yaml_path = yaml_path or _DEFAULT_YAML
        # Keyed by (platform, platform_market_id) → canonical_market_id
        self._lookup: dict[tuple[str, str], str] = {}
        self._load()

    def _load(self) -> None:
        if not self._yaml_path.exists():
            return
        with open(self._yaml_path) as fh:
            data: dict[str, Any] = yaml.safe_load(fh) or {}
        raw_mappings: dict[str, dict[str, str]] = data.get("mappings", {})
        for canonical_id, platforms in raw_mappings.items():
            if not isinstance(platforms, dict):
                continue
            for platform, platform_market_id in platforms.items():
                self._lookup[(platform, str(platform_market_id))] = canonical_id

    def resolve(self, platform: str, platform_market_id: str) -> str:
        """Return the canonical market ID.

        Falls back to *platform_market_id* when no explicit mapping exists.
        """
        return self._lookup.get((platform, platform_market_id), platform_market_id)

    @property
    def mapped_count(self) -> int:
        """Number of explicit (platform, id) → canonical mappings loaded."""
        return len(self._lookup)
