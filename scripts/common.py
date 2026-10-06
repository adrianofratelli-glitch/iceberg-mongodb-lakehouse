from __future__ import annotations

import os
import sys
from pathlib import Path
from datetime import datetime, timezone
from pymongo import MongoClient

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _load_config():
    """Import config with a readable error when .env is missing or incomplete."""
    try:
        from config import MONGODB_URI, DATABASE_NAME, COLLECTION_NAME
    except KeyError:
        raise SystemExit(
            "MONGODB_URI is not set.\n"
            "Copy .env.example to .env and fill in the connection string:\n"
            "    cp .env.example .env"
        )
    return MONGODB_URI, DATABASE_NAME, COLLECTION_NAME


MONGODB_URI, DATABASE_NAME, COLLECTION_NAME = _load_config()

PLACEHOLDERS = ("<username>", "<password>", "<cluster>", "xxxxx")


def validate_config() -> None:
    if not MONGODB_URI.strip():
        raise SystemExit("MONGODB_URI is empty. Fill it in .env before running the demo.")
    if any(token in MONGODB_URI for token in PLACEHOLDERS):
        raise SystemExit(
            "MONGODB_URI still contains placeholders from .env.example.\n"
            "Edit .env and set the real connection string."
        )


def assert_safe_target(db_name: str | None = None) -> None:
    """Refuse to write to the demo database unless explicitly allowed.

    Any database ending in ``_test`` is always writable. Anything else (the
    demo's ``iceberg_demo``) needs ALLOW_DEMO_DB_WRITE=1, so a test run with a
    forgotten DATABASE_NAME override can never rewrite what the audience sees.
    """
    name = db_name or DATABASE_NAME
    if name.endswith("_test") or os.getenv("ALLOW_DEMO_DB_WRITE") == "1":
        return
    raise SystemExit(
        f"Refusing to write to '{name}' (the demo database).\n"
        "Use DATABASE_NAME=<name>_test for tests, or set ALLOW_DEMO_DB_WRITE=1 "
        "to reset the demo on purpose."
    )


def get_collection():
    validate_config()
    client = MongoClient(MONGODB_URI, serverSelectionTimeoutMS=10000)
    client.admin.command("ping")
    return client, client[DATABASE_NAME][COLLECTION_NAME]


def utcnow() -> datetime:
    return datetime.now(timezone.utc)
