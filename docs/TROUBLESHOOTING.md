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

Check the queue with:

```js
db.dlq.find().sort({ dlqTime: -1 }).limit(5)
```

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
