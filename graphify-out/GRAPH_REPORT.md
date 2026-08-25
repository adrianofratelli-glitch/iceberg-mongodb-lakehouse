# Graph Report - .  (2026-08-25)

## Corpus Check
- Corpus is ~33,224 words - fits in a single context window. You may not need a graph.

## Summary
- 226 nodes · 305 edges · 23 communities (18 shown, 5 thin omitted)
- Extraction: 90% EXTRACTED · 10% INFERRED · 0% AMBIGUOUS · INFERRED: 29 edges (avg confidence: 0.81)
- Token cost: 0 input · 0 output

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

## God Nodes (most connected - your core abstractions)
1. `get_collection()` - 12 edges
2. `run_query()` - 10 edges
3. `collection()` - 9 edges
4. `client()` - 8 edges
5. `fmtBytes()` - 7 edges
6. `Pipeline $source/$match/$replaceRoot/$iceberg` - 7 edges
7. `utcnow()` - 6 edges
8. `AwsUnavailable` - 5 edges
9. `_friendly()` - 5 edges
10. `scripts` - 5 edges

## Surprising Connections (you probably didn't know these)
- `start.sh (backend 8250 + frontend 5250)` --references--> `Frontend index.html (React root, tema dark MongoDB)`  [INFERRED]
  CLAUDE.md → frontend/index.html
- `pov-signature.css sincronizada` --conceptually_related_to--> `Frontend index.html (React root, tema dark MongoDB)`  [INFERRED]
  CLAUDE.md → frontend/index.html
- `Near real-time, não tempo real` --conceptually_related_to--> `Lakehouse sem pipeline de ETL`  [INFERRED]
  docs/prompts/01-arquitetura.md → README.md
- `Latências medidas (insert ~10s, update ~20s, delete 30-60s)` --rationale_for--> `Near real-time, não tempo real`  [INFERRED]
  README.md → docs/prompts/01-arquitetura.md
- `Workspace de Stream Processing SP10` --conceptually_related_to--> `Workspace SP10 compartilhado com a PoV de PIX`  [INFERRED]
  setup/atlas/README.md → docs/prompts/01-arquitetura.md

## Import Cycles
- None detected.

## Hyperedges (group relationships)
- **Circuito CDC MongoDB → Iceberg → Athena** — docs_prompts_02_mongodb_orders_collection, docs_prompts_02_mongodb_change_stream_pre_post_images, docs_prompts_01_arquitetura_processor_orderstoiceberg, docs_prompts_02_mongodb_pipeline_processor, setup_aws_readme_glue_catalog, docs_prompts_02_mongodb_dlq [EXTRACTED 1.00]
- **Falhas medidas contra o ambiente real** — docs_troubleshooting_processor_morre_no_update, docs_troubleshooting_duplicacao_por_restart, docs_troubleshooting_campo_com_ponto, docs_troubleshooting_iam_permissions, docs_troubleshooting_iceberg_path_sem_barra, docs_troubleshooting_colunas_orfas, docs_troubleshooting_athena_result_location, docs_troubleshooting_credenciais_sso_expiram [EXTRACTED 1.00]
- **Ordem de montagem AWS + Atlas + seed** — setup_aws_readme_bootstrap_sh, setup_aws_readme_unified_aws_access, setup_atlas_readme_connection_atlas_orders, setup_atlas_readme_connection_s3_iceberg, docs_prompts_01_arquitetura_seed_orders_py, docs_prompts_01_arquitetura_preflight_py, setup_atlas_readme_create_processor_js [EXTRACTED 1.00]
- **Five-Screen Demo Walkthrough: convergence, CDC cycle, update, time travel, analytics** — docs_screenshots_01_duas_metades_screen, docs_screenshots_02_ciclo_cdc_screen, docs_screenshots_03_update_refletido_screen, docs_screenshots_04_time_travel_screen, docs_screenshots_05_consulta_analitica_screen [INFERRED 0.85]
- **No-ETL CDC Circuit: pipeline, propagation latency, mutable rows, convergence** — docs_architecture_pipeline_mdb_to_iceberg, docs_screenshots_02_ciclo_cdc_propagation_latency, docs_screenshots_03_update_refletido_mutable_table, docs_screenshots_01_duas_metades_convergence [INFERRED 0.85]
- **Iceberg Table Capabilities: snapshots, format-native versioning, Athena analytics, Glue catalog** — docs_screenshots_04_time_travel_snapshot_history, docs_screenshots_04_time_travel_versioning_from_format, docs_screenshots_05_consulta_analitica_business_aggregation, docs_architecture_glue_metadata_update [INFERRED 0.75]

## Communities (23 total, 5 thin omitted)

### Community 0 - "Scripts da Demo CDC"
Cohesion: 0.09
Nodes (25): main(), get_collection(), _load_config(), datetime, Import config with a readable error when .env is missing or incomplete., utcnow(), validate_config(), main() (+17 more)

### Community 1 - "Tese e Invariantes da PoV"
Cohesion: 0.09
Nodes (24): PoV Iceberg + MongoDB Lakehouse, Circuito Atlas → Stream Processing → Iceberg → Glue → Athena, Near real-time, não tempo real, scripts/preflight.py, Processor ordersToIceberg, scripts/seed_orders.py, changeStreamPreAndPostImages, Decimal128 rejeitado para a DLQ (+16 more)

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
Cohesion: 0.22
Nodes (17): client(), collection(), demo_delete(), demo_insert(), demo_reset(), demo_schema_field(), demo_update(), dlq() (+9 more)

### Community 8 - "Contrato de Interface e Consistência"
Cohesion: 0.22
Nodes (9): pov-signature.css sincronizada, start.sh (backend 8250 + frontend 5250), MongoDB é a fonte da verdade, Iceberg é derivado, Verificação de consistência total vs distinct _id, O Athena continua sendo a prova de formato aberto, As quatro seções da interface, Duplicação da tabela por restart sem checkpoint, Frontend index.html (React root, tema dark MongoDB) (+1 more)

### Community 9 - "Roteiro da Demo e Time Travel"
Cohesion: 0.25
Nodes (8): Ciclo CDC insert/update/delete, Demo Flow: operacional ao lakehouse em 5 minutos, Schema evolution via fraudScore, sql/08_time_travel.sql, Roteiro da demo (~8 min), Athena exige query result location, Colunas de documentos antigos permanecem no schema, Time travel via snapshots Iceberg

### Community 10 - "Provisionamento AWS e Atlas"
Cohesion: 0.33
Nodes (7): Ordem de montagem AWS + Atlas, Permissões IAM de S3 e Glue para a role do Atlas, Connection atlas-orders, Connection s3-iceberg, setup/aws/bootstrap.sh, Glue Data Catalog + bucket S3, Unified AWS Access

### Community 11 - "Launcher start.sh"
Cohesion: 0.70
Nodes (4): cleanup(), fail(), start.sh script, wait_for_url()

### Community 12 - "Separação de Stacks e Venvs"
Cohesion: 0.50
Nodes (4): Stack do backend (FastAPI, pymongo, boto3), Dois venvs separados, Backend nunca escreve no Iceberg, Stack dos scripts de demo (pymongo, dotenv)

### Community 13 - "Argumento de Custo Analítico"
Cohesion: 0.50
Nodes (4): scripts/compare_aggregation.py, sql/06_pergunta_de_negocio.sql, Argumento de custo: analítico não roda no cluster operacional, Ideias para fortalecer: volume, compaction, segundo consumidor

## Knowledge Gaps
- **36 isolated node(s):** `name`, `version`, `private`, `description`, `dev` (+31 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **5 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `get_collection()` connect `Scripts da Demo CDC` to `Escrita no MongoDB`?**
  _High betweenness centrality (0.082) - this node is a cross-community bridge._
- **Why does `client()` connect `Escrita no MongoDB` to `Leitura do Iceberg (Athena/Glue)`?**
  _High betweenness centrality (0.080) - this node is a cross-community bridge._
- **Are the 10 inferred relationships involving `get_collection()` (e.g. with `main()` and `MongoClient`) actually correct?**
  _`get_collection()` has 10 INFERRED edges - model-reasoned connections that need verification._
- **What connects `Everything that touches the Iceberg table: Athena and Glue.  Degrades on purpose`, `No usable AWS credentials.`, `Run one Athena query and return columns plus rows.` to the rest of the system?**
  _66 weakly-connected nodes found - possible documentation gaps or missing edges._
- **Should `Scripts da Demo CDC` be split into smaller, more focused modules?**
  _Cohesion score 0.0907563025210084 - nodes in this community are weakly interconnected._
- **Should `Tese e Invariantes da PoV` be split into smaller, more focused modules?**
  _Cohesion score 0.09057971014492754 - nodes in this community are weakly interconnected._
- **Should `API FastAPI` be split into smaller, more focused modules?**
  _Cohesion score 0.10526315789473684 - nodes in this community are weakly interconnected._