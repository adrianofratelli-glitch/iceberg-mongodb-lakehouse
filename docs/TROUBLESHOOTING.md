# Troubleshooting

Everything below was hit while running this demo against a real Atlas cluster
and a real S3 bucket. Run `python scripts/preflight.py` before a demo -- it
catches the first two on its own.

## The processor dies on the first UPDATE

```
NoMatchingDocument: Change stream was configured to require a post-image for
all update events, but the post-image was not found
```

The `$source` uses `config: { fullDocument: "required" }`, which needs
post-images on the source collection. Enable them once:

```js
db.runCommand({ collMod: "orders", changeStreamPreAndPostImages: { enabled: true } })
```

Post-images are not retroactive, so the event that failed has no image and
never will. Restart without the checkpoint:

```
load("stream-processing/restart_processor.js")
```

INSERT and DELETE work without this setting, so the demo looks healthy until
step 2 of the live script.

**Update (2026-09):** `stream-processing/create_processor.js` now checks and
enables this flag itself before creating the processor, and aborts with a
clear message if it can't (e.g. insufficient permissions) instead of creating
a processor that is guaranteed to fail on the first UPDATE. The manual fix
above (and `POST /api/corrigir/post-images`) still work as a fallback.

## `Invalid $iceberg.path: cannot end with a '/' character`

`ICEBERG_PATH` must not have a trailing slash. Use `"iceberg-warehouse"`.

## `is not authorized to perform: s3:PutObject`

The IAM role assumed by Atlas needs, on the bucket ARN: `s3:ListBucket`,
`s3:GetBucketLocation`; and on `<bucket>/*`: `s3:GetObject`, `s3:PutObject`,
`s3:DeleteObject`, `s3:AbortMultipartUpload`. With the Glue catalog it also
needs `glue:GetDatabase(s)`, `glue:GetTable(s)`, `glue:CreateTable`,
`glue:UpdateTable`, `glue:GetPartitions`, `glue:BatchCreatePartition`,
`glue:BatchGetPartition` on the catalog, database and table ARNs.

`setup/aws/bootstrap.sh` creates the bucket and the Glue database only. The
role, its trust policy and its permission policy are manual.

## `another operation "RestartStreamProcessor..." has the lock`

Atlas is already retrying the processor. Wait ~30s and check `stats()` before
starting it by hand.

## Documents that never reach Iceberg

The processor writes rejects to `iceberg_demo.dlq`. Observed causes:

| Input | Result |
|---|---|
| Nested documents and arrays | fine -- become struct / list |
| ObjectId, Binary, null | fine |
| 200 KB document | fine |
| `Decimal128` | **DLQ** |
| Type conflict (string into a double column) | **DLQ** -- `Unexpected BSON type of string for iceberg column name amount of type double` |
| Field name containing `.` | **processor FAILS** -- `The iceberg identifier "meta.origem" cannot contain a "." character` |

The last one is the dangerous one: a single document with a dotted field name
stops the whole pipeline, and it cannot be skipped by the DLQ. Iceberg column
names are stricter than MongoDB field names.

**Update (2026-09):** `stream-processing/create_processor.js` now adds a
sanitization stage before `$iceberg` that renames any key containing `.` or
`$` (recursively, including inside arrays) so a dotted field name no longer
takes the processor down. The DLQ config below still catches Decimal128 and
type conflicts, which is a separate failure mode.

Check the queue with:

```js
db.dlq.find().sort({ dlqTime: -1 }).limit(5)
```

## `Resume of change stream was not possible`

```
Resume of change stream was not possible. The processor's most recent
checkpoint's resume point is no longer in the oplog.
```

The processor sat stopped (or FAILED) for longer than the source cluster's oplog
window, so the resume token stored in its last checkpoint has already rolled off
the oplog. Nothing is wrong with the pipeline or the connections -- check
`details.checkpoint.timestamp` in the error and compare it with the oplog window.

A processor in `FAILED` state does not accept `stop()` ("stream processor must be
running in order to be stopped"); go straight to the start.

The only way out is starting without the checkpoint, which for this processor
means rebuilding the table -- `resumeFromCheckpoint: false` re-runs initialSync
and appends a full copy (see the next section). Drop the table first:

```sql
DROP TABLE IF EXISTS mongodb_iceberg_demo.orders   -- Athena
```
```
load("stream-processing/restart_processor.js")
```

Everything written to the source between the checkpoint timestamp and the restart
is not replayed from the stream -- initialSync picks it up from the collection,
which is the source of truth, so the table still comes back complete.

Hit on 2026-09-01 with checkpoints from 2026-08-27: all three processors in the
`spi-inter-pix` workspace failed this way at the same time.

## Duplicate rows in Athena after a restart

Symptom: `SELECT count(*)` in Athena returns a multiple of the MongoDB count
(measured: 48 rows in Iceberg for 12 documents in MongoDB, after four
restarts).

`$iceberg` in `mode: "cdc"` applies updates and deletes by `_id`, but
`initialSync` is a plain insert pass -- it does not upsert. Every start with
`resumeFromCheckpoint: false` replays the full collection and appends a
complete copy of it.

Fix: stop the processor, drop the table, then restart so initialSync rebuilds
from MongoDB (the source of truth):

```
sp.ordersToIceberg.stop()
```
```sql
DROP TABLE IF EXISTS mongodb_iceberg_demo.orders   -- Athena
```
```
load("stream-processing/restart_processor.js")
```

Verify before demoing:

```sql
SELECT count(*) AS total, count(DISTINCT _id) AS distinct_ids FROM orders
```

Both numbers must match the MongoDB count.

**Update (2026-09):** `stream-processing/restart_processor.js` now refuses to
run (`resumeFromCheckpoint: false`) unless `AUTO_REBUILD=1` is set in the
environment, printing the exact commands otherwise instead of duplicating
silently. `stream-processing/rebuild_table.py --auto-rebuild` automates the
`DROP TABLE` step via boto3 (same Athena client pattern as
`backend/athena_side.py`); without `--auto-rebuild` it also refuses and prints
the manual command.

## Columns from old documents stay in the table

Iceberg evolves the schema on new fields but never removes a column. Any field
that ever reached the table stays in the schema, `NULL` for rows without it.
Test documents pollute the demo schema permanently -- drop and rebuild the
table to clean it.

## Athena: the Run button stays disabled

Athena needs a query result location before it will run anything:
Settings -> Manage -> `s3://<bucket>/athena-results/`.

## AWS credentials keep expiring

SSO credentials last a few hours. `scripts/preflight.py` checks them and, on
macOS, opens `~/.aws/credentials` so a fresh block can be pasted in
(`POV_NO_POPUP=1` disables that).

The permanent fix is an SSO profile in `~/.aws/config`, which makes refreshing
a single command with no copy-paste:

```
aws sso login --profile <name>
```

preflight detects a configured SSO profile and prints that command instead of
opening the editor.


## Propagating is not duplication

The UI separates two states that look alike in a count comparison:

| State | Condition | What it means |
|---|---|---|
| `propagando` | counts differ, `total == distinct ids` | the CDC event is still in flight — wait |
| `tabela duplicada` | `total > distinct ids` | a restart without a checkpoint re-ran initialSync |

Only the second is a defect. Reading a lagging count as duplication sends you
dropping and rebuilding a table that was never broken.
