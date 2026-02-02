"""Tests for canonical market ID resolution."""

from __future__ import annotations

from pathlib import Path
from textwrap import dedent

import pytest

from prediction_data.gold.canonical import CanonicalResolver


@pytest.fixture()
def yaml_with_mappings(tmp_path: Path) -> Path:
    """Create a market_links.yaml with two canonical markets."""
    p = tmp_path / "market_links.yaml"
    p.write_text(
        dedent("""\
            mappings:
              us_presidential_2024:
                polymarket: "will-trump-win-2024"
                kalshi: "PRES-2024-DJT"
              btc_100k_2025:
                polymarket: "bitcoin-100k-by-2025"
        """)
    )
    return p


@pytest.fixture()
def empty_yaml(tmp_path: Path) -> Path:
    """Create a market_links.yaml with no mappings."""
    p = tmp_path / "market_links.yaml"
    p.write_text("mappings: {}\n")
    return p


class TestCanonicalResolver:
    """Core resolver behaviour."""

    def test_mapped_polymarket(self, yaml_with_mappings: Path) -> None:
        resolver = CanonicalResolver(yaml_path=yaml_with_mappings)
        assert resolver.resolve("polymarket", "will-trump-win-2024") == "us_presidential_2024"

    def test_mapped_kalshi(self, yaml_with_mappings: Path) -> None:
        resolver = CanonicalResolver(yaml_path=yaml_with_mappings)
        assert resolver.resolve("kalshi", "PRES-2024-DJT") == "us_presidential_2024"

    def test_unmapped_falls_back_to_native_id(self, yaml_with_mappings: Path) -> None:
        resolver = CanonicalResolver(yaml_path=yaml_with_mappings)
        assert resolver.resolve("polymarket", "unknown-market-xyz") == "unknown-market-xyz"

    def test_multi_platform_same_canonical(self, yaml_with_mappings: Path) -> None:
        resolver = CanonicalResolver(yaml_path=yaml_with_mappings)
        poly = resolver.resolve("polymarket", "will-trump-win-2024")
        kalshi = resolver.resolve("kalshi", "PRES-2024-DJT")
        assert poly == kalshi == "us_presidential_2024"

    def test_mapped_count(self, yaml_with_mappings: Path) -> None:
        resolver = CanonicalResolver(yaml_path=yaml_with_mappings)
        # 2 polymarket + 1 kalshi = 3 total mappings
        assert resolver.mapped_count == 3

    def test_empty_mappings(self, empty_yaml: Path) -> None:
        resolver = CanonicalResolver(yaml_path=empty_yaml)
        assert resolver.mapped_count == 0
        assert resolver.resolve("polymarket", "any-id") == "any-id"

    def test_missing_yaml_file(self, tmp_path: Path) -> None:
        resolver = CanonicalResolver(yaml_path=tmp_path / "nonexistent.yaml")
        assert resolver.mapped_count == 0
        assert resolver.resolve("kalshi", "TICKER") == "TICKER"
