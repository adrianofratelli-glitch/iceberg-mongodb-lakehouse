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
// Drop the Iceberg table BEFORE restarting, so initialSync rebuilds it clean:
//   Athena:  DROP TABLE IF EXISTS mongodb_iceberg_demo.orders
//
//   load("stream-processing/restart_processor.js")

const PROCESSOR_NAME = "ordersToIceberg";
const TIER = "SP10";

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
