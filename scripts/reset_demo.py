"""Put the demo back exactly where it starts: one command, idempotent.

What it does, in order, on DATABASE_NAME.COLLECTION_NAME:
  1. creates the collection when missing and makes sure
     changeStreamPreAndPostImages is enabled (without it the processor dies on
     the first UPDATE);
  2. removes the live demo documents (PED-AOVIVO-*) and any other document
     that is not part of the deterministic seed;
  3. upserts the 5,000 seeded orders (no-op for documents already identical,
     so an already-clean demo produces no change events);
  4. empties the dead-letter queue.

The Iceberg table is NOT touched: every change above is a normal write, so the
stream processor carries it to the lake by itself (deletes included). That is
the point of the demo. Rebuilding the table from scratch is a separate,
destructive path: stream-processing/rebuild_table.py --auto-rebuild followed by
restart_processor.js (see docs/TROUBLESHOOTING.md).

Safety: any database ending in ``_test`` is writable. The demo database needs
ALLOW_DEMO_DB_WRITE=1:

    ALLOW_DEMO_DB_WRITE=1 ./.venv/bin/python scripts/reset_demo.py
    DATABASE_NAME=iceberg_demo_test ./.venv/bin/python scripts/reset_demo.py
"""

from __future__ import annotations

import argparse

from common import assert_safe_target, get_collection
from seed_orders import SEED_COUNT, seed, seed_ids

LIVE_IDS = ["PED-AOVIVO-001", "PED-AOVIVO-002"]
DLQ_COLLECTION = "dlq"


def ensure_collection(client, db_name: str, coll_name: str) -> str:
    db = client[db_name]
    info = next(db.list_collections(filter={"name": coll_name}), None)
    if info is None:
        db.create_collection(coll_name, changeStreamPreAndPostImages={"enabled": True})
        return "created with changeStreamPreAndPostImages"
    enabled = info.get("options", {}).get("changeStreamPreAndPostImages", {}).get("enabled", False)
    if not enabled:
        db.command({"collMod": coll_name, "changeStreamPreAndPostImages": {"enabled": True}})
        return "changeStreamPreAndPostImages enabled now (restart the processor without checkpoint)"
    return "changeStreamPreAndPostImages already enabled"


def reset(client, coll) -> dict:
    db_name, coll_name = coll.database.name, coll.name
    images = ensure_collection(client, db_name, coll_name)
    expected = seed_ids()
    live = coll.delete_many({"_id": {"$in": LIVE_IDS}}).deleted_count
    strays = coll.delete_many({"_id": {"$nin": sorted(expected)}}).deleted_count
    written = seed(coll)
    dlq = client[db_name][DLQ_COLLECTION].delete_many({}).deleted_count
    total = coll.count_documents({})
    return {
        "namespace": f"{db_name}.{coll_name}",
        "post_images": images,
        "live_removed": live,
        "strays_removed": strays,
        "seed_upserted": written,
        "dlq_cleared": dlq,
        "total": total,
        "ok": total == SEED_COUNT,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.parse_args()
    assert_safe_target()
    client, coll = get_collection()
    try:
        result = reset(client, coll)
    finally:
        client.close()
    print(f"[ok]   {result['namespace']}: {result['post_images']}")
    print(f"[ok]   removed {result['live_removed']} live demo document(s), {result['strays_removed']} stray(s)")
    print(f"[ok]   upserted {result['seed_upserted']} seeded orders; cleared {result['dlq_cleared']} DLQ entr(ies)")
    print(f"[{'ok' if result['ok'] else 'FAIL'}]   {result['total']} document(s) in the collection (expected {SEED_COUNT})")
    print("       The stream processor propagates these changes to Iceberg on its own.")
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
