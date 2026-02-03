"""Compression and file format utilities for Bronze layer storage."""

import gzip
import io
import json
from collections.abc import Iterable, Iterator
from typing import Any


def serialize_jsonl(records: Iterable[dict[str, Any]]) -> Iterator[str]:
    """Serialize records to JSONL format (one JSON object per line).

    Args:
        records: Iterable of dictionaries to serialize.

    Yields:
        JSON strings, one per record, with newline terminators.
    """
    for record in records:
        yield json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n"


def serialize_jsonl_bytes(records: Iterable[dict[str, Any]]) -> Iterator[bytes]:
    """Serialize records to JSONL format as UTF-8 bytes.

    Args:
        records: Iterable of dictionaries to serialize.

    Yields:
        UTF-8 encoded bytes, one line per record, with newline terminators.
    """
    for line in serialize_jsonl(records):
        yield line.encode("utf-8")


def compress_gzip(data: bytes, *, compression_level: int = 9) -> bytes:
    """Compress data using gzip.

    Args:
        data: Bytes to compress.
        compression_level: Compression level (1-9, default 9 for best compression).

    Returns:
        Gzip-compressed bytes.
    """
    return gzip.compress(data, compresslevel=compression_level)


def decompress_gzip(data: bytes) -> bytes:
    """Decompress gzip data.

    Args:
        data: Gzip-compressed bytes.

    Returns:
        Decompressed bytes.
    """
    return gzip.decompress(data)


class JsonlGzipWriter:
    """Streaming writer for gzip-compressed JSONL data.

    This class enables streaming compression of large datasets without
    loading all data into memory at once.

    Example:
        writer = JsonlGzipWriter()
        for record in records:
            writer.write_record(record)
        compressed_data = writer.finish()
    """

    def __init__(self, *, compression_level: int = 9) -> None:
        """Initialize the writer.

        Args:
            compression_level: Compression level (1-9, default 9).
        """
        self._buffer = io.BytesIO()
        self._gzip_file = gzip.GzipFile(
            mode="wb",
            fileobj=self._buffer,
            compresslevel=compression_level,
        )
        self._row_count = 0
        self._finished = False

    def write_record(self, record: dict[str, Any]) -> None:
        """Write a single record to the compressed stream.

        Args:
            record: Dictionary to serialize and write.

        Raises:
            ValueError: If finish() has already been called.
        """
        if self._finished:
            raise ValueError("Cannot write to a finished writer")
        line = json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n"
        self._gzip_file.write(line.encode("utf-8"))
        self._row_count += 1

    def write_records(self, records: Iterable[dict[str, Any]]) -> int:
        """Write multiple records to the compressed stream.

        Args:
            records: Iterable of dictionaries to serialize and write.

        Returns:
            Number of records written.

        Raises:
            ValueError: If finish() has already been called.
        """
        count = 0
        for record in records:
            self.write_record(record)
            count += 1
        return count

    @property
    def row_count(self) -> int:
        """Get the number of rows written so far."""
        return self._row_count

    def finish(self) -> bytes:
        """Finish writing and return the compressed data.

        Returns:
            The complete gzip-compressed JSONL data.

        Raises:
            ValueError: If finish() has already been called.
        """
        if self._finished:
            raise ValueError("Writer has already been finished")
        self._gzip_file.close()
        self._finished = True
        return self._buffer.getvalue()


def compress_jsonl(
    records: Iterable[dict[str, Any]],
    *,
    compression_level: int = 9,
) -> tuple[bytes, int]:
    """Compress records as gzip-compressed JSONL.

    This is a convenience function that collects all records, serializes them
    to JSONL format, compresses with gzip, and returns the result along with
    the row count.

    For large datasets where memory is a concern, use JsonlGzipWriter instead.

    Args:
        records: Iterable of dictionaries to serialize and compress.
        compression_level: Compression level (1-9, default 9).

    Returns:
        Tuple of (compressed bytes, row count).
    """
    writer = JsonlGzipWriter(compression_level=compression_level)
    writer.write_records(records)
    return writer.finish(), writer.row_count


def decompress_jsonl(data: bytes) -> list[dict[str, Any]]:
    """Decompress and parse gzip-compressed JSONL data.

    Args:
        data: Gzip-compressed JSONL bytes.

    Returns:
        List of parsed dictionaries.

    Note:
        Uses split('\\n') instead of splitlines() because API data may contain
        Unicode line separators (U+2028, U+2029) inside JSON string values.
        These are valid JSON but splitlines() would incorrectly treat them as
        line boundaries.
    """
    decompressed = decompress_gzip(data)
    text = decompressed.decode("utf-8")
    records: list[dict[str, Any]] = []
    for line in text.split("\n"):
        if line.strip():
            records.append(json.loads(line))
    return records


def iter_jsonl(data: bytes) -> Iterator[dict[str, Any]]:
    """Iterate over gzip-compressed JSONL data.

    This is a memory-efficient alternative to decompress_jsonl when you
    don't need all records in memory at once.

    Args:
        data: Gzip-compressed JSONL bytes.

    Yields:
        Parsed dictionaries, one per line.

    Note:
        Uses split('\\n') instead of splitlines() because API data may contain
        Unicode line separators (U+2028, U+2029) inside JSON string values.
    """
    decompressed = decompress_gzip(data)
    text = decompressed.decode("utf-8")
    for line in text.split("\n"):
        if line.strip():
            yield json.loads(line)
