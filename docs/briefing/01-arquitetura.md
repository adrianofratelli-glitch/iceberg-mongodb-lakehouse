# 01 — Arquitetura

## O circuito

```
frontend React/Vite :5250  ──►  backend FastAPI :8250
                                  │            │
                     escreve ─────┘            └───── lê (boto3)
                        ▼                             ▼
MongoDB Atlas (M20, sa-east-1)                   Athena + Glue
  └─ iceberg_demo.orders          fonte da verdade
       │ change stream (insert/update/delete/replace)
       ▼
Atlas Stream Processing (SP10, AWS/SAOPAULO_BRA)
  └─ processor ordersToIceberg
       ├─ $source    connection atlas-orders, initialSync + fullDocument required
       ├─ $match     operationType in [insert, update, delete, replace]
       ├─ $replaceRoot   fullDocument, ou documentKey quando é delete
       └─ $iceberg   connection s3-iceberg, mode cdc, idFieldName _id, catálogo Glue
       └─ DLQ        iceberg_demo.dlq
       ▼
S3 <bucket>/iceberg-warehouse/  +  Glue Data Catalog
       ▼
Athena (workgroup primary, sa-east-1)
```

## Invariantes

1. **O MongoDB é a fonte da verdade.** O Iceberg é derivado e descartável:
   dropar a tabela e reiniciar o processor reconstrói tudo.
2. **A coleção precisa de `changeStreamPreAndPostImages`.** Sem isso o
   processor morre no primeiro UPDATE. `scripts/preflight.py` garante.
3. **Reiniciar sem checkpoint duplica a tabela.** `initialSync` insere, não faz
   upsert. Dropar a tabela antes de reiniciar sem checkpoint.
4. **Nome de campo com ponto derruba o pipeline.** Identificador de coluna
   Iceberg não aceita `.`, e a DLQ não captura esse caso.
5. **A demo é near real-time, não tempo real.** Medido: 10-30s.

## Ordem de montagem

1. AWS: bucket S3, Glue database (`setup/aws/bootstrap.sh` faz os dois)
2. AWS: role IAM + trust policy para o Atlas, e a permission policy —
   **manual**, o bootstrap não cria (ver TROUBLESHOOTING)
3. Atlas: Unified AWS Access apontando para a role
4. Atlas: workspace de Stream Processing + connections `atlas-orders` e
   `s3-iceberg`
5. `.env` a partir de `.env.example`
6. `python scripts/seed_orders.py`
7. `python scripts/preflight.py` — habilita pre/post images
8. mongosh no workspace: `load("stream-processing/create_processor.js")`

## Como rodar

```bash
python3 -m venv .venv
./.venv/bin/pip install -r requirements.txt
cp .env.example .env          # preencher
./.venv/bin/python scripts/preflight.py
./.venv/bin/python scripts/seed_orders.py
```

Estado do processor:

```bash
mongosh "<workspace-uri>" --tls --authenticationDatabase admin \
  --username <user> --eval 'sp.ordersToIceberg.stats()'
```

## Scripts

| Script | Papel |
|---|---|
| `scripts/preflight.py` | rodar antes de toda demo; valida e corrige o lado MongoDB |
| `scripts/seed_orders.py` | 5.000 pedidos reprodutíveis em 18 meses |
| `scripts/insert_order.py` / `update_order.py` / `delete_order.py` | os três passos do CDC ao vivo |
| `scripts/add_schema_field.py` | campo novo, para schema evolution |
| `scripts/compare_aggregation.py` | mesma agregação do `sql/06` no cluster, cronometrada |
| `scripts/reset_demo.py` | remove os `PED-AOVIVO-*` |
| `scripts/live_demo.py` | roteiro guiado, pausa entre passos |

| SQL | Papel |
|---|---|
| `sql/01`-`05` | validação de cada passo do CDC |
| `sql/06_pergunta_de_negocio.sql` | receita por UF/mês, ticket, cancelamento, canal |
| `sql/07_top_produtos.sql` | top produtos com window function |
| `sql/08_time_travel.sql` | snapshots do Iceberg e consulta a instante passado |

## Decisões

**Workspace compartilhado com outra PoV.** O `ordersToIceberg` roda no mesmo
SP10 de uma demo de PIX. Decisão consciente de custo: um SP10 dedicado para
12 documentos não se justifica.

**DLQ em coleção do próprio Atlas.** Rejeitados vão para `iceberg_demo.dlq` em
vez de sumirem. Sem isso, conflito de tipo é perda silenciosa.

**Interface própria, mas o Athena continua sendo prova.** A UI em `frontend/`
mostra as duas metades convergindo, dispara o ciclo CDC e cronometra a
propagação — coisas que um terminal ao lado do console não mostra bem. Ela não
substitui o Athena no roteiro: abrir o console e rodar a mesma query lá é o que
prova formato aberto, e a UI serve justamente para preparar esse momento.

**O backend nunca escreve no Iceberg.** Ele lê via Athena e Glue, e escreve
apenas no MongoDB. Quem alimenta a tabela é o Stream Processing — se o backend
pudesse escrever nos dois lados, a demo não provaria nada.
