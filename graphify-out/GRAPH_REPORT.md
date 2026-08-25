# Graph Report - iceberg-mongodb-lakehouse  (2026-08-25)

## Corpus Check
- 50 files · ~31,487 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 306 nodes · 333 edges · 74 communities (19 shown, 55 thin omitted)
- Extraction: 94% EXTRACTED · 6% INFERRED · 0% AMBIGUOUS · INFERRED: 21 edges (avg confidence: 0.8)
- Token cost: 0 input · 0 output

## Graph Freshness
- Built from commit: `183cd2d0`
- Run `git rev-parse HEAD` and compare to check if the graph is stale.
- Run `graphify update .` after code changes (no API cost).

## Community Hubs (Navigation)
- Scripts da Demo CDC
- Tese e Invariantes da PoV
- API FastAPI
- Arquitetura e Telas da Demo
- Frontend React
- Dependências do Frontend
- Leitura do Iceberg (Athena/Glue)
- Escrita no MongoDB
- Contrato de Interface e Consistência
- Roteiro da Demo e Time Travel
- Provisionamento AWS e Atlas
- Launcher start.sh
- Separação de Stacks e Venvs
- Argumento de Custo Analítico
- Pipeline do Stream Processor
- Configuração por Ambiente
- Workspace SP10 Compartilhado
- Proxy do Vite
- Bootstrap do Bucket e Glue
- Iceberg + MongoDB
- Demo
- Troubleshooting
- 03 — Interface e fluxos
- Atlas Setup
- preflight.py
- AWS Setup
- Demo Flow: operacional ao lakehouse em 5 minutos
- Schema evolution via fraudScore
- Backend nunca escreve no Iceberg
- Circuito Atlas → Stream Processing → Iceberg → Glue → Athena
- Near real-time, não tempo real
- scripts/preflight.py
- Processor ordersToIceberg
- scripts/seed_orders.py
- sql/06_pergunta_de_negocio.sql
- sql/08_time_travel.sql
- changeStreamPreAndPostImages
- Decimal128 rejeitado para a DLQ
- _id string com significado de negócio como idFieldName
- Coleção iceberg_demo.orders
- Pipeline $source/$match/$replaceRoot/$iceberg
- $replaceRoot condicional para delete
- Verificação de consistência total vs distinct _id
- Argumento de custo: analítico não roda no cluster operacional
- O Athena continua sendo a prova de formato aberto
- Degradação intencional sem credencial AWS
- Ideias para fortalecer: volume, compaction, segundo consumidor
- As quatro seções da interface
- Roteiro da demo (~8 min)
- Athena exige query result location
- Nome de campo com ponto derruba o processor
- Colunas de documentos antigos permanecem no schema
- Credenciais SSO da AWS expiram
- Duplicação da tabela por restart sem checkpoint
- ICEBERG_PATH sem barra final
- Processor morre no primeiro UPDATE (post-image ausente)
- Frontend index.html (React root, tema dark MongoDB)
- Tese da PoV: coleção operacional vira tabela Iceberg sem ETL
- Latências medidas (insert ~10s, update ~20s, delete 30-60s)
- Lakehouse sem pipeline de ETL
- Time travel via snapshots Iceberg
- mongodb-developer/Iceberg-MongoDB-Demo
- Stack dos scripts de demo (pymongo, dotenv)
- Connection atlas-orders
- Connection s3-iceberg
- stream-processing/create_processor.js
- Workspace de Stream Processing SP10
- setup/aws/bootstrap.sh
- Glue Data Catalog + bucket S3
- Unified AWS Access

## God Nodes (most connected - your core abstractions)
1. `get_collection()` - 12 edges
2. `Troubleshooting` - 11 edges
3. `run_query()` - 10 edges
4. `collection()` - 9 edges
5. `03 — Interface e fluxos` - 9 edges
6. `client()` - 8 edges
7. `Notas de desenvolvimento` - 8 edges
8. `Atlas Setup` - 8 edges
9. `fmtBytes()` - 7 edges
10. `Iceberg + MongoDB` - 7 edges

## Surprising Connections (you probably didn't know these)
- `main()` --calls--> `get_collection()`  [INFERRED]
  scripts/compare_aggregation.py → scripts/common.py
- `main()` --calls--> `get_collection()`  [INFERRED]
  scripts/delete_order.py → scripts/common.py
- `main()` --calls--> `get_collection()`  [INFERRED]
  scripts/preflight.py → scripts/common.py
- `main()` --calls--> `get_collection()`  [INFERRED]
  scripts/reset_demo.py → scripts/common.py
- `main()` --calls--> `get_collection()`  [INFERRED]
  scripts/update_order.py → scripts/common.py

## Import Cycles
- None detected.

## Hyperedges (group relationships)
- **Five-Screen Demo Walkthrough: convergence, CDC cycle, update, time travel, analytics** — docs_screenshots_01_duas_metades_screen, docs_screenshots_02_ciclo_cdc_screen, docs_screenshots_03_update_refletido_screen, docs_screenshots_04_time_travel_screen, docs_screenshots_05_consulta_analitica_screen [INFERRED 0.85]
- **No-ETL CDC Circuit: pipeline, propagation latency, mutable rows, convergence** — docs_architecture_pipeline_mdb_to_iceberg, docs_screenshots_02_ciclo_cdc_propagation_latency, docs_screenshots_03_update_refletido_mutable_table, docs_screenshots_01_duas_metades_convergence [INFERRED 0.85]
- **Iceberg Table Capabilities: snapshots, format-native versioning, Athena analytics, Glue catalog** — docs_screenshots_04_time_travel_snapshot_history, docs_screenshots_04_time_travel_versioning_from_format, docs_screenshots_05_consulta_analitica_business_aggregation, docs_architecture_glue_metadata_update [INFERRED 0.75]

## Communities (74 total, 55 thin omitted)

### Community 0 - "Scripts da Demo CDC"
Cohesion: 0.11
Nodes (20): MongoClient, main(), get_collection(), _load_config(), datetime, Import config with a readable error when .env is missing or incomplete., utcnow(), validate_config() (+12 more)

### Community 1 - "Tese e Invariantes da PoV"
Cohesion: 0.06
Nodes (26): AWS, Comandos, Dois venvs, Grafo de código, Interface, Invariantes que quebram a demo, Notas de desenvolvimento, O que é (+18 more)

### Community 2 - "API FastAPI"
Cohesion: 0.11
Nodes (9): consultas(), OperacaoResposta, preflight(), API da PoV Iceberg + MongoDB.  Duas metades: o cluster operacional (MongoDB) e a, O mesmo diagnóstico do scripts/preflight.py, servido para a interface., _titulo(), Backend configuration, read from the repository .env., BaseModel (+1 more)

### Community 3 - "Arquitetura e Telas da Demo"
Cohesion: 0.13
Nodes (20): Iceberg Example Architecture Diagram, Downstream Engines Read the Same Table (Databricks, Snowflake), AWS Glue Metadata Update Path, MongoDB OLTP to Managed Iceberg Table on S3 via Atlas Stream Processing, Processors Assemble Data Close to the Source, Convergence Check: MongoDB Count Equals Iceberg Row Count, Screenshot: Two Halves of the Circuit, MongoDB is Source of Truth, Iceberg is Derived (+12 more)

### Community 4 - "Frontend React"
Cohesion: 0.26
Nodes (11): api, fmtBRL(), fmtBytes(), fmtInt(), App(), AvisoAws(), CicloCdc(), PASSOS (+3 more)

### Community 5 - "Dependências do Frontend"
Cohesion: 0.11
Nodes (18): author, dependencies, react, react-dom, vite, @vitejs/plugin-react, description, keywords (+10 more)

### Community 6 - "Leitura do Iceberg (Athena/Glue)"
Cohesion: 0.21
Nodes (17): AwsUnavailable, _client(), counts(), find_order(), _friendly(), identity(), order_at_snapshot(), Everything that touches the Iceberg table: Athena and Glue.  Degrades on purpose (+9 more)

### Community 7 - "Escrita no MongoDB"
Cohesion: 0.24
Nodes (16): client(), collection(), demo_delete(), demo_insert(), demo_reset(), demo_schema_field(), demo_update(), dlq() (+8 more)

### Community 11 - "Launcher start.sh"
Cohesion: 0.70
Nodes (4): cleanup(), fail(), start.sh script, wait_for_url()

### Community 23 - "Iceberg + MongoDB"
Cohesion: 0.15
Nodes (12): 1. Two halves of one circuit, 2. An order enters through the transactional path, 3. The update lands in the lake, 4. Time travel comes free with the format, 5. The question nobody runs on the operational cluster, Before every demo, Driving the demo from the CLI, Iceberg + MongoDB (+4 more)

### Community 24 - "Demo"
Cohesion: 0.18
Nodes (10): 1. Establish the baseline, 2. Insert, 3. Update, 4. Delete, 5. Schema evolution, Before the meeting, Cleanup, Close (+2 more)

### Community 25 - "Troubleshooting"
Cohesion: 0.18
Nodes (11): `another operation "RestartStreamProcessor..." has the lock`, Athena: the Run button stays disabled, AWS credentials keep expiring, Columns from old documents stay in the table, Documents that never reach Iceberg, Duplicate rows in Athena after a restart, `Invalid $iceberg.path: cannot end with a '/' character`, `is not authorized to perform: s3:PutObject` (+3 more)

### Community 26 - "03 — Interface e fluxos"
Cohesion: 0.22
Nodes (9): 03 — Interface e fluxos, Antes de apresentar, As quatro capacidades da interface, Depois da demo, Estado atual — modo palco, Ideias para fortalecer, Números medidos (2026-08-24), O que dizer e o que não dizer (+1 more)

### Community 27 - "Atlas Setup"
Cohesion: 0.22
Nodes (8): 1. Atlas Cluster, 2. Stream Processing Workspace, 3. Atlas Source Connection, 4. S3 Connection, 5. Stream Processing Database User, 6. Create the Processor, Atlas Setup, Cross-Cloud

### Community 28 - "preflight.py"
Cohesion: 0.38
Nodes (6): check_aws(), main(), Run this before every demo.  Checks the MongoDB side of the pipeline and fixes w, Return a profile name configured for SSO, if any., Credentials for Athena/Glue expire; surface that before the demo starts., _sso_profile()

## Knowledge Gaps
- **126 isolated node(s):** `name`, `version`, `private`, `description`, `dev` (+121 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **55 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `get_collection()` connect `Scripts da Demo CDC` to `preflight.py`?**
  _High betweenness centrality (0.045) - this node is a cross-community bridge._
- **Why does `client()` connect `Escrita no MongoDB` to `Scripts da Demo CDC`, `Leitura do Iceberg (Athena/Glue)`?**
  _High betweenness centrality (0.044) - this node is a cross-community bridge._
- **Are the 10 inferred relationships involving `get_collection()` (e.g. with `main()` and `MongoClient`) actually correct?**
  _`get_collection()` has 10 INFERRED edges - model-reasoned connections that need verification._
- **What connects `Everything that touches the Iceberg table: Athena and Glue.  Degrades on purpose`, `No usable AWS credentials.`, `Run one Athena query and return columns plus rows.` to the rest of the system?**
  _157 weakly-connected nodes found - possible documentation gaps or missing edges._
- **Should `Scripts da Demo CDC` be split into smaller, more focused modules?**
  _Cohesion score 0.11083743842364532 - nodes in this community are weakly interconnected._
- **Should `Tese e Invariantes da PoV` be split into smaller, more focused modules?**
  _Cohesion score 0.0625 - nodes in this community are weakly interconnected._
- **Should `API FastAPI` be split into smaller, more focused modules?**
  _Cohesion score 0.10526315789473684 - nodes in this community are weakly interconnected._