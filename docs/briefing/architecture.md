# Arquitetura

## O que é essa PoV

CDC (Change Data Capture) do MongoDB Atlas para uma tabela Apache Iceberg no
S3, sem pipeline próprio: quem replica é o **Atlas Stream Processing (ASP)**,
não um job que o time escreveu. A tese que a demo prova: insert, update,
delete e evolução de schema chegam ao lake sozinhos, e uma consulta analítica
pesada roda sobre o S3/Athena sem disputar recursos com o cluster
transacional.

```
MongoDB Atlas (orders) --change stream--> Atlas Stream Processing
                                                 |
                                                 v
                                     estágio $iceberg (ASP)
                                                 |
                                                 v
                                   Apache Iceberg em S3, catálogo Glue
                                                 |
                                                 v
                                              Athena (SQL)
```

## Stack

| Camada | Tecnologia | Onde |
|---|---|---|
| Cluster operacional | MongoDB Atlas | `iceberg_demo.orders` |
| Réplica CDC → lake | Atlas Stream Processing | `stream-processing/create_processor.js` |
| Storage do lake | Apache Iceberg sobre S3 | bucket configurado em `.env` (`S3_BUCKET`) |
| Catálogo | AWS Glue | `GLUE_DATABASE` (default `mongodb_iceberg_demo`) |
| Consulta analítica | AWS Athena | `sql/*.sql`, `backend/athena_side.py` |
| Backend | FastAPI (Python) | `backend/main.py`, porta 8250 |
| Frontend | React (Vite) | `frontend/src/`, porta 5250 |
| Monitor de lag | mongosh (subprocess) + oplog | `backend/lag_side.py` |

Dois ambientes Python separados de propósito: `.venv/` na raiz roda os
scripts de demo (só precisa de `pymongo`); `backend/venv/` roda o FastAPI
(precisa também de `boto3` e `fastapi`).

## Componentes

### 1. Cluster MongoDB Atlas (fonte da verdade)
Coleção `orders` no banco `iceberg_demo`. `_id` é a chave de negócio
(`PED-<AAAAMM>-<seq>` para o seed, `PED-AOVIVO-001`/`002` para a demo ao
vivo). Sem índices adicionais além do índice único nativo em `_id` — não há
`create_index`/`createIndex` neste repositório; ver `docs/briefing/queries.md`
para o porquê.

Pré-requisito não óbvio: `changeStreamPreAndPostImages` precisa estar
habilitado na coleção. Sem isso, o `$source` do processor (que usa
`fullDocument: "required"`) morre silenciosamente no primeiro UPDATE — INSERT
e DELETE mascaram o problema porque não dependem de post-image. Três lugares
verificam/corrigem isso: `scripts/preflight.py`, `POST
/api/corrigir/post-images` (backend) e o próprio
`stream-processing/create_processor.js`, que agora aborta a criação do
processor se não conseguir habilitar a flag.

### 2. Atlas Stream Processing (o "ETL" que não existe)
`stream-processing/create_processor.js` define o processor `ordersToIceberg`.
Pipeline, em ordem:

1. `$source` — lê o change stream da coleção `orders`, com `initialSync`
   habilitado (carga inicial + eventos incrementais) e `fullDocument:
   "required"`.
2. `$match` — filtra `insert`, `update`, `delete`, `replace`.
3. `$replaceRoot` — para delete usa `documentKey` (só o `_id`, para permitir
   a remoção no Iceberg); para os demais usa `fullDocument` completo.
4. `sanitizeFieldNames` (`$addFields` + `$function`) — troca `.` e `$` em
   nomes de campo (recursivo, incluindo arrays) por `_`. Iceberg rejeita nomes
   de coluna com `.`, e essa falha **não cai na DLQ** — derruba o processor
   inteiro. Esse estágio existe só para blindar isso.
5. `$replaceRoot` — promove o documento sanitizado.
6. `$iceberg` — grava no bucket S3, catálogo Glue, `mode: "cdc"`,
   `idFieldName: "_id"`.

Documentos rejeitados por `$iceberg` (ex.: `Decimal128`, conflito de tipo)
vão para a dead-letter queue `iceberg_demo.dlq`, configurada na criação do
processor (`dlq: { connectionName, db, coll }`).

**Limitação conhecida:** a versão do ASP usada aqui não expõe `partitionBy`
no estágio `$iceberg` — a tabela não é particionada, Athena sempre varre o
dataset inteiro. Documentado no README.

### 3. Iceberg + Glue + Athena
Tabela Iceberg em S3, catalogada no Glue (`GLUE_DATABASE.ICEBERG_TABLE`,
default `mongodb_iceberg_demo.orders`). Cada commit do processor é um
snapshot Iceberg — histórico de append/overwrite/delete consultável via
`FOR VERSION AS OF` / `FOR TIMESTAMP AS OF` sem nenhuma configuração extra
(seção "time travel" em `queries.md`).

### 4. Backend FastAPI (`backend/`)
Nunca escreve no Iceberg — só lê (Athena) e opera no MongoDB (as ações de
demo). Arquivos:

- `main.py` — rotas HTTP.
- `mongo_side.py` — tudo que toca o cluster operacional (conexão, overview,
  as quatro operações de demo).
- `athena_side.py` — tudo que toca Athena/Glue, com retry curto em erros
  transientes e degradação explícita quando falta credencial AWS.
- `lag_side.py` — mede a distância entre o checkpoint do processor (via
  `mongosh --eval 'sp.<nome>.stats()'`, porque pymongo não fala com um
  workspace de ASP) e a janela do oplog do cluster fonte. Sinal antecipado
  antes do processor cair de vez com "resume of change stream was not
  possible".
- `settings.py` — configuração via `.env` na raiz do repo.

### 5. Frontend React (`frontend/`)
Ver `docs/briefing/ui-flows.md` para telas e componentes.

## Fluxo de dados ponta a ponta

1. Um dos scripts de demo (`scripts/insert_order.py` etc.) ou a UI
   (`POST /api/demo/{operacao}`) escreve/atualiza/apaga em
   `iceberg_demo.orders` no Atlas.
2. O change stream da coleção emite o evento.
3. O processor `ordersToIceberg` consome o evento, sanitiza nomes de campo,
   grava no Iceberg via `$iceberg` (commit = snapshot novo).
4. Glue reflete a coluna/tabela atualizada.
5. Athena responde `SELECT` sobre a tabela — usado tanto pelas telas da UI
   quanto pelos arquivos em `sql/`.
6. A UI mostra os dois lados (MongoDB e Iceberg) lado a lado e classifica o
   estado como convergido / propagando / divergente / tabela duplicada.

Latência medida contra ambiente real (README): inserts ~10s, updates ~20s,
deletes 30–60s.

## Decisões de arquitetura e por quê

- **CDC via Atlas Stream Processing em vez de Debezium/Kafka/Spark.** A tese
  da PoV é justamente eliminar esse pipeline. ASP fala nativamente com o
  change stream do Atlas e escreve Iceberg com um estágio (`$iceberg`) — sem
  infraestrutura própria para manter.
- **`idFieldName: "_id"` e `mode: "cdc"`** — necessário para que update/delete
  no Iceberg sejam upsert/remoção reais (não append puro), o que é a diferença
  central frente a um lake append-only tradicional.
- **Sanitização de nomes de campo como estágio explícito.** Descoberta em
  produção contra o ambiente real: um campo com `.` derruba o processor sem
  passar pela DLQ. Em vez de documentar como limitação, o pipeline se blinda.
- **`.env` central na raiz, nunca hardcoded.** Credenciais (URI do Mongo,
  bucket S3, região) saem do controle de versão; scripts e backend leem do
  mesmo arquivo.
- **Backend nunca escreve no Iceberg.** Mantém uma única fonte de verdade
  para a réplica (o processor) e evita duas escritas divergentes na mesma
  tabela.
- **Restart do processor exige `AUTO_REBUILD=1` explícito.** Reiniciar sem
  checkpoint faz o `initialSync` rodar de novo e duplicar a tabela inteira
  (insert, não upsert). `stream-processing/rebuild_table.py --auto-rebuild`
  automatiza o `DROP TABLE` via Athena antes do restart; sem a flag de
  ambiente o restart simplesmente recusa rodar.
- **Sem particionamento na tabela Iceberg.** Não é decisão de design — é
  limitação da versão do `$iceberg` do ASP usada aqui (sem `partitionBy`
  documentado). Fica registrado para não ser confundido com escolha.
- **Dois ambientes Python separados** (`.venv/` vs `backend/venv/`) — os
  scripts de demo não precisam de `boto3`/`fastapi`; separar evita que uma
  dependência pesada do backend vaze para o fluxo de seed/demo.

## Reset e bancos de teste

`scripts/reset_demo.py` é o comando único que devolve a demo ao ponto de
partida: garante `changeStreamPreAndPostImages`, remove os pedidos ao vivo e
qualquer documento fora do seed, regrava os 5.000 pedidos determinísticos e
esvazia a DLQ. O seed usa uma âncora de data fixa (`SEED_ANCHOR`, padrão
2026-08-24T18:59:04Z): antes ela era "agora", e como o `_id` carrega o mês
(`PED-AAAAMM-…`), rodar o seed em outro mês gravava 5.000 ids novos por cima
dos antigos. O Iceberg não é tocado pelo reset: as escritas propagam pelo
processor. Recriar a tabela do zero é o caminho destrutivo separado
(`rebuild_table.py --auto-rebuild` + `restart_processor.js`).

Escrita em banco que não termina em `_test` exige `ALLOW_DEMO_DB_WRITE=1`.
Testes e medições usam `iceberg_demo_test` (`DATABASE_NAME` no ambiente vence
o `.env`). `scripts/cdc_probe.py` mede, nesse banco, a perna escrita → evento
do change stream e a retomada por resume token.

## Onde continuar

- `implementation_plan.md` (raiz) — capa do projeto.
- `docs/DEMO_FLOW.md` — roteiro de apresentação.
- `docs/TROUBLESHOOTING.md` — nove falhas reais já encontradas, com sintoma e
  cura.
- `docs/DEV_NOTES.md` — notas de desenvolvimento.
