"""Kalshi API authentication using RSA-PSS signatures."""

import base64
import time
from dataclasses import dataclass
from pathlib import Path

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa

from prediction_data.core.config import get_settings


class KalshiAuthError(Exception):
    """Raised when Kalshi authentication fails."""

    pass


@dataclass(frozen=True)
class KalshiCredentials:
    """Kalshi API credentials.

    Attributes:
        api_key_id: The Kalshi API key ID.
        private_key: The RSA private key for signing requests.
    """

    api_key_id: str
    private_key: rsa.RSAPrivateKey


def load_private_key(key_path: str | Path) -> rsa.RSAPrivateKey:
    """Load an RSA private key from a PEM file.

    Args:
        key_path: Path to the PEM file containing the private key.

    Returns:
        The loaded RSA private key.

    Raises:
        KalshiAuthError: If the key file cannot be read or parsed.
    """
    path = Path(key_path)

    if not path.exists():
        raise KalshiAuthError(f"Private key file not found: {path}")

    try:
        key_data = path.read_bytes()
        private_key = serialization.load_pem_private_key(key_data, password=None)

        if not isinstance(private_key, rsa.RSAPrivateKey):
            raise KalshiAuthError(
                f"Expected RSA private key, got {type(private_key).__name__}"
            )

        return private_key
    except Exception as e:
        if isinstance(e, KalshiAuthError):
            raise
        raise KalshiAuthError(f"Failed to load private key: {e}") from e


def load_credentials_from_settings() -> KalshiCredentials:
    """Load Kalshi credentials from application settings.

    Returns:
        KalshiCredentials loaded from environment variables.

    Raises:
        KalshiAuthError: If required credentials are not configured.
    """
    settings = get_settings()

    if not settings.kalshi_api_key_id:
        raise KalshiAuthError(
            "KALSHI_API_KEY_ID environment variable is not set"
        )

    if not settings.kalshi_private_key_path:
        raise KalshiAuthError(
            "KALSHI_PRIVATE_KEY_PATH environment variable is not set"
        )

    private_key = load_private_key(settings.kalshi_private_key_path)

    return KalshiCredentials(
        api_key_id=settings.kalshi_api_key_id,
        private_key=private_key,
    )


def sign_request(
    credentials: KalshiCredentials,
    timestamp_ms: int,
    method: str,
    path: str,
) -> str:
    """Generate RSA-PSS signature for a Kalshi API request.

    The signature is computed by:
    1. Concatenating: {timestamp_ms}{HTTP_METHOD}{path_without_query_params}
    2. Signing with RSA-PSS using SHA-256 and PSS padding
    3. Base64-encoding the result

    Args:
        credentials: The Kalshi credentials containing the private key.
        timestamp_ms: Request timestamp in milliseconds since epoch.
        method: HTTP method (GET, POST, etc.) in uppercase.
        path: API path without query parameters (e.g., /trade-api/v2/markets).

    Returns:
        Base64-encoded RSA-PSS signature.
    """
    # Build the message to sign: timestamp + method + path
    message = f"{timestamp_ms}{method.upper()}{path}"
    message_bytes = message.encode("utf-8")

    # Sign with RSA-PSS
    signature = credentials.private_key.sign(
        message_bytes,
        padding.PSS(
            mgf=padding.MGF1(hashes.SHA256()),
            salt_length=padding.PSS.MAX_LENGTH,
        ),
        hashes.SHA256(),
    )

    return base64.b64encode(signature).decode("utf-8")


def generate_auth_headers(
    credentials: KalshiCredentials,
    method: str,
    path: str,
    timestamp_ms: int | None = None,
) -> dict[str, str]:
    """Generate authentication headers for a Kalshi API request.

    Args:
        credentials: The Kalshi credentials.
        method: HTTP method (GET, POST, etc.).
        path: API path without query parameters.
        timestamp_ms: Request timestamp in milliseconds. If None, uses current time.

    Returns:
        Dictionary of authentication headers to include in the request.
    """
    if timestamp_ms is None:
        timestamp_ms = int(time.time() * 1000)

    signature = sign_request(credentials, timestamp_ms, method, path)

    return {
        "KALSHI-ACCESS-KEY": credentials.api_key_id,
        "KALSHI-ACCESS-TIMESTAMP": str(timestamp_ms),
        "KALSHI-ACCESS-SIGNATURE": signature,
    }
