// Run this file from mongosh CONNECTED TO THE ATLAS STREAM PROCESSING WORKSPACE.
//
// Example inside mongosh:
//   load("stream-processing/create_processor.js")
//
// Edit these constants before running.

const PROCESSOR_NAME = "ordersToIceberg";
const SOURCE_CONNECTION = "atlas-orders";
const SOURCE_DATABASE = "iceberg_demo";
const SOURCE_COLLECTION = "orders";

// Direct connection string to the SOURCE Atlas cluster (not the Stream
// Processing workspace). Needed to validate/enable
// changeStreamPreAndPostImages on the source collection before the processor
// is created -- see the ABORT below for why this can't be skipped.
// Defaults to the MONGODB_URI env var (same one used by backend/.env) so
// mongosh sessions started with that variable already set need no edit here.
const SOURCE_URI = (typeof process !== "undefined" && process.env && process.env.MONGODB_URI) ||
  "REPLACE-ME-mongodb+srv://user:pass@cluster.mongodb.net/";

const S3_CONNECTION = "s3-iceberg";
const S3_BUCKET = "REPLACE-ME-seu-bucket";
const AWS_REGION = "sa-east-1";   // ajuste para a região do seu bucket
const ICEBERG_DATABASE = "mongodb_iceberg_demo";
const ICEBERG_TABLE = "orders";
const ICEBERG_PATH = "iceberg-warehouse";

// Dead-letter queue: documentos que o $iceberg rejeita (conflito de tipo,
// Decimal128, etc.) caem aqui em vez de sumirem sem rastro. Isso NÃO cobre
// nomes de campo com "." -- esses derrubam o processor inteiro antes mesmo de
// chegar ao $iceberg, por isso o estágio de sanitização abaixo existe.
const DLQ_DB = "iceberg_demo";
const DLQ_COLL = "dlq";

// --- 1. Pré-requisito: changeStreamPreAndPostImages -------------------------
//
// $source usa fullDocument: "required", que precisa de post-images na coleção
// de origem. Sem isso, INSERT e DELETE funcionam normalmente e mascaram o
// problema -- o processor só morre no primeiro UPDATE, silenciosamente, com o
// erro "post-image was not found". Ver docs/TROUBLESHOOTING.md.
//
// Antes só o backend FastAPI corrigia isso (POST /api/corrigir/post-images),
// e só quando alguém abria o dashboard e clicava. Este script agora valida e
// habilita a flag ele mesmo, e recusa criar o processor se não conseguir.

print(`Checking changeStreamPreAndPostImages on ${SOURCE_DATABASE}.${SOURCE_COLLECTION}...`);

if (SOURCE_URI.startsWith("REPLACE-ME")) {
  print("ABORT: SOURCE_URI not configured. Set MONGODB_URI in the environment " +
    "(same value as backend/.env) or edit SOURCE_URI at the top of this file.");
  quit(1);
}

let sourceDb;
try {
  const sourceConn = new Mongo(SOURCE_URI);
  sourceDb = sourceConn.getDB(SOURCE_DATABASE);
} catch (e) {
  print(`ABORT: could not connect to the source cluster at SOURCE_URI: ${e.message}`);
  quit(1);
}

const collInfos = sourceDb.getCollectionInfos({ name: SOURCE_COLLECTION });
if (!collInfos || collInfos.length === 0) {
  print(`ABORT: collection ${SOURCE_DATABASE}.${SOURCE_COLLECTION} does not exist. ` +
    "Seed it first (scripts/seed_orders.py) then rerun.");
  quit(1);
}

const alreadyEnabled = Boolean(
  collInfos[0].options &&
  collInfos[0].options.changeStreamPreAndPostImages &&
  collInfos[0].options.changeStreamPreAndPostImages.enabled
);

if (alreadyEnabled) {
  print("changeStreamPreAndPostImages already enabled.");
} else {
  print("changeStreamPreAndPostImages is NOT enabled -- enabling it now " +
    "(required for $source fullDocument: 'required'; without it the processor " +
    "would be created successfully and only fail later, on the first UPDATE).");
  try {
    sourceDb.runCommand({
      collMod: SOURCE_COLLECTION,
      changeStreamPreAndPostImages: { enabled: true }
    });
  } catch (e) {
    print(`ABORT: collMod failed: ${e.message}`);
    print("Most likely cause: the user in SOURCE_URI lacks dbAdmin (or an " +
      "equivalent collMod-capable role) on " + SOURCE_DATABASE + ". Refusing " +
      "to create a processor that is guaranteed to fail on the first UPDATE. " +
      "Grant the role and rerun this script.");
    quit(1);
  }

  const verify = sourceDb.getCollectionInfos({ name: SOURCE_COLLECTION })[0];
  const nowEnabled = Boolean(
    verify.options &&
    verify.options.changeStreamPreAndPostImages &&
    verify.options.changeStreamPreAndPostImages.enabled
  );
  if (!nowEnabled) {
    print("ABORT: collMod returned without error but the flag still reads as " +
      "disabled. Refusing to create the processor. Check the collection " +
      "manually with db.getCollectionInfos({name: \"" + SOURCE_COLLECTION + "\"}) " +
      "before retrying.");
    quit(1);
  }
  print("changeStreamPreAndPostImages enabled.");
}

// --- 2. Sanitização de nomes de campo antes do $iceberg ----------------------
//
// Iceberg é mais estrito que MongoDB: um campo com "." ou "$" no nome (válido
// em BSON) faz o estágio $iceberg derrubar o PROCESSOR INTEIRO --
// "The iceberg identifier ... cannot contain a '.' character" -- e isso NÃO
// cai na DLQ (ver docs/TROUBLESHOOTING.md). Um único documento malformado tira
// o pipeline inteiro do ar sem isolamento de falha por documento.
//
// Este estágio percorre o documento recursivamente e substitui "." e "$" em
// qualquer nome de chave (top-level ou aninhado, incluindo dentro de arrays)
// por "_", antes que o documento chegue ao $iceberg. Combinado com o `dlq`
// abaixo (que continua cobrindo Decimal128 e conflito de tipo), o processor
// não deve mais cair por causa de nome de campo.
const sanitizeFieldNames = {
  $addFields: {
    __sanitized: {
      $function: {
        body: function sanitize(value) {
          function clean(node) {
            if (Array.isArray(node)) {
              return node.map(clean);
            }
            if (node && typeof node === "object" &&
                !(node instanceof Date) && !node._bsontype) {
              const out = {};
              for (const key of Object.keys(node)) {
                const safeKey = key.replace(/[.$]/g, "_");
                out[safeKey] = clean(node[key]);
              }
              return out;
            }
            return node;
          }
          return clean(value);
        },
        args: ["$$ROOT"],
        lang: "js"
      }
    }
  }
};

const isDeleteExpr = {
  $eq: [{ $meta: "stream.source.operationType" }, "delete"]
};

const pipeline = [
  {
    $source: {
      connectionName: SOURCE_CONNECTION,
      db: SOURCE_DATABASE,
      coll: SOURCE_COLLECTION,
      initialSync: {
        enable: true
      },
      config: {
        fullDocument: "required"
      }
    }
  },
  {
    $match: {
      operationType: {
        $in: ["insert", "update", "delete", "replace"]
      }
    }
  },
  {
    $replaceRoot: {
      newRoot: {
        $cond: {
          if: isDeleteExpr,
          then: "$documentKey",
          else: "$fullDocument"
        }
      }
    }
  },
  // NOTE: $function support in Atlas Stream Processing pipelines should be
  // verified against the current ASP documentation for your Atlas version --
  // if $function is unavailable, replace this stage with an explicit $project
  // that lists and renames the known dotted/`$`-prefixed field paths in your
  // schema (less general, but works everywhere $project does).
  sanitizeFieldNames,
  { $replaceRoot: { newRoot: "$__sanitized" } },
  {
    $iceberg: {
      connectionName: S3_CONNECTION,
      bucket: S3_BUCKET,
      databaseName: ICEBERG_DATABASE,
      tableName: ICEBERG_TABLE,
      path: ICEBERG_PATH,
      region: AWS_REGION,
      mode: "cdc",
      idFieldName: "_id",
      catalog: {
        type: "glue"
      }
      // partitionBy: not supported by $iceberg in the ASP version this demo
      // was built against -- verified against docs as of 2026-09; see
      // docs/TROUBLESHOOTING.md and README for the note. Revisit if the
      // feature ships.
    }
  }
];

print(`Creating stream processor ${PROCESSOR_NAME}...`);
sp.createStreamProcessor(PROCESSOR_NAME, pipeline, {
  dlq: {
    connectionName: SOURCE_CONNECTION,
    db: DLQ_DB,
    coll: DLQ_COLL
  }
});

print(`Starting ${PROCESSOR_NAME} on SP10...`);
sp.ordersToIceberg.start({ tier: "SP10" });

print("Processor started. Use load(\"stream-processing/status.js\") to see stats.");
