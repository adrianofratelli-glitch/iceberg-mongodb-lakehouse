# ADR 0001 — Atlas Stream Processing `$iceberg` em vez de Debezium/Kafka/Spark

- Status: aceita (2026-08, registrada em 2026-11-12)

## Contexto
A tese da PoV é que uma coleção operacional vira tabela Iceberg consultável sem
um pipeline próprio. O caminho tradicional é change stream → Debezium ou Kafka
Connector → Kafka → job Flink/Spark que escreve Iceberg, com cada peça operada
por alguém.

## Decisão
Usar o estágio `$iceberg` do Atlas Stream Processing (GA desde 2026-06-30) com
`$source` no change stream (`initialSync` + `fullDocument: "required"`),
`mode: "cdc"`, catálogo Glue e leitura pelo Athena
(`stream-processing/create_processor.js`).

## Consequências
- Não há Kafka nem job de escrita para operar; insert, update e delete viram
  operações na tabela pelo `_id`.
- Requisitos que passam a valer: post-images na coleção, workspace SP10+,
  sanitização de nomes com `.`/`$` antes do `$iceberg`, DLQ para conflitos de
  tipo (invariantes em `docs/DEV_NOTES.md`).
- Restart sem checkpoint duplica a tabela (`initialSync` insere): exige drop
  antes (`stream-processing/rebuild_table.py`).
- Latência não é garantida pela doc; é medida (`backend/lake_probe.py`).
- Alternativa descartada para a demo, não para o mundo: Debezium/Kafka continua
  válido quando já existe Kafka ou quando o destino não é Iceberg.
