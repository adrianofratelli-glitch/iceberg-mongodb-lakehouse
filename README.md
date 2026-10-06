# Iceberg + MongoDB

Operational data lives in MongoDB. Analytics lives in the lake. Keeping the two
in sync is usually a pipeline someone owns: Debezium, Kafka, Spark jobs, a
nightly batch that drifts.

This demo removes that pipeline. An Atlas collection is mirrored into an Apache
Iceberg table on S3 by Atlas Stream Processing, catalogued in AWS Glue and
queried from Athena. Inserts, updates, deletes and new fields propagate on their
own — including the two a traditional append-only lake struggles with.

> MongoDB Atlas → Atlas Stream Processing → Iceberg on S3 → Glue → Athena

Measured against a real cluster and a real bucket (2026-08-24): **5,000 orders
on both sides, inserts visible in ~10s, updates in ~20s, deletes in 30-60s.**

![Architecture: Atlas cluster, Atlas Stream Processing, Iceberg on S3, Glue and Athena](docs/architecture.png)

---

## The demo

### 1. Two halves of one circuit

The operational cluster and the derived table, side by side. Same count, no
synchronisation job produced it.

![Two halves of the circuit: MongoDB with 5,000 orders and the Iceberg table with 5,000 rows, marked as converged](docs/screenshots/01-duas-metades.png)

### 2. An order enters through the transactional path

`INSERT` writes to MongoDB. The change stream carries it; the UI times how long
the row takes to appear in Iceberg — 6 seconds in the run below, and up to a
minute depending on where the write lands relative to the processor's commit.

![The live CDC panel: the order in MongoDB and the same row reflected in Iceberg after 6 seconds](docs/screenshots/02-ciclo-cdc.png)

### 3. The update lands in the lake

Status and amount change in MongoDB and the Iceberg row follows. This is the
step that matters: an append-only lake would need a partition rewrite.

![The same order showing EM_TRANSPORTE and the new amount, reflected in 35 seconds](docs/screenshots/03-update-refletido.png)

Delete works the same way — the row disappears from the table. For regulated
industries that is the right-to-be-forgotten reaching the lake without a
compaction job.

### 4. Time travel comes free with the format

Every processor commit is an Iceberg snapshot. Click one and the order comes
back as it was at that instant, even after being deleted from MongoDB. Nobody
configured versioning.

![Iceberg snapshot history with append, overwrite and delete operations](docs/screenshots/04-time-travel.png)

### 5. The question nobody runs on the operational cluster

Revenue by state and month, ticket size, cancellation rate, app share — 18
months of history scanned on S3, with the cluster untouched.

![Analytical query results with per-state monthly revenue, scan time and bytes scanned](docs/screenshots/05-consulta-analitica.png)

A new field (`fraudScore`) becomes a column in the Glue catalogue with no
migration, and older rows read as `NULL`.

---

## Setup

Requires an Atlas cluster, an Atlas Stream Processing workspace, an S3 bucket, a
Glue database and an IAM role trusted by Atlas.

```bash
# 1. AWS: bucket and Glue database (the IAM role and its policy are manual)
AWS_REGION=<region> S3_BUCKET=<bucket> bash setup/aws/bootstrap.sh

# 2. credentials
cp .env.example .env    # fill in MONGODB_URI, S3_BUCKET, AWS_REGION

# 3. python
python3 -m venv .venv && ./.venv/bin/pip install -r requirements.txt
./.venv/bin/python scripts/preflight.py     # validates and fixes the MongoDB side
DATABASE_NAME=iceberg_demo_test ./.venv/bin/python scripts/reset_demo.py   # try it on a test db first
ALLOW_DEMO_DB_WRITE=1 ./.venv/bin/python scripts/reset_demo.py          # 5,000 reproducible orders in the demo db

# 4. the stream processor, from mongosh connected to the workspace
#    edit the constants at the top of the file first
load("stream-processing/create_processor.js")
```

## Running the UI

```bash
cd backend && python3 -m venv venv && ./venv/bin/pip install -r requirements.txt
cd ../frontend && npm install
cd .. && ./start.sh          # backend :8250, frontend :5250
```

The Iceberg panels need AWS credentials; without them the MongoDB side keeps
working and the UI says what is missing.

## Driving the demo from the CLI

```bash
./.venv/bin/python scripts/insert_order.py
./.venv/bin/python scripts/update_order.py
./.venv/bin/python scripts/delete_order.py
./.venv/bin/python scripts/add_schema_field.py
ALLOW_DEMO_DB_WRITE=1 ./.venv/bin/python scripts/reset_demo.py
./.venv/bin/python scripts/compare_aggregation.py   # same aggregation on the cluster, timed
```

Athena queries live in `sql/`, from per-step validation to the business question
and the time travel snippets.

## Resetting the demo

`scripts/reset_demo.py` is the one command that puts everything back: it makes
sure the collection has `changeStreamPreAndPostImages`, removes the live demo
orders and anything that is not part of the seed, upserts the 5,000 seeded
orders and empties the dead-letter queue. It is idempotent: on a clean demo it
writes nothing that changes a document, so the processor has nothing to carry.

- Any database ending in `_test` is writable; the demo database needs
  `ALLOW_DEMO_DB_WRITE=1`. `DATABASE_NAME` in the environment wins over `.env`.
- The seed is anchored on a fixed date (`SEED_ANCHOR`, default
  `2026-08-24T18:59:04Z`) because the `_id` carries the order month. Set
  `SEED_ANCHOR` to refresh the dates, then run the reset so the old ids go.
- The Iceberg table is not touched: the reset is plain writes and the processor
  propagates them, deletes included. Rebuilding the table from scratch is the
  separate, destructive path in `docs/TROUBLESHOOTING.md`
  (`stream-processing/rebuild_table.py --auto-rebuild`, then
  `restart_processor.js`).

## Measuring the change-stream leg

```bash
./.venv/bin/python scripts/cdc_probe.py --samples 30   # runs in iceberg_demo_test only
```

It times write → change event (with post-image, as the processor uses) for
insert, update and delete, checks that a consumer resumed from its token on a
new connection gets exactly the events it missed, and that concurrent writers
produce events in commit order. It does not include the `$iceberg` commit or
Athena; the UI's CDC panel times that end to end.

Run on 2026-10-06 from a laptop to the Atlas cluster (includes the write
round trip): p50 419 ms / p95 445 ms for insert, 418 / 460 ms for update,
425 / 447 ms for delete (30 samples each); resume delivered 30/30 missed
events with 0 duplicates; 100 concurrent updates arrived in order.

## Adversarial tests

```bash
backend/venv/bin/pip install -r backend/requirements-dev.txt
backend/venv/bin/pytest -q backend/tests                 # offline, mocks only
LIVE_ATLAS=1 backend/venv/bin/pytest -q backend/tests/test_live_cdc_adversarial.py   # Atlas, iceberg_demo_test
cd frontend && node --test tests/*.test.mjs
```

The suite rejects malformed or oversized order IDs, SQL-like snapshot values and
query traversal before MongoDB, Athena or the filesystem is touched. Snapshot IDs
are positive bounded integers; order and query IDs use an explicit allowlist
(zero-width, RTL, emoji and 60 KB identifiers included). Error text that reaches
the browser has connection strings, cluster hosts and AWS ids masked.

The live suite runs against `iceberg_demo_test` and drops what it creates:
eight concurrent INSERT clicks leave one document, schema drift (`amount` as
string, `Decimal128`, null, a new field) does not break the overview, unicode
and dotted keys arrive verbatim in the change stream, and a 10 MB document is
served. It also pins a real limit: updating a ~9 MB field of a ~10 MB document
produces a change event above 16 MB that a plain change stream cannot deliver
(`$changeStreamSplitLargeEvent` splits it). Keep documents well below that if
they are going to the lake.

## Before every demo

```bash
./.venv/bin/python scripts/preflight.py
```

It checks the connection, enables `changeStreamPreAndPostImages` when missing,
reports the dead-letter queue and flags expired AWS credentials.

## Things that break it

`docs/TROUBLESHOOTING.md` documents nine failures found while building this
against real infrastructure, with symptom and cure. The ones worth knowing up
front:

| Symptom | Cause |
|---|---|
| Processor dies on the first UPDATE | source collection has no post-images |
| Duplicate rows in Athena | a restart without a checkpoint re-runs `initialSync`, which inserts rather than upserts |
| A document never arrives | `Decimal128` or a type conflict — check `iceberg_demo.dlq` |
| Processor fails and the DLQ is empty | a field name containing `.`; Iceberg column names are stricter than MongoDB's |

---

Based on [mongodb-developer/Iceberg-MongoDB-Demo](https://github.com/mongodb-developer/Iceberg-MongoDB-Demo),
hardened against a live environment: credentials moved to `.env`, a dead-letter
queue, a preflight script, the business and time travel queries, and a UI.

## License

MIT, see [LICENSE](LICENSE).
