# CLAUDE.md

Orientações para o Claude Code neste repositório.

## O que é

PoV de portfólio: uma coleção do MongoDB Atlas replicada como tabela Apache
Iceberg no S3 via Atlas Stream Processing, consultada por Athena com catálogo
Glue. Insert, update, delete e schema evolution propagam sem ETL.

Comece por `implementation_plan.md` e pelos três briefings em `docs/prompts/`.
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

1. A coleção precisa de `changeStreamPreAndPostImages`, senão o processor morre
   no primeiro UPDATE. `preflight.py` corrige.
2. Reiniciar sem checkpoint **duplica a tabela** — `initialSync` insere, não faz
   upsert. Dropar a tabela antes.
3. Nome de campo com `.` derruba o processor e não vai para a DLQ.
4. `Decimal128` e conflito de tipo vão para a DLQ (`iceberg_demo.dlq`).
5. O backend nunca escreve no Iceberg. Quem alimenta a tabela é o processor.

## Interface

Antes de mexer no frontend, leia o `POV_UI_DESIGN_SYSTEM.md` na raiz do
workspace. `src/pov-signature.css` é cópia sincronizada entre os frontends e não
pode divergir. Validar em 1440, 768 e 360 px, sem erro de console e sem overflow
horizontal.

## AWS

Credencial de SSO expira em horas. `preflight.py` detecta e abre
`~/.aws/credentials` no macOS. Sem credencial, a UI continua servindo o lado
MongoDB e o painel do Iceberg explica o que falta.
