# Mapa do código — iceberg-mongodb-lakehouse

> Também conhecida como: Iceberg lakehouse. Portas: frontend 5250 / backend 8250. Em uma frase: o MongoDB Atlas é o banco operacional, o Atlas Stream Processing replica cada mudança (CDC) para uma tabela Apache Iceberg no S3, e a tela mostra as duas metades convergindo (Athena lê o Iceberg).

Detalhes de queries e telas: [briefing/queries.md](briefing/queries.md), [briefing/ui-flows.md](briefing/ui-flows.md), [briefing/architecture.md](briefing/architecture.md). Este mapa só aponta onde está o código.

## 1. Árvore anotada

```
backend/                    API FastAPI (porta 8250)
  main.py                   todas as rotas + safe_error (mascara URI/host/ID AWS antes de ir ao navegador)
  mongo_side.py             tudo que fala com o Atlas (pymongo): visão geral, find, as 4 operações da demo, reset
  athena_side.py            tudo que fala com a AWS: Athena (SQL), Glue (colunas), retry, credencial recarregada a cada chamada
  lag_side.py               distância checkpoint do processor x janela do oplog (usa mongosh + local.oplog.rs)
  settings.py               lê o .env da raiz (nomes de banco, bucket, workgroup, IDs dos pedidos ao vivo)
  tests/                    testes pytest (ver seção 6)
frontend/                   React + Vite (porta 5250, proxy /api e /preflight para 8250: vite.config.js)
  src/App.jsx               tela única: topbar, cards das duas metades, seções colapsáveis
  src/api.js                cliente HTTP (um método por rota) e formatadores
  src/components/CicloCdc.jsx     botões INSERT/UPDATE/DELETE/CAMPO NOVO/Limpar + polling de propagação
  src/components/TimeTravel.jsx   lista de snapshots Iceberg e "pedido naquele snapshot"
  src/components/Consultas.jsx    botões das consultas SQL da pasta sql/
  src/components/QueryDetails.jsx painel "ver query executada" (mascara segredos)
  src/components/Tabela.jsx, AvisoAws.jsx   tabela genérica e aviso de credencial AWS
  src/pov-signature.css, index.css          estilos (o pov-signature é de marca)
  tests/http-deadline.test.mjs              teste do prazo de requisição (node --test)
scripts/                    CLI Python: seed, reset, operações manuais, preflight, medição de CDC
  config.py                 lê MONGODB_URI/DATABASE_NAME/COLLECTION_NAME do .env
  common.py                 conexão, validação de config, trava assert_safe_target (só banco *_test ou ALLOW_DEMO_DB_WRITE=1)
  seed_orders.py            gera os 5.000 pedidos determinísticos
  reset_demo.py             volta tudo ao estado inicial (idempotente)
  insert_order.py / update_order.py / delete_order.py / add_schema_field.py   as 4 operações da demo, via terminal
  live_demo.py              roteiro interativo (ENTER entre passos)
  preflight.py              checagens antes da demo (conexão, post-images, DLQ, credencial AWS)
  compare_aggregation.py    roda no Mongo a mesma pergunta de negócio do sql/06 e mostra COLLSCAN
  cdc_probe.py              mede latência write -> change event (só em iceberg_demo_test)
sql/                        8 consultas Athena (01..08), listadas e executadas pela UI
stream-processing/          scripts mongosh/py do Atlas Stream Processing (o CDC de verdade)
  create_processor.js       cria o processor ordersToIceberg ($source -> sanitização -> $iceberg)
  restart_processor.js / stop_processor.js / drop_processor.js / status.js   ciclo de vida do processor
  rebuild_table.py          DROP da tabela Iceberg antes de reiniciar sem checkpoint (evita duplicar)
setup/                      atlas/README.md e aws/ (README + bootstrap.sh: bucket S3, Glue, Athena)
docs/                       DEMO_FLOW, TROUBLESHOOTING, DEV_NOTES, briefing/, screenshots/
start.sh                    sobe backend (8250) e frontend (5250)
```

Peça central que NÃO está no backend: o CDC roda dentro do Atlas Stream Processing, definido em `stream-processing/create_processor.js`. O backend não escreve no Iceberg; só lê (Athena) e escreve no Mongo.

## 2. "Apertei o botão X, o que roda?"

Rotas em `backend/main.py`; cliente em `frontend/src/api.js:26-39`.

| Tela / botão | Componente | Chamada HTTP | Handler | Função de negócio | Onde toca o MongoDB / AWS |
|---|---|---|---|---|---|
| Abrir a página (cards "duas metades", pill de estado) | `App.jsx:15-18` (`carregar`) | `GET /api/visao-geral` | `main.py:122` `visao_geral` | `mongo_side.py::overview` + `athena_side.py::counts` | Mongo: `count_documents`, 2x `aggregate` em `orders`, `count_documents` em `dlq` (`mongo_side.py:61-104`). Athena: `count(*)`/`count(DISTINCT _id)` (`athena_side.py:173`) |
| Abrir a página (contagem de colunas) | `App.jsx:17` | `GET /api/schema` | `main.py:145` `schema` | `athena_side.py::table_columns` | Glue `get_table` (`athena_side.py:160`); sem Mongo |
| Abrir a página (avisos de pré-requisito) | `App.jsx:22` | `GET /preflight` | `main.py:66` `preflight` | `mongo_side.py::ping`, `post_images_enabled`, `dlq`; `athena_side.py::identity` | Mongo: `ping`, `list_collections` (`mongo_side.py:40`), `count_documents` em `dlq` |
| Abrir a página (pill de lag do checkpoint) | `App.jsx:23, 80-86` | `GET /api/lag` | `main.py:253` `lag` | `lag_side.py::processor_lag` (`:136`) | Mongo: `find_one` ordenado por `$natural` em `local.oplog.rs` (`lag_side.py:119-121`) e `mongosh` externo `sp.<processor>.stats()` (`lag_side.py:41`) |
| Reconsulta automática a cada 8 s quando o Iceberg está fora | `App.jsx:33-43` | as mesmas rotas acima | idem | idem | idem |
| "Corrigir agora" (aviso post-images) | `App.jsx:105` | `POST /api/corrigir/post-images` | `main.py:268` `corrigir_post_images` | `mongo_side.py::enable_post_images` (`:52`) | Mongo: `collMod` com `changeStreamPreAndPostImages` em `orders` |
| INSERT | `CicloCdc.jsx:110-118` -> `executar` (`:73`) | `POST /api/demo/insert` | `main.py:176` `demo` | `mongo_side.py::demo_insert` (`:113`) | `replace_one(upsert)` em `orders` (`:129`) |
| UPDATE | idem | `POST /api/demo/update` | idem | `mongo_side.py::demo_update` (`:133`) | `update_one` `$set` + `find_one` em `orders`; 409 se não existir |
| DELETE | idem | `POST /api/demo/delete` | idem | `mongo_side.py::demo_delete` (`:143`) | `delete_one` em `orders` |
| CAMPO NOVO | idem | `POST /api/demo/schema` | idem | `mongo_side.py::demo_schema_field` (`:148`) | `replace_one(upsert)` do `PED-AOVIVO-002` com `fraudScore` (`:162`) |
| Limpar | `CicloCdc.jsx:121` -> `resetar` (`:89`) | `POST /api/demo/reset` | `main.py:176` `demo` | `mongo_side.py::demo_reset` (`:166`) | `delete_many` dos 2 IDs ao vivo + `count_documents` em `orders` |
| Polling após cada operação (a cada 3 s, até 40x) | `CicloCdc.jsx:34-60` (`esperarPropagacao`) | `GET /api/pedido/{order_id}` | `main.py:154` `pedido` | `mongo_side.py::find_order` + `athena_side.py::find_order` | Mongo `find_one` por `_id` (`mongo_side.py:108`); Athena `SELECT ... WHERE _id` (`athena_side.py:187`) |
| "Ver query / chamada executada" | `QueryDetails.jsx` (usa `query_details` da resposta do `demo`) | nenhuma (dado vem da resposta do passo acima) | `main.py:236-250` monta `query_details` | texto montado em `main.py:209-235` (espelha as chamadas reais) | só exibição |
| Time travel: abrir a seção | `TimeTravel.jsx:13-21` (`carregar`) | `GET /api/snapshots` | `main.py:281` `snapshots` | `athena_side.py::snapshots` (`:195`) | Athena em `"orders$snapshots"`; sem Mongo |
| Time travel: clicar numa linha | `TimeTravel.jsx:23` (`consultar`) | `GET /api/snapshots/{snapshot_id}/pedido/{order_id}` | `main.py:289` `pedido_no_snapshot` | `athena_side.py::order_at_snapshot` (`:205`) | Athena `FOR VERSION AS OF`; sem Mongo |
| Consultas analíticas: abrir a seção | `Consultas.jsx:13-15` | `GET /api/consultas` | `main.py:302` `consultas` | lista `sql/*.sql` (`_titulo`, `main.py:312`) | nenhum |
| Consultas analíticas: botão de cada consulta | `Consultas.jsx:17` (`rodar`), botão `:38` | `POST /api/consultas/{id}` | `main.py:319` `rodar_consulta` | `athena_side.py::run_query` (`:75`) com o SQL do arquivo | Athena; sem Mongo |

Observação: não há upload, chat nem rota de login. Os botões de "reset completo com 5.000 pedidos" só existem na linha de comando (`scripts/reset_demo.py`); o "Limpar" da UI remove só os 2 pedidos ao vivo.

## 3. Onde estão as queries MongoDB

Levantamento completo com texto das queries: [briefing/queries.md](briefing/queries.md). Não há índice criado no repositório (só o `_id` nativo).

| O que faz | arquivo::função (linha) | Operador / pipeline principal | Collection |
|---|---|---|---|
| Total de pedidos | `backend/mongo_side.py::overview` (:63) | `count_documents({})` | `orders` |
| Pedidos por status | `mongo_side.py::overview` (:64-68) | `aggregate` `$group` + `$sort` | `orders` |
| Receita e primeiro/último pedido | `mongo_side.py::overview` (:69-96) | `aggregate` `$group` com `$convert` (tolera `amount` string/Decimal128) | `orders` |
| Documentos na DLQ | `mongo_side.py::overview` (:103) e `main.py::preflight` (:82) | `count_documents` | `dlq` |
| Buscar pedido | `mongo_side.py::find_order` (:107) | `find_one({_id})` | `orders` |
| Ver se post-images está ligado | `mongo_side.py::post_images_enabled` (:40) | `list_collections` | `orders` |
| Ligar post-images | `mongo_side.py::enable_post_images` (:52) | comando `collMod` | `orders` |
| INSERT / CAMPO NOVO | `mongo_side.py::demo_insert` (:129), `demo_schema_field` (:162) | `replace_one(upsert=True)` | `orders` |
| UPDATE | `mongo_side.py::demo_update` (:134) | `update_one` `$set` | `orders` |
| DELETE / reset da UI | `mongo_side.py::demo_delete` (:144), `demo_reset` (:166) | `delete_one`, `delete_many $in` | `orders` |
| Janela do oplog | `backend/lag_side.py::_oplog_window` (:112; finds em :120-121) | `find_one` com `sort $natural` 1 e -1 | `local.oplog.rs` |
| Estatísticas do processor | `lag_side.py::_run_mongosh_stats` (:41) | `mongosh --eval sp.<nome>.stats()` (workspace do Stream Processing, não pymongo) | n/a |
| Seed dos 5.000 pedidos | `scripts/seed_orders.py::seed` (:115) | `ReplaceOne(upsert)` em lotes | `orders` |
| Reset completo | `scripts/reset_demo.py::reset` (:51-58) e `ensure_collection` (:35-47) | `create_collection`/`collMod`, `delete_many` (ao vivo, `$nin` do seed), `delete_many({})` na DLQ | `orders`, `dlq` |
| Pergunta de negócio no Mongo | `scripts/compare_aggregation.py` (PIPELINE :17; run :44; `explain` :47) | `$group` por região/mês, `$sort`, `$limit`; `explain` executionStats | `orders` |
| Inspeção da DLQ | `scripts/preflight.py` (:120) | `find().limit(3)` | `dlq` |
| Operações manuais CLI | `scripts/insert_order.py`, `update_order.py`, `delete_order.py`, `add_schema_field.py`, `live_demo.py` | `find_one`/`delete_one`/`insert`/`update_one` | `orders` |
| Medição de CDC | `scripts/cdc_probe.py` (:56 cria coleção com post-images; :72-74, :95, :105, :128, :150) | change stream + escritas de teste | coleção de sonda em `iceberg_demo_test` |
| Change stream do processor (CDC real) | `stream-processing/create_processor.js` (`$source` :161; `$match` :174; `$replaceRoot` :181; sanitização `$function` :129; `$iceberg` :199; `createStreamProcessor` :220) | `$source` com `initialSync` e `fullDocument: "required"` -> `$iceberg` | `iceberg_demo.orders` -> S3/Glue |

Consultas Athena (não são Mongo): `sql/01..08` e as de `backend/athena_side.py` (`counts` :173, `find_order` :187, `snapshots` :195, `order_at_snapshot` :205, `drop_table` :147).

## 4. Compartilhado × só desta PoV

- **`_shared`**: nenhum. Não há import de `_shared` neste repositório (conferido com busca). O backend usa direto `pymongo`, `boto3`, `fastapi`.
- **Variáveis de ambiente** (todas lidas em `backend/settings.py` e `scripts/config.py`; o `.env` fica na raiz; modelo em `.env.example`):
  - `MONGODB_URI` (cluster; vem do ambiente comum do portfólio), `DATABASE_NAME`, `COLLECTION_NAME` (banco/coleção da demo).
  - AWS: `AWS_REGION`, `S3_BUCKET`, `GLUE_DATABASE`, `ICEBERG_TABLE`, `ATHENA_WORKGROUP`, `ATHENA_OUTPUT` (locais desta PoV). A credencial AWS não está no `.env`: o `boto3` lê `~/.aws/credentials`/SSO, em sessão nova a cada chamada (`athena_side.py:21-27`).
  - Lag opcional: `STREAM_PROCESSING_URI`, `PROCESSOR_NAME`, `MONGOSH_PATH`.
  - Trava: `ALLOW_DEMO_DB_WRITE=1` para escrever no banco da demo; `SEED_ANCHOR` para mudar a data-âncora do seed.
  - Não confirmei no repositório qual dessas vêm do `.env.shared` via `sync_env`; o `.env.example` não cita isso.
- **Bancos/coleções**: `iceberg_demo.orders` e `iceberg_demo.dlq` (exclusivos desta PoV por padrão); testes usam `iceberg_demo_test`. Glue: banco `mongodb_iceberg_demo`, tabela `orders`.
- **Chamadas externas**: Athena e Glue em `backend/athena_side.py` (`_client`, `_run_query_once`); Atlas Stream Processing via `mongosh` em `backend/lag_side.py`. Sem LLM, sem Voyage, sem Langfuse.

## 5. "Quero mexer em..."

- Texto/botões do ciclo CDC -> `frontend/src/components/CicloCdc.jsx` (`PASSOS`, linha 6).
- O pedido que o INSERT/UPDATE cria (campos, valores) -> `backend/mongo_side.py::demo_insert` (:113) e `demo_update` (:133); e o espelho exibido em `backend/main.py:209-235` (`calls`).
- Os IDs dos pedidos ao vivo -> `backend/settings.py` (`LIVE_ORDER_ID`, `SCHEMA_ORDER_ID`); a UI repete `PED-AOVIVO-001` em `TimeTravel.jsx:27`.
- Uma consulta analítica -> edite o arquivo em `sql/` (aparece sozinha na UI; título = primeiro comentário `--`). Rota: `backend/main.py:302-337`.
- Adicionar uma rota -> `backend/main.py` + método em `frontend/src/api.js:26`.
- Query do card MongoDB -> `backend/mongo_side.py::overview` (:61).
- Quantidade/formato do seed -> `scripts/seed_orders.py` (`SEED_COUNT`, âncora de data em `DEFAULT_ANCHOR`).
- O pipeline do CDC (o que vira linha no Iceberg) -> `stream-processing/create_processor.js` (`pipeline`, :160+); depois reiniciar com `restart_processor.js` e `rebuild_table.py`.
- Limiares do alerta de lag -> `backend/lag_side.py::processor_lag` (:136).
- Tempo/limite do polling da UI -> `CicloCdc.jsx` (`LIMITE_TENTATIVAS`, `INTERVALO_MS`, :33-34).
- Mudar porta -> `start.sh` (:35-71), `frontend/vite.config.js`, CORS em `backend/main.py:26`.
- Estado da pill (convergido/propagando/duplicada) -> `frontend/src/App.jsx` (`estado`, :54).
- Máscara de erro -> `backend/main.py::safe_error` (:48).

## 6. Testes

Comandos (do README, "Adversarial tests"): `backend/venv/bin/pytest -q backend/tests` (offline, só mocks); `LIVE_ATLAS=1 backend/venv/bin/pytest -q backend/tests/test_live_cdc_adversarial.py` (roda em `iceberg_demo_test`); `cd frontend && node --test tests/*.test.mjs`.

- `backend/tests/test_adversarial.py` — timeout do Athena cancela a execução; IDs/snapshots inválidos são barrados; consulta fora de `sql/` nunca é lida.
- `backend/tests/test_hardening_adversarial.py` — `safe_error` mascara segredos, rotas degradam (503/502) sem 500, `query_details` mostra a escrita idempotente, reset recusa banco da demo sem flag, seed estável.
- `backend/tests/test_client_concurrency.py` — partida a frio concorrente cria um único pool Mongo.
- `backend/tests/test_credentials_refresh.py` — credencial nova no arquivo vale sem reiniciar.
- `backend/tests/test_retry_identity.py` — retry do Athena reaproveita a identidade da execução.
- `backend/tests/test_live_cdc_adversarial.py` — (live) duplo clique idempotente, schema drift, chaves com ponto/unicode, documento perto do limite.
- `frontend/tests/http-deadline.test.mjs` — prazo das requisições do `api.js`.
