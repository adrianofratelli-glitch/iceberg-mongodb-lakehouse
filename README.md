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
Not re-measured since: the AWS credential was expired during the October 2026
review rounds, so only the MongoDB → change stream leg was measured then (see
*Measuring the change-stream leg*).

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

Delete works the same way — the row disappears from the table's current view.
It does **not** disappear from history: older snapshots still reference the data
file that holds it, which is exactly what makes time travel work. Erasing it for
good takes table maintenance, shown in step 4b below.

### 4. Time travel comes free with the format

Every processor commit is an Iceberg snapshot. Click one and the order comes
back as it was at that instant, even after being deleted from MongoDB — until
that snapshot expires. Nobody configured versioning.

![Iceberg snapshot history with append, overwrite and delete operations](docs/screenshots/04-time-travel.png)

### 4b. Right to be forgotten: delete, then expire

Time travel and erasure pull in opposite directions. The Iceberg maintenance
docs are explicit: *"Data files are not deleted until they are no longer
referenced by a snapshot that may be used for time travel or rollback"*
([Iceberg — Maintenance](https://iceberg.apache.org/docs/latest/maintenance/)).
So a DELETE that reached the lake is step one of three:

1. **DELETE in MongoDB.** The processor commits it; the row leaves the current
   view. Every earlier snapshot still has it.
2. **Rewrite the files with the delete applied** — Athena
   [`OPTIMIZE ... REWRITE DATA USING BIN_PACK`](https://docs.aws.amazon.com/athena/latest/ug/optimize-statement.html).
   The thresholds `optimize_rewrite_delete_file_threshold` and
   `optimize_rewrite_data_file_threshold` (defaults 2 and 5,
   [table properties](https://docs.aws.amazon.com/athena/latest/ug/querying-iceberg-creating-tables.html))
   are set to 1, otherwise a single delete does not trigger a rewrite.
3. **Expire snapshots and remove files** — Athena
   [`VACUUM`](https://docs.aws.amazon.com/athena/latest/ug/vacuum-statement.html)
   expires snapshots older than `vacuum_max_snapshot_age_seconds` (default
   432,000 s, 5 days), deletes the data files that became unreachable and the
   orphan files. After that the order cannot be time-travelled to.

The UI panel *Direito ao esquecimento* shows the steps with their SQL and checks,
snapshot by snapshot (`FOR VERSION AS OF` on each retained snapshot), whether the
order can still come back. The same from the CLI:

```bash
./backend/venv/bin/python stream-processing/forget_order.py PED-AOVIVO-001          # read-only check
ALLOW_LAKE_PURGE=1 ./backend/venv/bin/python stream-processing/forget_order.py \
    PED-AOVIVO-001 --purge --retention-seconds 1                                    # destructive
```

The purge refuses while the order still exists in MongoDB or in the current
Iceberg view, and it is off unless `ALLOW_LAKE_PURGE=1`, because it removes time
travel for the **whole table**, not just one order. In production the retention
*is* the erasure SLA: a scheduled VACUUM with 5-day retention completes erasure
within 5 days plus the schedule interval. What this does not cover: S3 object
versioning (deleted objects become noncurrent versions until a lifecycle rule
expires them — the check reports the bucket's versioning status), a query role
without `s3:DeleteObject` (VACUUM then succeeds and deletes nothing, per the
Athena docs), Atlas backups and the dead-letter queue, which have their own
retention.

Status: implemented and covered by offline tests; **not yet run against the
real table** — the AWS credential was expired during the 2026-10-08 round. Run
the read-only check first when it is renewed.

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

The Iceberg panels need AWS credentials. Without them the demo runs in
**MongoDB-only mode**: `/preflight` returns `modo: "somente_mongodb"` with a
plain-language `resumo`, the UI shows a banner, the CDC buttons still write to
Atlas, and every step stays at "aguardando confirmação" — the backend reports a
write as confirmed in MongoDB only; the lake side is confirmed by reading the
row back from Athena, never assumed. Renewing the credential brings the Iceberg
side back without a restart.

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
they are going to the lake; the preflight warns above 8 MB.

## Before every demo

```bash
./.venv/bin/python scripts/preflight.py
```

It checks the connection, enables `changeStreamPreAndPostImages` when missing,
reports the dead-letter queue and the largest document (above 8 MB an UPDATE can
produce a change event over the 16 MB limit), flags expired AWS credentials and
ends with `PASSED (full demo)` or `PASSED WITH WARNINGS (MongoDB-only mode)`.

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
