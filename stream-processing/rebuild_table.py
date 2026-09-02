#!/usr/bin/env python3
"""Automate the DROP-before-restart step that docs/TROUBLESHOOTING.md used to
document as a manual Athena command.

A restart of the stream processor without a checkpoint (resumeFromCheckpoint:
false) re-runs initialSync, which INSERTs the whole source collection again
without upserting. Every checkpoint-less restart therefore duplicates the
Iceberg table, unless it is dropped and rebuilt first. See
stream-processing/restart_processor.js and docs/TROUBLESHOOTING.md.

Usage:
    ./backend/venv/bin/python stream-processing/rebuild_table.py --auto-rebuild

Without --auto-rebuild this refuses to touch anything and prints the exact
manual command instead -- dropping a table is destructive against a real AWS
account, so it never happens implicitly.

This script only handles the Athena/Glue side (DROP TABLE via boto3, same
client pattern as backend/athena_side.py). It does not restart the stream
processor itself -- Atlas Stream Processing is only reachable from mongosh,
not from boto3/pymongo. After this script succeeds, run in mongosh:

    AUTO_REBUILD=1 mongosh "<workspace-uri>"
    load("stream-processing/restart_processor.js")
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1] / "backend"
sys.path.insert(0, str(BACKEND))

import athena_side  # noqa: E402
import settings  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--auto-rebuild",
        action="store_true",
        help="Actually run DROP TABLE against Athena/Glue. Without this flag, "
        "the script only prints instructions and exits non-zero.",
    )
    args = parser.parse_args()

    table = f"{settings.GLUE_DATABASE}.{settings.ICEBERG_TABLE}"

    if not args.auto_rebuild:
        print(
            "REFUSING to drop the Iceberg table without --auto-rebuild.\n\n"
            "A restart without a checkpoint duplicates every row already in "
            f"{table} (initialSync inserts, it does not upsert).\n\n"
            "To rebuild automatically:\n"
            "    ./backend/venv/bin/python stream-processing/rebuild_table.py --auto-rebuild\n\n"
            "To rebuild manually instead, run in Athena:\n"
            f"    DROP TABLE IF EXISTS {table}\n\n"
            "Either way, once the table is confirmed dropped, restart the "
            "processor with:\n"
            '    AUTO_REBUILD=1 mongosh "<workspace-uri>"\n'
            '    load("stream-processing/restart_processor.js")\n'
        )
        return 1

    print(f"Dropping {table} via Athena (this is destructive)...")
    try:
        result = athena_side.drop_table()
    except athena_side.AwsUnavailable as exc:
        print(f"FAILED: could not reach Athena/Glue: {exc}")
        return 1

    print(f"Dropped. query_id={result.get('query_id')} tempo_ms={result.get('tempo_ms')}")
    print("\nTable rebuilt. Now restart the processor:")
    print('    AUTO_REBUILD=1 mongosh "<workspace-uri>"')
    print('    load("stream-processing/restart_processor.js")')
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
