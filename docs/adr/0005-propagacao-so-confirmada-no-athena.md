# ADR 0005 — A API só afirma o commit no MongoDB

- Status: aceita (2026-11-12)

## Contexto
A resposta do INSERT dizia que o change stream "já levou o evento adiante",
sem nenhuma verificação; num banco sem processor (como `iceberg_demo_test`) a
frase era falsa. O `/preflight` respondia `ok: true` com a credencial AWS
expirada, sem dizer que metade da demo estava fora.

## Decisão
- `POST /api/demo/{op}` afirma só o que o backend verificou (o commit no
  MongoDB) e devolve `propagacao: "aguardando_confirmacao"`.
- A chegada no Iceberg só é confirmada lendo a linha de volta no Athena: a UI
  faz o polling e cronometra; `backend/lake_probe.py` mede p50/p95 em lote.
- `/preflight` devolve `modo` (`completo`, `somente_mongodb`, `com_falha`) e
  `resumo`; `ok` continua significando "o lado MongoDB está saudável".

## Consequências
- Clientes que liam só `ok` e `checks` continuam funcionando.
- Sem AWS a demo segue útil para o lado MongoDB e não afirma nada sobre o lake.
