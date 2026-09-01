# 02 — MongoDB

## Coleções

| Coleção | Papel |
|---|---|
| `iceberg_demo.orders` | fonte da verdade; 5.000 pedidos de seed + os `PED-AOVIVO-*` da demo |
| `iceberg_demo.dlq` | dead-letter queue do processor; vazia quando tudo está são |

Documento de `orders`:

```json
{
  "_id": "PED-202608-004217",
  "customerId": "CLI-00042",
  "region": "SP",
  "product": "Smart TV 50\"",
  "quantity": 1,
  "amount": 2399.00,
  "status": "ENTREGUE",
  "channel": "APP",
  "paymentMethod": "PIX",
  "orderDate": ISODate("...")
}
```

`scripts/seed_orders.py` gera 5.000 pedidos distribuídos em 18 meses, com
semente fixa (`RANDOM_SEED = 42`) para que a base seja reprodutível. UF,
status e forma de pagamento são ponderados para parecer varejo real: SP com
~32% do volume, ~62% dos pedidos entregues, PIX como método dominante.

Valores em BRL armazenados como **double**. `Decimal128` seria o tipo natural
para dinheiro, mas o `$iceberg` o rejeita e manda para a DLQ.

`_id` é string com significado de negócio, não ObjectId — é a chave que o
`$iceberg` usa como `idFieldName` para aplicar update e delete.

## Pré-requisito não óbvio

```js
db.runCommand({ collMod: "orders", changeStreamPreAndPostImages: { enabled: true } })
```

O `$source` usa `fullDocument: "required"`, que exige post-image em todo
evento de update. Sem isso o processor entra em FAILED no primeiro UPDATE —
e insert e delete continuam funcionando, então a demo parece saudável até o
passo 2 do roteiro. `scripts/preflight.py` verifica e corrige.

Post-image não é retroativo: eventos anteriores ao `collMod` nunca terão
imagem. Depois de habilitar, reinicie sem checkpoint.

## O pipeline

```js
[
  { $source: { connectionName: "atlas-orders", db: "iceberg_demo", coll: "orders",
               initialSync: { enable: true }, config: { fullDocument: "required" } } },
  { $match: { operationType: { $in: ["insert","update","delete","replace"] } } },
  { $replaceRoot: { newRoot: { $cond: {
      if: { $eq: [ { $meta: "stream.source.operationType" }, "delete" ] },
      then: "$documentKey",
      else: "$fullDocument" } } } },
  { $iceberg: { connectionName: "s3-iceberg", bucket: "...", databaseName: "...",
                tableName: "orders", path: "iceberg-warehouse", region: "sa-east-1",
                mode: "cdc", idFieldName: "_id", catalog: { type: "glue" } } }
]
```

Duas sutilezas:

- **`$replaceRoot` condicional.** Delete não tem `fullDocument`; só
  `documentKey`. Sem o `$cond`, todo delete iria para a DLQ.
- **`path` sem barra final.** `"iceberg-warehouse/"` é rejeitado na criação.

## DLQ

```js
sp.createStreamProcessor(name, pipeline, {
  dlq: { connectionName: "atlas-orders", db: "iceberg_demo", coll: "dlq" }
});
```

Cada rejeitado grava o documento original, o operador que recusou e o motivo:

```
errInfo: { reason: 'Unexpected BSON type of string for iceberg column name amount of type double' }
```

## Tipos: o que passa e o que não passa

Medido contra o cluster real:

| Entrada | Resultado |
|---|---|
| documento aninhado, array | vira struct / list |
| ObjectId, Binary, null | ok |
| documento de 200 KB | ok |
| `Decimal128` | **DLQ** |
| tipo conflitante (string em coluna double) | **DLQ** |
| nome de campo com `.` | **processor FAILED** |

`Decimal128` na DLQ merece atenção: é o tipo natural para valor monetário em
produção. Numa implantação real, ou o campo vira double na origem, ou entra um
`$addFields` de conversão antes do `$iceberg`.

As rotas de leitura não interpolam identificadores arbitrários. `order_id` e
`query_id` aceitam somente `[A-Za-z0-9_-]` com limite de 128 caracteres; snapshots
são inteiros positivos de até 64 bits. A validação acontece no FastAPI e
`athena_side._safe()` repete a guarda antes de montar SQL. Entrada inválida é
rejeitada, nunca reescrita para outro identificador.

## Verificação de consistência

```js
db.orders.countDocuments({})     // MongoDB
```
```sql
SELECT count(*) AS total, count(DISTINCT _id) AS ids FROM orders   -- Athena
```

Os três números têm que bater. `total > ids` significa tabela duplicada por
restart — ver TROUBLESHOOTING.
