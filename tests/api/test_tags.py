"""Tests for the tags API endpoint."""

from unittest.mock import MagicMock

import pytest

from tests.api.conftest import make_mock_ch_response


class TestListTags:
    """Tests for GET /api/v1/tags endpoint."""

    @pytest.mark.asyncio
    async def test_list_tags_success(
        self, client, mock_clickhouse_client: MagicMock
    ) -> None:
        """Test successful tag listing."""
        # Mock ClickHouse response with sample tags
        mock_clickhouse_client.query.return_value = make_mock_ch_response(
            columns=["label", "event_count"],
            rows=[
                ("Sports", 1250),
                ("Politics", 980),
                ("Crypto", 750),
            ],
        )

        response = await client.get("/api/v1/tags")

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) == 3

        # Check first tag (Sports)
        assert data[0]["label"] == "Sports"
        assert data[0]["slug"] == "sports"
        assert data[0]["eventCount"] == 1250

        # Check second tag (Politics)
        assert data[1]["label"] == "Politics"
        assert data[1]["slug"] == "politics"
        assert data[1]["eventCount"] == 980

        # Check third tag (Crypto)
        assert data[2]["label"] == "Crypto"
        assert data[2]["slug"] == "crypto"
        assert data[2]["eventCount"] == 750

    @pytest.mark.asyncio
    async def test_list_tags_empty(
        self, client, mock_clickhouse_client: MagicMock
    ) -> None:
        """Test tag listing when no tags exist."""
        mock_clickhouse_client.query.return_value = make_mock_ch_response(
            columns=["label", "event_count"],
            rows=[],
        )

        response = await client.get("/api/v1/tags")

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) == 0

    @pytest.mark.asyncio
    async def test_list_tags_slug_generation(
        self, client, mock_clickhouse_client: MagicMock
    ) -> None:
        """Test that slugs are generated correctly from labels."""
        mock_clickhouse_client.query.return_value = make_mock_ch_response(
            columns=["label", "event_count"],
            rows=[
                ("Science & Technology", 100),
                ("Pop Culture", 50),
                ("Breaking News!", 25),
            ],
        )

        response = await client.get("/api/v1/tags")

        assert response.status_code == 200
        data = response.json()

        # "Science & Technology" -> "science-and-technology"
        assert data[0]["slug"] == "science-and-technology"

        # "Pop Culture" -> "pop-culture"
        assert data[1]["slug"] == "pop-culture"

        # "Breaking News!" -> "breaking-news" (special chars removed)
        assert data[2]["slug"] == "breaking-news"

    @pytest.mark.asyncio
    async def test_list_tags_filters_empty_labels(
        self, client, mock_clickhouse_client: MagicMock
    ) -> None:
        """Test that empty labels are filtered out."""
        mock_clickhouse_client.query.return_value = make_mock_ch_response(
            columns=["label", "event_count"],
            rows=[
                ("Sports", 100),
                ("", 50),  # Empty label should be filtered
                ("Politics", 25),
            ],
        )

        response = await client.get("/api/v1/tags")

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 2
        labels = [t["label"] for t in data]
        assert "" not in labels
