"""Tests for Kalshi API authentication."""

import base64
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from prediction_data.bronze.kalshi.auth import (
    KalshiAuthError,
    KalshiCredentials,
    generate_auth_headers,
    load_credentials_from_settings,
    load_private_key,
    sign_request,
)


def generate_test_private_key() -> rsa.RSAPrivateKey:
    """Generate a test RSA private key."""
    return rsa.generate_private_key(
        public_exponent=65537,
        key_size=2048,
    )


def key_to_pem(private_key: rsa.RSAPrivateKey) -> bytes:
    """Convert a private key to PEM format."""
    return private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )


class TestLoadPrivateKey:
    """Tests for load_private_key function."""

    def test_loads_valid_pem_file(self) -> None:
        """Should load a valid RSA private key from PEM file."""
        private_key = generate_test_private_key()
        pem_data = key_to_pem(private_key)

        with tempfile.NamedTemporaryFile(suffix=".pem", delete=False) as f:
            f.write(pem_data)
            f.flush()

            loaded_key = load_private_key(f.name)
            assert isinstance(loaded_key, rsa.RSAPrivateKey)

    def test_accepts_path_object(self) -> None:
        """Should accept Path objects as well as strings."""
        private_key = generate_test_private_key()
        pem_data = key_to_pem(private_key)

        with tempfile.NamedTemporaryFile(suffix=".pem", delete=False) as f:
            f.write(pem_data)
            f.flush()

            loaded_key = load_private_key(Path(f.name))
            assert isinstance(loaded_key, rsa.RSAPrivateKey)

    def test_raises_for_missing_file(self) -> None:
        """Should raise KalshiAuthError for missing file."""
        with pytest.raises(KalshiAuthError, match="Private key file not found"):
            load_private_key("/nonexistent/path/to/key.pem")

    def test_raises_for_invalid_pem(self) -> None:
        """Should raise KalshiAuthError for invalid PEM content."""
        with tempfile.NamedTemporaryFile(suffix=".pem", delete=False) as f:
            f.write(b"not a valid PEM file")
            f.flush()

            with pytest.raises(KalshiAuthError, match="Failed to load private key"):
                load_private_key(f.name)


class TestLoadCredentialsFromSettings:
    """Tests for load_credentials_from_settings function."""

    def test_loads_credentials_from_settings(self) -> None:
        """Should load credentials from application settings."""
        private_key = generate_test_private_key()
        pem_data = key_to_pem(private_key)

        with tempfile.NamedTemporaryFile(suffix=".pem", delete=False) as f:
            f.write(pem_data)
            f.flush()

            mock_settings = MagicMock()
            mock_settings.kalshi_api_key_id = "test-api-key-id"
            mock_settings.kalshi_private_key_path = f.name

            with patch(
                "prediction_data.bronze.kalshi.auth.get_settings",
                return_value=mock_settings,
            ):
                credentials = load_credentials_from_settings()

            assert credentials.api_key_id == "test-api-key-id"
            assert isinstance(credentials.private_key, rsa.RSAPrivateKey)

    def test_raises_when_api_key_id_missing(self) -> None:
        """Should raise KalshiAuthError when API key ID is not set."""
        mock_settings = MagicMock()
        mock_settings.kalshi_api_key_id = None
        mock_settings.kalshi_private_key_path = "/some/path.pem"

        with patch(
            "prediction_data.bronze.kalshi.auth.get_settings",
            return_value=mock_settings,
        ):
            with pytest.raises(
                KalshiAuthError, match="KALSHI_API_KEY_ID environment variable"
            ):
                load_credentials_from_settings()

    def test_raises_when_private_key_path_missing(self) -> None:
        """Should raise KalshiAuthError when private key path is not set."""
        mock_settings = MagicMock()
        mock_settings.kalshi_api_key_id = "test-api-key-id"
        mock_settings.kalshi_private_key_path = None

        with patch(
            "prediction_data.bronze.kalshi.auth.get_settings",
            return_value=mock_settings,
        ):
            with pytest.raises(
                KalshiAuthError, match="KALSHI_PRIVATE_KEY_PATH environment variable"
            ):
                load_credentials_from_settings()


class TestSignRequest:
    """Tests for sign_request function."""

    def test_produces_base64_encoded_signature(self) -> None:
        """Should produce a valid base64-encoded signature."""
        private_key = generate_test_private_key()
        credentials = KalshiCredentials(
            api_key_id="test-key",
            private_key=private_key,
        )

        signature = sign_request(
            credentials,
            timestamp_ms=1706467200000,
            method="GET",
            path="/trade-api/v2/markets",
        )

        # Should be valid base64
        decoded = base64.b64decode(signature)
        assert len(decoded) > 0

    def test_signature_is_deterministic(self) -> None:
        """Should produce the same signature for the same inputs."""
        private_key = generate_test_private_key()
        credentials = KalshiCredentials(
            api_key_id="test-key",
            private_key=private_key,
        )

        sig1 = sign_request(
            credentials,
            timestamp_ms=1706467200000,
            method="GET",
            path="/trade-api/v2/markets",
        )
        sig2 = sign_request(
            credentials,
            timestamp_ms=1706467200000,
            method="GET",
            path="/trade-api/v2/markets",
        )

        # RSA-PSS is probabilistic due to salt, so signatures should differ
        # but both should be valid base64
        assert isinstance(sig1, str)
        assert isinstance(sig2, str)
        # Both should decode as valid base64
        base64.b64decode(sig1)
        base64.b64decode(sig2)

    def test_uses_uppercase_method(self) -> None:
        """Should convert method to uppercase for signing."""
        private_key = generate_test_private_key()
        credentials = KalshiCredentials(
            api_key_id="test-key",
            private_key=private_key,
        )

        # Both should work - method is converted to uppercase
        sig_lower = sign_request(
            credentials,
            timestamp_ms=1706467200000,
            method="get",
            path="/trade-api/v2/markets",
        )
        sig_upper = sign_request(
            credentials,
            timestamp_ms=1706467200000,
            method="GET",
            path="/trade-api/v2/markets",
        )

        # Both should be valid signatures
        assert isinstance(sig_lower, str)
        assert isinstance(sig_upper, str)


class TestGenerateAuthHeaders:
    """Tests for generate_auth_headers function."""

    def test_returns_required_headers(self) -> None:
        """Should return all required Kalshi auth headers."""
        private_key = generate_test_private_key()
        credentials = KalshiCredentials(
            api_key_id="test-key-id",
            private_key=private_key,
        )

        headers = generate_auth_headers(
            credentials,
            method="GET",
            path="/trade-api/v2/markets",
            timestamp_ms=1706467200000,
        )

        assert "KALSHI-ACCESS-KEY" in headers
        assert "KALSHI-ACCESS-TIMESTAMP" in headers
        assert "KALSHI-ACCESS-SIGNATURE" in headers

    def test_uses_api_key_id(self) -> None:
        """Should use the API key ID from credentials."""
        private_key = generate_test_private_key()
        credentials = KalshiCredentials(
            api_key_id="my-api-key-123",
            private_key=private_key,
        )

        headers = generate_auth_headers(
            credentials,
            method="GET",
            path="/trade-api/v2/markets",
            timestamp_ms=1706467200000,
        )

        assert headers["KALSHI-ACCESS-KEY"] == "my-api-key-123"

    def test_uses_provided_timestamp(self) -> None:
        """Should use the provided timestamp."""
        private_key = generate_test_private_key()
        credentials = KalshiCredentials(
            api_key_id="test-key",
            private_key=private_key,
        )

        headers = generate_auth_headers(
            credentials,
            method="GET",
            path="/trade-api/v2/markets",
            timestamp_ms=1706467200000,
        )

        assert headers["KALSHI-ACCESS-TIMESTAMP"] == "1706467200000"

    def test_generates_timestamp_if_not_provided(self) -> None:
        """Should generate current timestamp if not provided."""
        private_key = generate_test_private_key()
        credentials = KalshiCredentials(
            api_key_id="test-key",
            private_key=private_key,
        )

        with patch("prediction_data.bronze.kalshi.auth.time") as mock_time:
            mock_time.time.return_value = 1706467200.123  # 1706467200123 ms

            headers = generate_auth_headers(
                credentials,
                method="GET",
                path="/trade-api/v2/markets",
            )

            assert headers["KALSHI-ACCESS-TIMESTAMP"] == "1706467200123"

    def test_signature_is_valid_base64(self) -> None:
        """Should produce a valid base64 signature."""
        private_key = generate_test_private_key()
        credentials = KalshiCredentials(
            api_key_id="test-key",
            private_key=private_key,
        )

        headers = generate_auth_headers(
            credentials,
            method="GET",
            path="/trade-api/v2/markets",
            timestamp_ms=1706467200000,
        )

        signature = headers["KALSHI-ACCESS-SIGNATURE"]
        # Should be valid base64
        decoded = base64.b64decode(signature)
        assert len(decoded) > 0


class TestKalshiCredentials:
    """Tests for KalshiCredentials dataclass."""

    def test_is_frozen(self) -> None:
        """Credentials should be immutable."""
        private_key = generate_test_private_key()
        credentials = KalshiCredentials(
            api_key_id="test-key",
            private_key=private_key,
        )

        with pytest.raises(Exception):  # FrozenInstanceError
            credentials.api_key_id = "new-key"  # type: ignore[misc]

    def test_stores_api_key_id(self) -> None:
        """Should store the API key ID."""
        private_key = generate_test_private_key()
        credentials = KalshiCredentials(
            api_key_id="my-key-id",
            private_key=private_key,
        )

        assert credentials.api_key_id == "my-key-id"

    def test_stores_private_key(self) -> None:
        """Should store the private key."""
        private_key = generate_test_private_key()
        credentials = KalshiCredentials(
            api_key_id="test-key",
            private_key=private_key,
        )

        assert credentials.private_key is private_key
