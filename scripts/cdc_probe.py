"""Measure the native CDC leg (write -> change event) and its resume guarantee.

What this measures, and what it does not:
  * write -> change event delivered to a consumer, for INSERT, UPDATE (with
    post-image, as the processor's fullDocument: "required" needs) and DELETE.
    This is the primitive Atlas Stream Processing's $source is built on.
  * resume after a dropped consumer: events before the token are not
    re-delivered and events written while the consumer was down are not lost.
  * it does NOT include the $iceberg commit to S3 nor the Athena read; that
    end-to-end number is what the UI's CDC panel times (needs AWS credentials
    and the processor running).

Runs only against a database ending in _test (default iceberg_demo_test):

    ./.venv/bin/python scripts/cdc_probe.py            # 30 samples per operation
    ./.venv/bin/python scripts/cdc_probe.py --samples 100 --json
"""

from __future__ import annotations

import argparse
import json
import os
import statistics
import threading
import time
import uuid

from pymongo import MongoClient

os.environ.setdefault("DATABASE_NAME", "iceberg_demo_test")

from common import MONGODB_URI, DATABASE_NAME, assert_safe_target, validate_config  # noqa: E402

PROBE_COLL = "cdc_probe"


def _pct(values: list[float], q: float) -> float:
    ordered = sorted(values)
    k = max(0, min(len(ordered) - 1, round(q * (len(ordered) - 1))))
    return round(ordered[k], 1)


def summary(values: list[float]) -> dict:
    return {
        "n": len(values),
        "p50_ms": _pct(values, 0.50),
        "p95_ms": _pct(values, 0.95),
        "max_ms": round(max(values), 1),
        "mean_ms": round(statistics.fmean(values), 1),
    }


def ensure_probe_collection(db):
    if PROBE_COLL not in db.list_collection_names():
        db.create_collection(PROBE_COLL, changeStreamPreAndPostImages={"enabled": True})
    return db[PROBE_COLL]


def measure_latency(coll, samples: int) -> dict:
    """Time write -> event for each operation, one write in flight at a time."""
    results: dict[str, list[float]] = {"insert": [], "update": [], "delete": []}
    run = uuid.uuid4().hex[:8]
    with coll.watch(full_document="required", max_await_time_ms=50) as stream:
        for i in range(samples):
            _id = f"PROBE-{run}-{i:04d}"
            for op in ("insert", "update", "delete"):
                started = time.perf_counter()
                if op == "insert":
                    coll.insert_one({"_id": _id, "status": "NOVO", "amount": float(i)})
                elif op == "update":
                    coll.update_one({"_id": _id}, {"$set": {"status": "ATUALIZADO"}})
                else:
                    coll.delete_one({"_id": _id})
                while True:
                    event = stream.try_next()
                    if event is None:
                        continue
                    if event["documentKey"]["_id"] == _id and event["operationType"] == op:
                        if op == "update":
                            assert event["fullDocument"]["status"] == "ATUALIZADO"
                        results[op].append((time.perf_counter() - started) * 1000)
                        break
    return {op: summary(v) for op, v in results.items()}


def check_resume(coll, before: int = 20, during: int = 30) -> dict:
    """Consumer dies after `before` events; `during` writes happen while it is
    down (on a brand-new client, as after a process restart). Resuming from the
    last token must deliver exactly the missed events, in order, once each."""
    run = uuid.uuid4().hex[:8]
    ids = [f"RESUME-{run}-{i:03d}" for i in range(before + during)]
    with coll.watch() as stream:
        # The first batch is written with the consumer alive.
        coll.insert_many([{"_id": i, "n": n} for n, i in enumerate(ids[:before])])
        seen, token = [], None
        while len(seen) < before:
            event = stream.try_next()
            if event is not None:
                seen.append(event["documentKey"]["_id"])
                token = stream.resume_token
    # consumer is gone; writes keep happening, from another connection
    other = MongoClient(MONGODB_URI, serverSelectionTimeoutMS=10000)
    try:
        other[coll.database.name][coll.name].insert_many(
            [{"_id": i, "n": n} for n, i in enumerate(ids[before:], start=before)]
        )
    finally:
        other.close()
    fresh = MongoClient(MONGODB_URI, serverSelectionTimeoutMS=10000)
    resumed: list[str] = []
    try:
        fcoll = fresh[coll.database.name][coll.name]
        deadline = time.monotonic() + 30
        with fcoll.watch(resume_after=token, max_await_time_ms=200) as stream:
            while len(resumed) < during and time.monotonic() < deadline:
                event = stream.try_next()
                if event is not None:
                    resumed.append(event["documentKey"]["_id"])
            # anything extra within a short grace window would be a duplicate
            grace = time.monotonic() + 1.5
            while time.monotonic() < grace:
                event = stream.try_next()
                if event is not None and event["documentKey"]["_id"].startswith(f"RESUME-{run}"):
                    resumed.append(event["documentKey"]["_id"])
    finally:
        fresh.close()
    coll.delete_many({"_id": {"$in": ids}})
    return {
        "before": seen == ids[:before],
        "missed_delivered": resumed[:during] == ids[before:],
        "duplicates": len(resumed) - len(set(resumed)) + len(set(resumed) & set(seen)),
        "extra": max(0, len(resumed) - during),
        "ok": seen == ids[:before] and resumed == ids[before:],
    }


def check_ordering(coll, writers: int = 4, per_writer: int = 25) -> dict:
    """Concurrent writers on one document: events arrive in commit order, so the
    last event's post-image equals the final document (what a cdc sink keyed by
    _id converges to), and clusterTime never goes backwards."""
    _id = f"ORDER-{uuid.uuid4().hex[:8]}"
    coll.insert_one({"_id": _id, "seq": 0})
    times, last_post = [], None
    expected = writers * per_writer
    with coll.watch([{"$match": {"documentKey._id": _id}}], full_document="required",
                    max_await_time_ms=100) as stream:
        def work():
            for _ in range(per_writer):
                coll.update_one({"_id": _id}, {"$inc": {"seq": 1}})

        threads = [threading.Thread(target=work) for _ in range(writers)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        got = 0
        deadline = time.monotonic() + 30
        while got < expected and time.monotonic() < deadline:
            event = stream.try_next()
            if event is not None and event["operationType"] == "update":
                got += 1
                times.append(event["clusterTime"])
                last_post = event["fullDocument"]
    final = coll.find_one({"_id": _id})
    coll.delete_one({"_id": _id})
    monotonic = all(a <= b for a, b in zip(times, times[1:]))
    return {
        "events": len(times),
        "cluster_time_monotonic": monotonic,
        "last_event_equals_final": last_post == final,
        "ok": len(times) == expected and monotonic and last_post == final,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--samples", type=int, default=30)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    if not DATABASE_NAME.endswith("_test"):
        raise SystemExit("cdc_probe only runs against a *_test database.")
    assert_safe_target()
    validate_config()
    client = MongoClient(MONGODB_URI, serverSelectionTimeoutMS=10000)
    try:
        coll = ensure_probe_collection(client[DATABASE_NAME])
        report = {
            "namespace": f"{DATABASE_NAME}.{PROBE_COLL}",
            "latency": measure_latency(coll, args.samples),
            "resume": check_resume(coll),
            "ordering": check_ordering(coll),
        }
    finally:
        client.close()
    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print(f"namespace {report['namespace']}")
        for op, s in report["latency"].items():
            print(f"  {op:<7} write->event  p50 {s['p50_ms']} ms  p95 {s['p95_ms']} ms  max {s['max_ms']} ms  (n={s['n']})")
        print(f"  resume   {report['resume']}")
        print(f"  ordering {report['ordering']}")
    return 0 if report["resume"]["ok"] and report["ordering"]["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
