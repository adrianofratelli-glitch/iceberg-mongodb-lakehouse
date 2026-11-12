"""Measure the whole circuit: MongoDB write -> processor -> Iceberg -> Athena read.

scripts/cdc_probe.py stops at the change event. This probe closes the loop the
README promises: it writes an order in MongoDB, then polls Athena until the
Iceberg table reflects it, for INSERT (row appears), UPDATE (new status) and
DELETE (row gone from the current version). Each sample uses its own
`PED-PROBE-*` id and deletes it at the end (also on failure).

What the numbers mean:
  * `visivel_s` is an upper bound: time from the MongoDB acknowledgement to the
    end of the first Athena query that saw the change. Its resolution is the
    polling interval plus one Athena query (`janela_s` shows the uncertainty).
  * A timeout means the change did not show up in `--timeout` seconds. The usual
    causes are a stopped processor or a database the processor does not read
    (it sources the demo database; a `*_test` database never converges unless a
    processor reads it).
  * Every poll is an Athena query; the summary reports the bytes scanned so the
    cost is visible (Athena bills per TB scanned).

Refuses to write to a database that does not end in `_test` unless
ALLOW_DEMO_DB_WRITE=1, and refuses to start without AWS credentials (nothing is
written in that case).

    DATABASE_NAME=<db>_test backend/venv/bin/python backend/lake_probe.py
    ALLOW_DEMO_DB_WRITE=1 backend/venv/bin/python backend/lake_probe.py --samples 10 --json
"""

from __future__ import annotations

import argparse
import json
import os
import statistics
import sys
import time
import uuid
from typing import Callable

import athena_side
import mongo_side
import settings

PROBE_PREFIX = "PED-PROBE-"


class ProbeRefused(RuntimeError):
    """The probe must not run (unsafe target or no AWS credentials)."""


def assert_safe_target(db_name: str) -> None:
    if db_name.endswith("_test") or os.getenv("ALLOW_DEMO_DB_WRITE") == "1":
        return
    raise ProbeRefused(
        f"Recusado: '{db_name}' é o banco da demo. Use DATABASE_NAME=<nome>_test ou "
        "ALLOW_DEMO_DB_WRITE=1 de propósito (o processor da demo lê esse banco)."
    )


def wait_until(
    read: Callable[[], dict],
    reflected: Callable[[list], bool],
    *,
    timeout_s: float,
    interval_s: float,
    clock: Callable[[], float] = time.monotonic,
    sleep: Callable[[float], None] = time.sleep,
) -> dict:
    """Poll `read` until `reflected(rows)` holds or the timeout passes."""
    start = clock()
    previous_start = start
    polls = 0
    scanned = 0
    while True:
        poll_start = clock()
        result = read()
        polls += 1
        scanned += int(result.get("bytes_escaneados", 0) or 0)
        now = clock()
        if reflected(result.get("linhas") or []):
            return {
                "ok": True,
                "visivel_s": round(now - start, 2),
                "janela_s": round(now - previous_start, 2),
                "consultas": polls,
                "bytes_escaneados": scanned,
            }
        if now - start >= timeout_s:
            return {
                "ok": False,
                "visivel_s": None,
                "esperou_s": round(now - start, 2),
                "consultas": polls,
                "bytes_escaneados": scanned,
            }
        previous_start = poll_start
        sleep(interval_s)


def probe_document(order_id: str) -> dict:
    return {
        "_id": order_id,
        "customerId": "CLI-PROBE",
        "region": "SP",
        "product": "Sonda de latência",
        "quantity": 1,
        "amount": 100.0,
        "status": "PROCESSANDO",
        "channel": "APP",
        "paymentMethod": "PIX",
        "orderDate": mongo_side.utcnow(),
    }


# operation -> (MongoDB write, predicate over Athena rows of find_order)
def _steps(coll, order_id: str):
    return [
        ("insert", lambda: coll.insert_one(probe_document(order_id)), lambda rows: len(rows) == 1),
        (
            "update",
            lambda: coll.update_one({"_id": order_id}, {"$set": {"status": "EM_TRANSPORTE"}}),
            lambda rows: len(rows) == 1 and rows[0][1] == "EM_TRANSPORTE",
        ),
        ("delete", lambda: coll.delete_one({"_id": order_id}), lambda rows: len(rows) == 0),
    ]


def run_sample(coll, order_id: str, read_order: Callable[[str], dict], **wait_kwargs) -> dict:
    """One INSERT -> UPDATE -> DELETE cycle; stops at the first timeout."""
    results: dict[str, dict] = {}
    try:
        for op, write, reflected in _steps(coll, order_id):
            write()
            results[op] = wait_until(lambda: read_order(order_id), reflected, **wait_kwargs)
            if not results[op]["ok"]:
                break
    finally:
        coll.delete_one({"_id": order_id})
    return results


def _pct(values: list[float], q: float) -> float:
    ordered = sorted(values)
    k = max(0, min(len(ordered) - 1, round(q * (len(ordered) - 1))))
    return round(ordered[k], 2)


def summarize(samples: list[dict]) -> dict:
    out = {}
    for op in ("insert", "update", "delete"):
        rows = [s[op] for s in samples if op in s]
        seen = [r["visivel_s"] for r in rows if r["ok"]]
        out[op] = {
            "amostras": len(rows),
            "convergiu": len(seen),
            "timeouts": len(rows) - len(seen),
            "p50_s": _pct(seen, 0.50) if seen else None,
            "p95_s": _pct(seen, 0.95) if seen else None,
            "max_s": round(max(seen), 2) if seen else None,
            "media_s": round(statistics.fmean(seen), 2) if seen else None,
            "bytes_escaneados": sum(r["bytes_escaneados"] for r in rows),
        }
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--samples", type=int, default=3)
    parser.add_argument("--timeout", type=float, default=120.0, help="segundos por operação")
    parser.add_argument("--interval", type=float, default=2.0, help="segundos entre consultas")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    try:
        assert_safe_target(settings.DATABASE_NAME)
        aws = athena_side.identity()
        if not aws["disponivel"]:
            raise ProbeRefused(f"Sem AWS, nada a medir (nada foi gravado): {aws.get('erro')}")
    except ProbeRefused as exc:
        print(exc, file=sys.stderr)
        return 2

    coll = mongo_side.collection()
    run = uuid.uuid4().hex[:8]
    samples = []
    for i in range(args.samples):
        order_id = f"{PROBE_PREFIX}{run}-{i:03d}"
        samples.append(
            run_sample(
                coll,
                order_id,
                athena_side.find_order,
                timeout_s=args.timeout,
                interval_s=args.interval,
            )
        )
    report = {
        "banco": f"{settings.DATABASE_NAME}.{settings.COLLECTION_NAME}",
        "tabela": f"{settings.GLUE_DATABASE}.{settings.ICEBERG_TABLE}",
        "intervalo_s": args.interval,
        "operacoes": summarize(samples),
    }
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(f"{report['banco']} -> {report['tabela']} (polling a cada {args.interval}s)")
        for op, r in report["operacoes"].items():
            print(
                f"  {op:<6} {r['convergiu']}/{r['amostras']} convergiram  "
                f"p50 {r['p50_s']}s  p95 {r['p95_s']}s  max {r['max_s']}s  "
                f"Athena {r['bytes_escaneados'] / 1e6:.1f} MB"
            )
    timeouts = sum(r["timeouts"] for r in report["operacoes"].values())
    return 1 if timeouts else 0


if __name__ == "__main__":
    raise SystemExit(main())
