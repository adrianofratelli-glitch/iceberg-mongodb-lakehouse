# Notas de desenvolvimento

O que é preciso saber antes de mexer neste repositório.

## O que é

PoV de portfólio: uma coleção do MongoDB Atlas replicada como tabela Apache
Iceberg no S3 via Atlas Stream Processing, consultada por Athena com catálogo
Glue. Insert, update, delete e schema evolution propagam sem ETL.

Comece por `implementation_plan.md` e pelos três briefings em `docs/briefing/`.
`docs/TROUBLESHOOTING.md` lista as nove falhas já encontradas contra o ambiente
real — leia antes de debugar qualquer coisa.

## Comandos

```bash
./start.sh                                   # backend :8250 + frontend :5250
POV_DEV=1 ./start.sh                         # HMR + uvicorn --reload

./.venv/bin/python scripts/preflight.py      # rodar antes de toda demo
./.venv/bin/python scripts/seed_orders.py    # 5.000 pedidos reprodutíveis
./.venv/bin/python scripts/compare_aggregation.py

cd frontend && npm run build                 # build de produção
```

Ciclo da demo: `insert_order.py` → `update_order.py` → `delete_order.py` →
`add_schema_field.py`, e `reset_demo.py` para limpar.

Stream processor (mongosh conectado ao workspace de Stream Processing):

```
load("stream-processing/create_processor.js")
load("stream-processing/restart_processor.js")   # restart sem checkpoint
sp.ordersToIceberg.stats()
```

## Dois venvs

`.venv/` na raiz roda os scripts de demo; `backend/venv/` roda o FastAPI. São
separados de propósito: os scripts precisam apenas de pymongo, o backend também
de boto3 e fastapi.

## Invariantes que quebram a demo

1. A coleção precisa de `changeStreamPreAndPostImages`, senão o processor morre no primeiro UPDATE. `create_processor.js` habilita/aborta; `preflight.py` e `POST /api/corrigir/post-images` são o corretor manual.
2. Reiniciar sem checkpoint **duplica a tabela** (`initialSync` insere, não faz upsert). `restart_processor.js` recusa rodar sem `AUTO_REBUILD=1`; drope a tabela antes (`rebuild_table.py --auto-rebuild`).
3. Nome de campo com `.` ou `$` derruba o processor e **não** vai para a DLQ. O estágio de sanitização (`$function`) em `create_processor.js` renomeia antes do `$iceberg`; se `$function` não existir na versão do ASP, troque por `$project` explícito (ver nota no arquivo).
4. `Decimal128` e conflito de tipo vão para a DLQ `iceberg_demo.dlq`. Valores monetários ficam `double`.
5. O backend nunca escreve no Iceberg; quem alimenta a tabela é o processor.
6. Tabela Iceberg sem `partitionedBy` explícito: o processor foi criado antes de o campo existir. Hoje o `$iceberg` aceita `partitionedBy` (o primeiro transform é sobre o `idFieldName`; sem o campo a doc diz haver transform padrão no id, a confirmar). Mudar exige drop da tabela e restart sem checkpoint; ver `docs/adr/0004-particionamento.md`.
7. `/api/lag` (`backend/lag_side.py`) usa `mongosh --eval 'sp.<nome>.stats()'`, exige `STREAM_PROCESSING_URI` e leitura de `local.oplog.rs`; o parsing de `stats()` **não foi validado** contra workspace real — confira os nomes de campo antes de usar em demo.
8. IDs de rota nunca são "limpos" em silêncio: pedido/consulta em allowlist, snapshot inteiro positivo limitado; fora do contrato → 422 antes de tocar MongoDB, Athena ou filesystem.
9. Seed ancorado em `SEED_ANCHOR` fixo (padrão `2026-08-24T18:59:04Z`) porque o `_id` (`PED-AAAAMM-…`) carrega o mês. Mudar a âncora exige rodar `reset_demo.py` para remover os ids antigos.

## Interface

Antes de mexer no frontend, leia o `POV_UI_DESIGN_SYSTEM.md` na raiz do
workspace. `src/pov-signature.css` é cópia sincronizada entre os frontends e não
pode divergir. Validar em 1440, 768 e 360 px, sem erro de console e sem overflow
horizontal.

## AWS

Credencial de SSO expira em horas. `preflight.py` detecta e abre
`~/.aws/credentials` no macOS. Sem credencial, a UI continua servindo o lado
MongoDB e o painel do Iceberg explica o que falta.
