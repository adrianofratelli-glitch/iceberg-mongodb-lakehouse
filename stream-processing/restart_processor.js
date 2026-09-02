// Restart the processor from scratch, ignoring the stored checkpoint.
//
// Use this after fixing a failure. Resuming from the checkpoint replays the
// event that killed the processor, so a plain start() fails again.
//
// WARNING: skipping the checkpoint re-runs initialSync, and initialSync
// INSERTS every source document again. $iceberg "cdc" mode applies updates
// and deletes by _id, but the initial load is a plain insert -- so every
// restart without a checkpoint duplicates the whole table. Measured: four
// restarts produced four copies of all 12 documents (48 rows).
//
// Because that duplication is real and has already happened once in
// production (spi-inter-pix, 2026-09-01), this script now REFUSES to run
// unless it has been told the table was already rebuilt:
//
//   RECOMMENDED (automated):
//     ./backend/venv/bin/python stream-processing/rebuild_table.py --auto-rebuild
//     load("stream-processing/restart_processor.js")
//
//   MANUAL (if you don't trust the automated DROP, or backend/venv isn't set up):
//     -- Athena:
//     DROP TABLE IF EXISTS mongodb_iceberg_demo.orders
//     -- then, with the table confirmed dropped, set the env var and load:
//     AUTO_REBUILD=1 mongosh "<workspace-uri>"
//     load("stream-processing/restart_processor.js")
//
// Either path sets AUTO_REBUILD=1 in the environment mongosh was started
// with -- this script checks for it and aborts otherwise, instead of
// silently duplicating the table like it used to.

const PROCESSOR_NAME = "ordersToIceberg";
const TIER = "SP10";

const autoRebuildConfirmed =
  typeof process !== "undefined" && process.env && process.env.AUTO_REBUILD === "1";

if (!autoRebuildConfirmed) {
  print("ABORT: restarting without a checkpoint duplicates the whole Iceberg " +
    "table (initialSync inserts, it does not upsert). This script refuses to " +
    "run until the table has been rebuilt. Do ONE of:");
  print("");
  print("  1) Automated (recommended):");
  print("       ./backend/venv/bin/python stream-processing/rebuild_table.py --auto-rebuild");
  print("     then rerun this script in the SAME mongosh session (that script " +
    "prints the exact env var to export first).");
  print("");
  print("  2) Manual:");
  print("       -- Athena:");
  print("       DROP TABLE IF EXISTS mongodb_iceberg_demo.orders");
  print("     then start mongosh with AUTO_REBUILD=1 set, e.g.:");
  print('       AUTO_REBUILD=1 mongosh "<workspace-uri>"');
  print('       load("stream-processing/restart_processor.js")');
  quit(1);
}

print("AUTO_REBUILD confirmed -- proceeding on the assumption the Iceberg " +
  "table was already dropped/rebuilt.");

const proc = sp[PROCESSOR_NAME];

try {
  proc.stop();
  print(`Stopped ${PROCESSOR_NAME}.`);
} catch (e) {
  print(`Stop skipped (${e.codeName || e.message}).`);
}

proc.start({ tier: TIER, resumeFromCheckpoint: false });
print(`Started ${PROCESSOR_NAME} on ${TIER} without checkpoint.`);
print('Check it with: sp.' + PROCESSOR_NAME + '.stats()');
