# ADR 0004 — Tabela sem `partitionedBy` explícito

- Status: aceita (2026-11-12)

## Contexto
O processor foi criado em 2026-08 sem particionamento porque o estágio
`$iceberg` não oferecia o campo. A doc atual oferece `partitionedBy` com 1 a 3
transforms (`identity`, `year`, `month`, `day`, `hour`, `truncate`, `bucket`),
o primeiro obrigatoriamente sobre o `idFieldName`, e aplica um transform padrão
no id quando o campo é omitido. As perguntas de negócio da demo varrem a base
inteira (`sql/06_pergunta_de_negocio.sql` agrupa por UF e mês,
`sql/07_top_produtos.sql` por produto), então particionar por id não reduz o
que o Athena lê; só um filtro por período se beneficiaria de partição temporal.

## Decisão
Não mudar o pipeline agora. Trocar o particionamento significa dropar a tabela
e reiniciar o processor sem checkpoint, e isso só pode ser feito com a AWS
disponível e fora de demo.

## Consequências
- A demo segue como está; os bytes escaneados por consulta aparecem na UI.
- Experimento proposto, quando houver AWS: `partitionedBy: { _id: { bucket: 8 },
  orderDate: "month" }`, rebuild com `rebuild_table.py --auto-rebuild` +
  `restart_processor.js`, e comparar bytes escaneados de uma consulta filtrada
  por mês antes e depois, além de contar arquivos pequenos por partição.
