#!/usr/bin/env python3
"""Derive or create Polymarket CLOB API credentials using your wallet private key.

Usage:
    python scripts/derive_clob_creds.py

Reads POLYGON_WALLET_PRIVATE_KEY from .env and prints the API credentials.
Use --create to create new credentials instead of deriving existing ones.
"""

import argparse
import os
import sys

from dotenv import load_dotenv
from py_clob_client.client import ClobClient

CLOB_HOST = "https://clob.polymarket.com"
CHAIN_ID = 137  # Polygon mainnet


def main() -> None:
    parser = argparse.ArgumentParser(description="Derive or create CLOB API credentials")
    parser.add_argument("--create", action="store_true", help="Create new creds instead of deriving")
    args = parser.parse_args()

    load_dotenv()
    private_key = os.environ.get("POLYGON_WALLET_PRIVATE_KEY")
    if not private_key:
        print("ERROR: POLYGON_WALLET_PRIVATE_KEY not set", file=sys.stderr)
        sys.exit(1)

    client = ClobClient(CLOB_HOST, chain_id=CHAIN_ID, key=private_key)

    if args.create:
        print("Creating new API credentials...")
        creds = client.create_api_key()
    else:
        print("Deriving existing API credentials...")
        creds = client.derive_api_key()

    print()
    print("Add these to your .env file:")
    print()
    print(f'POLYMARKET_BUILDER_API_KEY="{creds.api_key}"')
    print(f'POLYMARKET_BUILDER_SECRET="{creds.api_secret}"')
    print(f'POLYMARKET_BUILDER_PASSPHRASE="{creds.api_passphrase}"')


if __name__ == "__main__":
    main()
