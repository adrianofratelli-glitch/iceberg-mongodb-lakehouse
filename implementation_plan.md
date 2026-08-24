# Iceberg + MongoDB — plano de implementação

PoV de portfólio interno, sem cliente vinculado. Base: fork de
[mongodb-developer/Iceberg-MongoDB-Demo](https://github.com/mongodb-developer/Iceberg-MongoDB-Demo),
endurecido contra um cluster Atlas real e um bucket S3 real em `sa-east-1`.

**A tese:** uma coleção operacional do MongoDB vira tabela Apache Iceberg
consultável por Athena, com insert, update, delete e schema evolution
propagando sozinhos — sem ETL, sem Spark, sem Debezium, sem Kafka.

## Índice do briefing

| Arquivo | Conteúdo |
|---|---|
| [docs/prompts/01-arquitetura.md](docs/prompts/01-arquitetura.md) | arquitetura, invariantes, ordem de montagem, como rodar |
| [docs/prompts/02-mongodb.md](docs/prompts/02-mongodb.md) | coleções, pre/post images, DLQ, pipeline do processor |
| [docs/prompts/03-interface-fluxos.md](docs/prompts/03-interface-fluxos.md) | roteiro da demo, queries Athena, o que dizer e o que não dizer |
| [docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md) | as nove falhas medidas, com sintoma e cura |

## Estado

Validado ponta a ponta em 2026-08-24: insert visível no Athena em ~10s, update
em ~20s, delete em <30s, coluna nova em 9s. Base de 5.000 pedidos em 18 meses
(R$ 7,85 mi), ingerida pelo processor em menos de um minuto, DLQ vazia.

## Portas

| Serviço | Porta |
|---|---|
| Backend FastAPI | 8250 |
| Frontend React/Vite | 5250 |

Registradas no `PORTS.md` do workspace e no `pov-portfolio/povs.json`. Sobe com
`./start.sh` ou pelo launcher (`povs activate iceberg`).
