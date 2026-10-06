"""Adversarial checks against the real Atlas cluster, in iceberg_demo_test only.

Opt-in (needs the .env MONGODB_URI and network):

    LIVE_ATLAS=1 backend/venv/bin/pytest -q backend/tests/test_live_cdc_adversarial.py

Never touches the demo database: settings.DATABASE_NAME is forced to
iceberg_demo_test and every test drops what it created.
"""

from __future__ import annotations

import os
import sys
import threading
import time
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

pytestmark = pytest.mark.skipif(os.getenv("LIVE_ATLAS") != "1", reason="set LIVE_ATLAS=1 to hit Atlas")

TEST_DB = "iceberg_demo_test"
TEST_COLL = "orders_adversarial"


@pytest.fixture
def live(monkeypatch):
    import mongo_side
    import settings

    if not settings.MONGODB_URI:
        pytest.skip("MONGODB_URI ausente")
    monkeypatch.setattr(settings, "DATABASE_NAME", TEST_DB)
    monkeypatch.setattr(settings, "COLLECTION_NAME", TEST_COLL)
    db = mongo_side.client()[TEST_DB]
    db.drop_collection(TEST_COLL)
    db.create_collection(TEST_COLL, changeStreamPreAndPostImages={"enabled": True})
    yield mongo_side, db[TEST_COLL]
    db.drop_collection(TEST_COLL)


def test_double_click_insert_is_idempotent(live):
    mongo_side, coll = live
    errors = []
    barrier = threading.Barrier(8)

    def click():
        try:
            barrier.wait(timeout=10)
            mongo_side.demo_insert()
        except Exception as exc:  # noqa: BLE001
            errors.append(repr(exc))

    threads = [threading.Thread(target=click) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert errors == []
    assert coll.count_documents({}) == 1


def test_schema_drift_does_not_break_the_overview(live):
    from bson.decimal128 import Decimal128

    mongo_side, coll = live
    coll.insert_many(
        [
            {"_id": "A", "amount": 10.0, "status": "ENTREGUE"},
            {"_id": "B", "amount": "20.5", "status": "ENTREGUE"},          # type swapped
            {"_id": "C", "amount": Decimal128("30.25"), "status": "NOVO"},  # lands in DLQ downstream
            {"_id": "D", "amount": None, "fraudScore": 0.9},                # new field, null amount
            {"_id": "E", "amount": "abc"},                                  # unparsable
        ]
    )
    data = mongo_side.overview()
    assert data["total"] == 5
    assert data["receita"] == pytest.approx(60.75)


def test_unicode_and_dotted_keys_round_trip_through_the_change_stream(live):
    _, coll = live
    doc = {
        "_id": "U1",
        "cliente​zw": 1,
        "שלום": "rtl",
        "emoji\U0001f9ca": True,
        "a.b": "dotted",
        "nested": {"x.y": 1},
    }
    with coll.watch(full_document="required", max_await_time_ms=200) as stream:
        coll.insert_one(doc)
        deadline = time.monotonic() + 20
        event = None
        while event is None and time.monotonic() < deadline:
            event = stream.try_next()
    assert event is not None
    # The source carries every key verbatim. Dots are legal in MongoDB and
    # illegal in Iceberg column names: create_processor.js sanitises them
    # before $iceberg (docs/TROUBLESHOOTING.md).
    assert event["fullDocument"] == doc


def test_near_limit_document_and_oversized_change_event(live):
    """A ~10 MB document is fine; updating a ~9 MB field yields a change event
    above 16 MB (updateDescription + post-image) that a plain change stream
    cannot deliver. $changeStreamSplitLargeEvent splits it into fragments."""
    from pymongo.errors import OperationFailure

    mongo_side, coll = live
    big = "x" * (10 * 1024 * 1024)
    coll.insert_one({"_id": "BIG", "payload": big})
    assert mongo_side.find_order("BIG")["payload"] == big

    with coll.watch(full_document="required", max_await_time_ms=500) as stream:
        coll.update_one({"_id": "BIG"}, {"$set": {"payload": "y" * (9 * 1024 * 1024)}})
        with pytest.raises(OperationFailure):
            deadline = time.monotonic() + 20
            while time.monotonic() < deadline:
                stream.try_next()

    token_before = None
    with coll.watch(max_await_time_ms=200) as probe:
        probe.try_next()
        token_before = probe.resume_token
    coll.update_one({"_id": "BIG"}, {"$set": {"payload": "z" * (9 * 1024 * 1024)}})
    fragments = []
    with coll.watch(
        [{"$changeStreamSplitLargeEvent": {}}],
        full_document="required",
        resume_after=token_before,
        max_await_time_ms=500,
    ) as stream:
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            event = stream.try_next()
            if event is None:
                continue
            fragments.append(event["splitEvent"])
            if event["splitEvent"]["fragment"] == event["splitEvent"]["of"]:
                break
    assert len(fragments) >= 2
