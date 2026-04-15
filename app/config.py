"""Centralized configuration — reads .env, fails loudly if vars are missing."""

import os

from dotenv import load_dotenv

load_dotenv()


def _require(name: str) -> str:
    """Read an env var or crash at startup with a clear error."""
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


# Astra DB (vector knowledge base)
ASTRA_DB_ENDPOINT = _require("ASTRA_DB_ENDPOINT")
ASTRA_DB_TOKEN = _require("ASTRA_DB_TOKEN")
