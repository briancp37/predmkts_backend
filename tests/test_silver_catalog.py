"""Tests for Silver Iceberg catalog and table initialization."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from pyiceberg.schema import Schema
from pyiceberg.types import NestedField, StringType, TimestamptzType

from prediction_data.silver.catalog import (
    CATALOG_NAME,
    CatalogConnectionError,
    _build_catalog_properties,
    load_catalog,
)
from prediction_data.silver.tables import (
    SILVER_TABLES,
    TABLE_PROPERTIES,
    init_tables,
)


class TestBuildCatalogProperties:
    """Tests for _build_catalog_properties."""

    def test_returns_expected_keys(self) -> None:
        props = _build_catalog_properties(
            warehouse="s3://bucket/silver/", region="us-east-1"
        )
        assert props == {
            "type": "glue",
            "s3.region": "us-east-1",
            "glue.region": "us-east-1",
            "warehouse": "s3://bucket/silver/",
        }


class TestLoadCatalog:
    """Tests for load_catalog with mocked GlueCatalog."""

    @patch("prediction_data.silver.catalog.GlueCatalog")
    @patch("prediction_data.core.config.get_settings")
    def test_success_on_first_attempt(
        self, mock_settings: MagicMock, mock_glue: MagicMock
    ) -> None:
        mock_settings.return_value.aws_region = "us-east-1"
        mock_settings.return_value.silver_bucket = "test-bucket"
        mock_catalog = MagicMock()
        mock_glue.return_value = mock_catalog

        result = load_catalog()

        assert result is mock_catalog
        mock_glue.assert_called_once()

    @patch("prediction_data.silver.catalog.time.sleep")
    @patch("prediction_data.silver.catalog.GlueCatalog")
    @patch("prediction_data.core.config.get_settings")
    def test_retries_on_failure(
        self,
        mock_settings: MagicMock,
        mock_glue: MagicMock,
        mock_sleep: MagicMock,
    ) -> None:
        mock_settings.return_value.aws_region = "us-east-1"
        mock_settings.return_value.silver_bucket = "test-bucket"
        mock_catalog = MagicMock()
        mock_glue.side_effect = [RuntimeError("fail"), mock_catalog]

        result = load_catalog()

        assert result is mock_catalog
        assert mock_glue.call_count == 2
        mock_sleep.assert_called_once_with(1.0)

    @patch("prediction_data.silver.catalog.time.sleep")
    @patch("prediction_data.silver.catalog.GlueCatalog")
    @patch("prediction_data.core.config.get_settings")
    def test_raises_after_max_retries(
        self,
        mock_settings: MagicMock,
        mock_glue: MagicMock,
        mock_sleep: MagicMock,
    ) -> None:
        mock_settings.return_value.aws_region = "us-east-1"
        mock_settings.return_value.silver_bucket = "test-bucket"
        mock_glue.side_effect = RuntimeError("always fails")

        with pytest.raises(CatalogConnectionError, match="after 3 attempts"):
            load_catalog()

        assert mock_glue.call_count == 3


class TestInitTables:
    """Tests for init_tables."""

    def _make_mock_catalog(self) -> MagicMock:
        mock = MagicMock()
        # All tables "don't exist" — load_table raises
        mock.load_table.side_effect = Exception("NoSuchTableException")
        mock.create_table.return_value = MagicMock()
        return mock

    def test_creates_all_six_tables(self) -> None:
        catalog = self._make_mock_catalog()

        created = init_tables(catalog)

        assert len(created) == 6
        assert catalog.create_table.call_count == 6

    def test_dry_run_creates_nothing(self) -> None:
        catalog = self._make_mock_catalog()

        created = init_tables(catalog, dry_run=True)

        assert len(created) == 6
        catalog.create_table.assert_not_called()
        catalog.create_namespace.assert_not_called()

    def test_idempotent_skips_existing(self) -> None:
        catalog = MagicMock()
        # All tables already exist — load_table succeeds
        catalog.load_table.return_value = MagicMock()

        created = init_tables(catalog)

        assert len(created) == 0
        catalog.create_table.assert_not_called()

    def test_creates_namespace_before_table(self) -> None:
        catalog = self._make_mock_catalog()

        init_tables(catalog)

        # Should have attempted to create namespaces
        assert catalog.create_namespace.call_count > 0

    def test_table_properties_passed(self) -> None:
        catalog = self._make_mock_catalog()

        init_tables(catalog)

        call_kwargs = catalog.create_table.call_args_list[0].kwargs
        assert call_kwargs["properties"] == TABLE_PROPERTIES


class TestSilverTablesRegistry:
    """Tests for the SILVER_TABLES registry structure."""

    def test_has_six_tables(self) -> None:
        assert len(SILVER_TABLES) == 6

    def test_all_schemas_have_event_ts_first(self) -> None:
        for (ns, name), (schema, _sort) in SILVER_TABLES.items():
            first_field = schema.fields[0]
            assert first_field.name == "event_ts", f"{ns}.{name} missing event_ts as field 1"
            assert isinstance(first_field.field_type, TimestamptzType)

    def test_all_schemas_have_platform_id_second(self) -> None:
        for (ns, name), (schema, _sort) in SILVER_TABLES.items():
            second_field = schema.fields[1]
            assert second_field.name.startswith("platform_"), (
                f"{ns}.{name} field 2 should be platform ID"
            )

    def test_schema_roundtrip(self) -> None:
        """Verify schemas can be serialized and deserialized (round-trip)."""
        for (_ns, _name), (schema, _sort) in SILVER_TABLES.items():
            # Schema -> dict -> Schema (pyiceberg supports this)
            schema_dict = schema.model_dump()
            restored = Schema(**schema_dict)
            assert len(restored.fields) == len(schema.fields)
