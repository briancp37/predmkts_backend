"""Tests for compression and file format utilities."""

import gzip
import json

import pytest

from prediction_data.core.compression import (
    JsonlGzipWriter,
    compress_gzip,
    compress_jsonl,
    decompress_gzip,
    decompress_jsonl,
    iter_jsonl,
    serialize_jsonl,
    serialize_jsonl_bytes,
)


class TestSerializeJsonl:
    """Tests for JSONL serialization functions."""

    def test_serialize_empty_records(self) -> None:
        """Empty input produces no output."""
        result = list(serialize_jsonl([]))
        assert result == []

    def test_serialize_single_record(self) -> None:
        """Single record serializes to one line with newline."""
        records = [{"id": 1, "name": "test"}]
        result = list(serialize_jsonl(records))
        assert len(result) == 1
        assert result[0].endswith("\n")
        parsed = json.loads(result[0])
        assert parsed == {"id": 1, "name": "test"}

    def test_serialize_multiple_records(self) -> None:
        """Multiple records serialize to multiple lines."""
        records = [{"id": 1}, {"id": 2}, {"id": 3}]
        result = list(serialize_jsonl(records))
        assert len(result) == 3
        for i, line in enumerate(result, 1):
            assert json.loads(line) == {"id": i}

    def test_serialize_unicode_content(self) -> None:
        """Unicode content is preserved in serialization."""
        records = [{"name": "日本語", "emoji": "🎉"}]
        result = list(serialize_jsonl(records))
        parsed = json.loads(result[0])
        assert parsed["name"] == "日本語"
        assert parsed["emoji"] == "🎉"

    def test_serialize_compact_format(self) -> None:
        """Output uses compact JSON format (no extra spaces)."""
        records = [{"key": "value", "num": 123}]
        result = list(serialize_jsonl(records))
        # Compact format has no spaces after separators
        assert '{"key":"value","num":123}\n' == result[0]

    def test_serialize_nested_structures(self) -> None:
        """Nested dicts and lists are properly serialized."""
        records = [{"nested": {"key": "value"}, "list": [1, 2, 3]}]
        result = list(serialize_jsonl(records))
        parsed = json.loads(result[0])
        assert parsed["nested"]["key"] == "value"
        assert parsed["list"] == [1, 2, 3]


class TestSerializeJsonlBytes:
    """Tests for JSONL byte serialization."""

    def test_serialize_to_bytes(self) -> None:
        """Records are serialized as UTF-8 bytes."""
        records = [{"id": 1}]
        result = list(serialize_jsonl_bytes(records))
        assert len(result) == 1
        assert isinstance(result[0], bytes)
        assert result[0] == b'{"id":1}\n'

    def test_serialize_unicode_to_bytes(self) -> None:
        """Unicode is properly encoded as UTF-8 bytes."""
        records = [{"name": "日本語"}]
        result = list(serialize_jsonl_bytes(records))
        decoded = result[0].decode("utf-8")
        parsed = json.loads(decoded)
        assert parsed["name"] == "日本語"


class TestGzipCompression:
    """Tests for gzip compression and decompression."""

    def test_compress_decompress_roundtrip(self) -> None:
        """Compression followed by decompression returns original data."""
        original = b"Hello, World! This is test data."
        compressed = compress_gzip(original)
        decompressed = decompress_gzip(compressed)
        assert decompressed == original

    def test_compressed_is_smaller(self) -> None:
        """Compression reduces size for compressible data."""
        original = b"AAAAAAAAAA" * 1000  # Highly compressible
        compressed = compress_gzip(original)
        assert len(compressed) < len(original)

    def test_compress_empty_data(self) -> None:
        """Empty data can be compressed and decompressed."""
        original = b""
        compressed = compress_gzip(original)
        decompressed = decompress_gzip(compressed)
        assert decompressed == original

    def test_compression_level_affects_size(self) -> None:
        """Higher compression levels produce smaller output."""
        data = b"Compressible data pattern " * 100
        low_compression = compress_gzip(data, compression_level=1)
        high_compression = compress_gzip(data, compression_level=9)
        # High compression should be smaller or equal
        assert len(high_compression) <= len(low_compression)

    def test_decompress_invalid_data_raises(self) -> None:
        """Decompressing non-gzip data raises an error."""
        with pytest.raises(gzip.BadGzipFile):
            decompress_gzip(b"not gzip data")


class TestJsonlGzipWriter:
    """Tests for the streaming JsonlGzipWriter."""

    def test_write_single_record(self) -> None:
        """Writing a single record produces valid compressed JSONL."""
        writer = JsonlGzipWriter()
        writer.write_record({"id": 1})
        data = writer.finish()

        # Decompress and verify
        decompressed = gzip.decompress(data)
        assert decompressed == b'{"id":1}\n'

    def test_write_multiple_records(self) -> None:
        """Writing multiple records produces valid compressed JSONL."""
        writer = JsonlGzipWriter()
        writer.write_record({"id": 1})
        writer.write_record({"id": 2})
        writer.write_record({"id": 3})
        data = writer.finish()

        decompressed = gzip.decompress(data)
        lines = decompressed.decode("utf-8").strip().split("\n")
        assert len(lines) == 3

    def test_write_records_batch(self) -> None:
        """write_records handles batches and returns count."""
        writer = JsonlGzipWriter()
        count = writer.write_records([{"id": i} for i in range(5)])
        assert count == 5
        assert writer.row_count == 5

    def test_row_count_tracking(self) -> None:
        """Row count is tracked correctly."""
        writer = JsonlGzipWriter()
        assert writer.row_count == 0
        writer.write_record({"id": 1})
        assert writer.row_count == 1
        writer.write_record({"id": 2})
        assert writer.row_count == 2
        writer.write_records([{"id": 3}, {"id": 4}])
        assert writer.row_count == 4

    def test_write_after_finish_raises(self) -> None:
        """Writing after finish() raises an error."""
        writer = JsonlGzipWriter()
        writer.write_record({"id": 1})
        writer.finish()

        with pytest.raises(ValueError, match="Cannot write to a finished writer"):
            writer.write_record({"id": 2})

    def test_double_finish_raises(self) -> None:
        """Calling finish() twice raises an error."""
        writer = JsonlGzipWriter()
        writer.write_record({"id": 1})
        writer.finish()

        with pytest.raises(ValueError, match="already been finished"):
            writer.finish()

    def test_unicode_in_streaming(self) -> None:
        """Unicode is properly handled in streaming mode."""
        writer = JsonlGzipWriter()
        writer.write_record({"name": "日本語", "emoji": "🎉"})
        data = writer.finish()

        decompressed = gzip.decompress(data)
        parsed = json.loads(decompressed.decode("utf-8"))
        assert parsed["name"] == "日本語"
        assert parsed["emoji"] == "🎉"


class TestCompressJsonl:
    """Tests for the compress_jsonl convenience function."""

    def test_compress_and_count(self) -> None:
        """compress_jsonl returns compressed data and row count."""
        records = [{"id": i} for i in range(10)]
        data, count = compress_jsonl(records)

        assert count == 10
        assert isinstance(data, bytes)

        # Verify content
        decompressed = gzip.decompress(data)
        lines = decompressed.decode("utf-8").strip().split("\n")
        assert len(lines) == 10

    def test_compress_empty_records(self) -> None:
        """Empty records produce valid gzip with zero count."""
        data, count = compress_jsonl([])
        assert count == 0
        assert isinstance(data, bytes)
        # Should still be valid gzip
        decompressed = gzip.decompress(data)
        assert decompressed == b""


class TestDecompressJsonl:
    """Tests for decompress_jsonl function."""

    def test_decompress_and_parse(self) -> None:
        """decompress_jsonl returns parsed records."""
        # Create compressed JSONL
        original = [{"id": 1, "name": "first"}, {"id": 2, "name": "second"}]
        jsonl = "\n".join(json.dumps(r) for r in original) + "\n"
        compressed = gzip.compress(jsonl.encode("utf-8"))

        # Decompress and parse
        result = decompress_jsonl(compressed)
        assert result == original

    def test_handles_blank_lines(self) -> None:
        """Blank lines in JSONL are skipped."""
        jsonl = '{"id":1}\n\n{"id":2}\n'
        compressed = gzip.compress(jsonl.encode("utf-8"))

        result = decompress_jsonl(compressed)
        assert len(result) == 2
        assert result[0]["id"] == 1
        assert result[1]["id"] == 2

    def test_unicode_line_separator_u2028_preserved(self) -> None:
        """U+2028 inside JSON string values must not cause extra splits.

        The Gamma API embeds U+2028 (LINE SEPARATOR) inside market question
        fields.  Using splitlines() would incorrectly break the JSON line at
        that character; split('\\n') does not.
        """
        record = {"id": 1, "question": "Will X happen?\u2028Details here."}
        jsonl = json.dumps(record, ensure_ascii=False) + "\n"
        compressed = gzip.compress(jsonl.encode("utf-8"))

        result = decompress_jsonl(compressed)
        assert len(result) == 1
        assert result[0]["question"] == "Will X happen?\u2028Details here."

    def test_unicode_paragraph_separator_u2029_preserved(self) -> None:
        """U+2029 inside JSON string values must not cause extra splits."""
        record = {"id": 2, "description": "Paragraph one.\u2029Paragraph two."}
        jsonl = json.dumps(record, ensure_ascii=False) + "\n"
        compressed = gzip.compress(jsonl.encode("utf-8"))

        result = decompress_jsonl(compressed)
        assert len(result) == 1
        assert result[0]["description"] == "Paragraph one.\u2029Paragraph two."

    def test_multiple_records_with_u2028_and_u2029(self) -> None:
        """Multiple records containing U+2028/U+2029 are parsed correctly."""
        records = [
            {"id": 1, "text": "line\u2028break"},
            {"id": 2, "text": "para\u2029break"},
            {"id": 3, "text": "both\u2028and\u2029here"},
        ]
        jsonl = "\n".join(json.dumps(r, ensure_ascii=False) for r in records) + "\n"
        compressed = gzip.compress(jsonl.encode("utf-8"))

        result = decompress_jsonl(compressed)
        assert len(result) == 3
        assert result[0]["text"] == "line\u2028break"
        assert result[1]["text"] == "para\u2029break"
        assert result[2]["text"] == "both\u2028and\u2029here"


class TestIterJsonl:
    """Tests for iter_jsonl streaming decompression."""

    def test_iterate_records(self) -> None:
        """iter_jsonl yields records one at a time."""
        original = [{"id": i} for i in range(5)]
        data, _ = compress_jsonl(original)

        result = list(iter_jsonl(data))
        assert result == original

    def test_memory_efficient_iteration(self) -> None:
        """iter_jsonl can process records without loading all into memory."""
        # Create a larger dataset
        original = [{"id": i, "data": "x" * 100} for i in range(100)]
        data, _ = compress_jsonl(original)

        # Iterate and verify we can stop early
        count = 0
        for record in iter_jsonl(data):
            count += 1
            if count >= 10:
                break

        assert count == 10

    def test_unicode_line_separator_u2028_preserved(self) -> None:
        """iter_jsonl handles U+2028 inside JSON string values correctly."""
        record = {"id": 1, "question": "Will X happen?\u2028Details here."}
        jsonl = json.dumps(record, ensure_ascii=False) + "\n"
        compressed = gzip.compress(jsonl.encode("utf-8"))

        result = list(iter_jsonl(compressed))
        assert len(result) == 1
        assert result[0]["question"] == "Will X happen?\u2028Details here."

    def test_unicode_paragraph_separator_u2029_preserved(self) -> None:
        """iter_jsonl handles U+2029 inside JSON string values correctly."""
        record = {"id": 2, "description": "Paragraph one.\u2029Paragraph two."}
        jsonl = json.dumps(record, ensure_ascii=False) + "\n"
        compressed = gzip.compress(jsonl.encode("utf-8"))

        result = list(iter_jsonl(compressed))
        assert len(result) == 1
        assert result[0]["description"] == "Paragraph one.\u2029Paragraph two."


class TestRoundTrip:
    """End-to-end roundtrip tests."""

    def test_full_roundtrip(self) -> None:
        """Data survives full serialization and deserialization cycle."""
        original = [
            {"id": 1, "name": "Test", "value": 123.45},
            {"id": 2, "nested": {"key": "value"}},
            {"id": 3, "list": [1, 2, 3], "unicode": "日本語"},
        ]

        # Compress
        data, count = compress_jsonl(original)
        assert count == 3

        # Decompress
        result = decompress_jsonl(data)
        assert result == original

    def test_large_dataset_roundtrip(self) -> None:
        """Large datasets survive roundtrip."""
        # 1000 records with various data
        original = [
            {"id": i, "data": f"record_{i}" * 10, "value": i * 1.5}
            for i in range(1000)
        ]

        data, count = compress_jsonl(original)
        assert count == 1000

        result = decompress_jsonl(data)
        assert len(result) == 1000
        assert result[0]["id"] == 0
        assert result[999]["id"] == 999
