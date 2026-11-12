# Decisões de arquitetura

| ADR | Decisão | Status |
|---|---|---|
| [0001](0001-asp-iceberg-em-vez-de-debezium.md) | Atlas Stream Processing `$iceberg` em vez de Debezium/Kafka/Spark | aceita |
| [0002](0002-dois-venvs.md) | Dois ambientes Python: scripts só com pymongo, backend com FastAPI + boto3 | aceita |
| [0003](0003-rtbf-fora-da-main.md) | Direito ao esquecimento no lake fica fora da `main` até validação na AWS | aceita |
| [0004](0004-particionamento.md) | Tabela sem `partitionedBy` explícito; troca é experimento registrado | aceita |
| [0005](0005-propagacao-so-confirmada-no-athena.md) | A API só afirma o commit no MongoDB; propagação é confirmada lendo o Athena | aceita |
