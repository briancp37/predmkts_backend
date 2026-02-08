"""Tag-related business logic and ClickHouse queries."""

from typing import Any

from clickhouse_connect.driver.client import Client

from prediction_data.api.clickhouse import execute_query


async def get_event_tags(
    client: Client,
) -> list[dict[str, Any]]:
    """Fetch all unique event tags with their event counts.

    Queries the tags array column in dim_event using ARRAY JOIN to flatten
    the tags and count occurrences.

    Args:
        client: ClickHouse client.

    Returns:
        List of tag dicts formatted for EventTagResponse (label, slug, eventCount).
        Ordered by eventCount descending.
    """
    query = """
        SELECT
            tag AS label,
            COUNT() AS event_count
        FROM prediction_gold.dim_event
        ARRAY JOIN tags AS tag
        WHERE tag != ''
        GROUP BY tag
        ORDER BY event_count DESC
    """

    rows = await execute_query(query, {}, client=client)

    results: list[dict[str, Any]] = []
    for row in rows:
        label = row.get("label") or ""
        if not label:
            continue

        # Generate slug: lowercase, replace spaces with hyphens, remove special chars
        slug = label.lower().replace(" ", "-").replace("&", "and")
        slug = "".join(c for c in slug if c.isalnum() or c == "-")

        results.append({
            "label": label,
            "slug": slug,
            "eventCount": int(row.get("event_count", 0)),
        })

    return results
