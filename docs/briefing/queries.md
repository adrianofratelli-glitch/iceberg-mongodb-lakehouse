# Queries, pipelines e índices

Levantamento direto do código (grep por `.aggregate(`, `.find(`,
`create_index`/`createIndex`, config de change stream). Nada inventado —
cada item abaixo aponta para o arquivo:linha real.

## Índices MongoDB

**Não há nenhum `create_index`/`createIndex` neste repositório.** A única
proteção de acesso por chave é o índice único nativo do MongoDB em `_id`
(criado automaticamente em toda coleção, não é código deste projeto).

Por quê não há índices extras:
- A coleção `orders` (5.000 documentos após o seed) cabe inteira na RAM/cache
  do WiredTiger nesta escala — não há query lenta o bastante para justificar
  um índice novo na demo.
- Todo acesso pontual usado na demo é por `_id` (`PED-AOVIVO-001`,
  `PED-AOVIVO-002`), já coberto pelo índice único.
- `scripts/compare_aggregation.py` reporta explicitamente que a agregação de
  negócio roda como `COLLSCAN` — isso é proposital, é o contraponto da
  demo: a mesma pergunta roda sem tocar o cluster quando feita no Iceberg via
  Athena (ver `sql/06_pergunta_de_negocio.sql`).

Se a PoV crescer para um volume realista, o candidato óbvio a índice seria
composto em `{status: 1, orderDate: -1}` ou `{region: 1, orderDate: -1}`
(pipelines de `$group` por região/mês/status a seguir se beneficiariam), mas
isso não existe no código hoje — só registro para conversa com o cliente.

## Change stream / CDC (não é `.find`/`.aggregate`, mas é a query real do pipeline)

**`stream-processing/create_processor.js:32-49`** — estágio `$source` do
processor `ordersToIceberg`:
```js
{
  $source: {
    connectionName: SOURCE_CONNECTION,
    db: SOURCE_DATABASE,
    coll: SOURCE_COLLECTION,
    initialSync: { enable: true },
    config: { fullDocument: "required" }
  }
}
```
O que faz: abre um change stream sobre `iceberg_demo.orders`, com carga
inicial completa (`initialSync`) seguida de eventos incrementais, exigindo
documento completo em cada evento (`fullDocument: "required"` — por isso
depende de `changeStreamPreAndPostImages` habilitado na coleção).

Por que existe: é o próprio mecanismo de CDC da PoV — sem ele não há
replicação para o Iceberg.

## Aggregation pipelines — MongoDB

### `backend/mongo_side.py:64-68` — distribuição de pedidos por status
```python
coll.aggregate(
    [{"$group": {"_id": "$status", "n": {"$sum": 1}}}, {"$sort": {"n": -1}}]
)
```
O que faz: conta pedidos agrupados por `status`, ordenado do mais frequente
ao menos frequente.
Onde é usado: `GET /api/visao-geral` → card "MongoDB Atlas" da UI (top 3
status).
Por que existe: dar contexto de negócio ao lado operacional na tela
principal, sem precisar de uma segunda ida ao banco por status.

### `backend/mongo_side.py` (`overview`) — totais de receita e janela de datas
```python
coll.aggregate(
    [
        {
            "$group": {
                "_id": None,
                "receita": {
                    "$sum": {
                        "$convert": {
                            "input": "$amount", "to": "double",
                            "onError": 0, "onNull": 0,
                        }
                    }
                },
                "primeiro": {"$min": "$orderDate"},
                "ultimo": {"$max": "$orderDate"},
            }
        }
    ]
)
```
O que faz: soma `amount` de toda a coleção e pega a data do primeiro e do
último pedido. O `$convert` existe por schema drift: um `amount` gravado como
string ou `Decimal128` (que o `$iceberg` manda para a DLQ) derrubava a visão
geral com `TypeError`; agora é convertido, e o que não converte conta como 0.
Onde é usado: mesma rota `GET /api/visao-geral`.
Por que existe: mostrar receita total do lado MongoDB ao lado da receita
equivalente calculada via Athena — parte do argumento "os dois lados
convergem".

### `scripts/compare_aggregation.py:17-35` — a "pergunta de negócio" rodada no cluster operacional
```python
PIPELINE = [
    {
        "$group": {
            "_id": {
                "region": "$region",
                "mes": {"$dateToString": {"format": "%Y-%m", "date": "$orderDate"}},
            },
            "pedidos": {"$sum": 1},
            "receita": {"$sum": "$amount"},
            "ticket_medio": {"$avg": "$amount"},
            "cancelados": {"$sum": {"$cond": [{"$eq": ["$status", "CANCELADO"]}, 1, 0]}},
            "via_app": {"$sum": {"$cond": [{"$eq": ["$channel", "APP"]}, 1, 0]}},
        }
    },
    {"$sort": {"receita": -1}},
    {"$limit": 25},
]
```
O que faz: receita, pedidos, ticket médio, % cancelamento e % via app,
agrupados por região e mês — as top 25 combinações por receita.
Onde é usado: `scripts/compare_aggregation.py`, rodado manualmente pelo
engenheiro para comparar tempo/`COLLSCAN` contra a mesma pergunta em
`sql/06_pergunta_de_negocio.sql` (Athena).
Por que existe: é o argumento central da PoV — a mesma pergunta analítica
custa CPU/IO do cluster transacional no MongoDB (`totalDocsExamined` alto,
sem índice que ajude) e custa zero no Iceberg via Athena. O script chama
`explain` em seguida (linha 47-53) para capturar `executionStats` e imprimir
quantos documentos foram examinados.

## Escritas da demo — MongoDB

### `backend/mongo_side.py` (`demo_insert`, `demo_schema_field`)
```python
collection().replace_one({"_id": doc["_id"]}, doc, upsert=True)
```
`replaceOne` com `upsert` no lugar do antigo `deleteOne` + `insertOne`: dois
cliques seguidos (ou duas abas) corriam para `DuplicateKeyError`. O evento a
jusante continua certo para o modo `cdc` do `$iceberg`: `insert` quando o
pedido não existe, `replace` (documento inteiro) quando já existe.

### `scripts/reset_demo.py` — reset completo e idempotente
```python
coll.delete_many({"_id": {"$in": LIVE_IDS}})            # pedidos ao vivo
coll.delete_many({"_id": {"$nin": sorted(seed_ids())}})  # qualquer sobra
ReplaceOne({"_id": doc["_id"]}, doc, upsert=True)        # 5.000 do seed, lotes de 1.000
db.dlq.delete_many({})
```
Recusa qualquer banco que não termine em `_test` sem `ALLOW_DEMO_DB_WRITE=1`.
Documentos do seed já idênticos não geram evento de change stream, então um
reset numa demo limpa não mexe no Iceberg.

## `.find()` — MongoDB

### `backend/mongo_side.py:97` — `find_order`
```python
collection().find_one({"_id": order_id})
```
Busca pontual por `_id`. Usado por `GET /api/pedido/{order_id}` (comparação
lado a lado MongoDB × Iceberg de um pedido específico) e internamente por
`demo_update`. Coberto pelo índice único de `_id` — não precisa de índice
adicional.

### `scripts/preflight.py:120` — inspeção da dead-letter queue
```python
db[DLQ_COLLECTION].find().limit(3)
```
Lista até 3 documentos rejeitados pelo processor (`iceberg_demo.dlq`) para
mostrar motivo (`errInfo.reason`) e `_id` do documento problemático antes de
cada demo.

## Consultas analíticas — Athena / Iceberg (`sql/`)

Executadas via `backend/athena_side.py:run_query` (com retry curto em erro
transiente) e servidas por `POST /api/consultas/{consulta_id}` — o backend
lê o arquivo, remove comentários, roda o primeiro statement.

| Arquivo | O que faz | Por que existe |
|---|---|---|
| `sql/01_orders_by_region.sql` | Receita e volume de pedidos por UF (`GROUP BY region`) | Consulta analítica simples de abertura, mostra agregação básica sobre o lake |
| `sql/02_find_live_order.sql` | `SELECT *` do pedido `PED-AOVIVO-001` | Espelha `find_order` do lado Mongo para comparação lado a lado na demo ao vivo |
| `sql/03_validate_update.sql` | `status`/`amount` do pedido ao vivo, com o valor esperado documentado em comentário | Valida visualmente que o UPDATE propagou (`EM_TRANSPORTE`, `2159.10`) |
| `sql/04_validate_delete.sql` | Mesma busca, espera 0 linhas | Valida que o DELETE propagou (linha não existe mais) |
| `sql/05_validate_schema.sql` | Busca o pedido `PED-AOVIVO-002`, que tem o campo novo `fraudScore` | Prova schema evolution: campo novo vira coluna sem migração |
| `sql/06_pergunta_de_negocio.sql` | Receita/pedidos/ticket médio/% cancelado/% app, por região e mês, 18 meses, top 25 por receita | O contraponto direto de `scripts/compare_aggregation.py`: mesma pergunta, custo zero no cluster operacional |
| `sql/07_top_produtos.sql` | Top produtos por receita com `% do total` via `SUM(...) OVER ()` | Mostra window function/agregação pesada sobre a base inteira |
| `sql/08_time_travel.sql` | (a) histórico de snapshots via `"orders$snapshots"`; (b)/(c) `FOR VERSION AS OF <snapshot_id>`; (d) `FOR TIMESTAMP AS OF <timestamp>`; (e) estado atual (0 linhas, já deletado) | Mostra o time travel "de graça" do formato Iceberg — cada commit do processor é um snapshot, sem nada configurado à parte |

### Consultas auxiliares no backend (`athena_side.py`)

- **`counts()` (linha 157-168)** — `SELECT count(*) AS total, count(DISTINCT
  _id) AS ids FROM <tabela>`. Usado por `GET /api/visao-geral` para o card
  Iceberg e para a lógica de "convergiu / propagando / tabela duplicada" (se
  `total > ids`, a tabela foi duplicada por um restart sem checkpoint).
- **`find_order(order_id)` (linha 171-176)** — `SELECT _id, status, amount,
  channel, paymentmethod FROM <tabela> WHERE _id = '<id>'`. Usado por `GET
  /api/pedido/{order_id}`. Interpolação de string sanitizada por `_safe()`
  (linha 198-202, regex `[A-Za-z0-9][A-Za-z0-9_-]{0,127}` — Athena não tem
  bind parameters).
- **`snapshots(limit=12)` (linha 179-186)** — `SELECT snapshot_id,
  committed_at, operation, summary['added-records'], summary['deleted-records']
  FROM "<db>"."<tabela>$snapshots" ORDER BY committed_at DESC LIMIT <n>`.
  Alimenta a tela de time travel na UI.
- **`order_at_snapshot(order_id, snapshot_id)` (linha 189-195)** — `SELECT
  _id, status, amount FROM <tabela> FOR VERSION AS OF <snapshot_id> WHERE _id
  = '<id>'`. Usado por `GET
  /api/snapshots/{snapshot_id}/pedido/{order_id}` para reconstruir o pedido
  como ele era num snapshot específico, mesmo já deletado no presente.
- **`drop_table()` (linha 131-141)** — `DROP TABLE IF EXISTS <db>.<tabela>`.
  Usado por `stream-processing/rebuild_table.py --auto-rebuild` antes de um
  restart sem checkpoint, para evitar duplicar a tabela (ver
  `architecture.md`).
- **`table_columns()` (linha 144-154)** — `glue.get_table(...)`, não é SQL:
  lê o esquema de colunas direto do catálogo Glue. Alimenta `GET /api/schema`
  (contagem de colunas mostrada na UI, e a evidência visual de schema
  evolution).

## Índices/consultas do lado Athena/Glue

Não há índice a configurar em Athena/Iceberg (é engine de query sobre
arquivos Parquet, não um banco com índice tradicional). O equivalente
funcional discutido no time travel (`08_time_travel.sql`) é o **snapshot**:
cada commit do processor grava um snapshot Iceberg automaticamente — não é
configuração da PoV, é o formato de tabela em si.
