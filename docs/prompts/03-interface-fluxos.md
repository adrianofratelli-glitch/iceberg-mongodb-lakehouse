# 03 — Interface e fluxos

A PoV tem interface própria em `frontend/` (React + Vite, porta 5250), servida
pelo backend FastAPI na 8250. Ela existe para o que um terminal não mostra bem:
as duas metades do circuito lado a lado, convergindo, e o cronômetro da
propagação rodando ao vivo.

O console do Athena continua no roteiro. A UI prepara o momento; abrir o Athena
e rodar a mesma query é o que prova formato aberto — se o dado só existisse na
nossa tela, não teríamos provado nada.

## As quatro seções da interface

| Seção | O que mostra |
|---|---|
| As duas metades | contagem do MongoDB × contagem do Iceberg, com selo de convergência: `convergido`, `propagando` (CDC a caminho) ou `tabela duplicada` (defeito real) |
| Ciclo CDC ao vivo | os quatro botões, o documento no Mongo e a linha no Iceberg, cronometrados |
| Time travel | snapshots clicáveis; clicar mostra o pedido naquele instante |
| Consultas analíticas | roda os arquivos de `sql/` no Athena e mostra tempo e bytes escaneados |

A UI degrada de propósito: sem credencial AWS, o lado MongoDB continua
funcionando e o painel do Iceberg diz o que fazer, em vez de girar um spinner.

## Antes de apresentar

```bash
./start.sh                       # sobe backend 8250 + frontend 5250
./.venv/bin/python scripts/preflight.py
```

Ou pelo launcher do portfólio: `povs activate iceberg`.

Tem que sair `preflight PASSED`, DLQ vazia. Depois, no Athena:

```sql
SELECT count(*) AS total, count(DISTINCT _id) AS ids FROM orders
```

Os dois números iguais e batendo com `db.orders.countDocuments({})`.
Se `total > ids`, a tabela foi duplicada por um restart: dropar e reconstruir
antes da demo.

O Athena precisa de result location configurado
(`s3://<bucket>/athena-results/`), senão o botão Run fica desabilitado.

## Roteiro (~8 min)

**Abertura (1 min).** Duas telas: MongoDB Compass em `iceberg_demo.orders`,
Athena em `mongodb_iceberg_demo.orders`. Mesma contagem nos dois lados —
5.000 pedidos, 18 meses, R$ 7,85 mi. "Mesmo dado, dois mundos. Nenhum ETL
entre eles."

**1. INSERT (2 min).**

```bash
./.venv/bin/python scripts/insert_order.py
```
```sql
SELECT * FROM orders WHERE _id = 'PED-AOVIVO-001'
```

Aparece em ~10s. Ponto: o pedido entrou pelo caminho operacional normal.

**2. UPDATE (2 min).**

```bash
./.venv/bin/python scripts/update_order.py
```

A mesma query mostra `EM_TRANSPORTE` e `2159.1`. **Este é o momento da demo.** Data
lake tradicional é append-only: mudar uma linha exige reescrever partição.
Aqui o update propagou sozinho.

**3. DELETE (1 min).**

```bash
./.venv/bin/python scripts/delete_order.py
```

A linha some do Athena. Se o cliente for de setor regulado, conecte com LGPD:
direito ao esquecimento que atravessa o lake sem job de compactação.

**4. Schema evolution (2 min).**

```bash
./.venv/bin/python scripts/add_schema_field.py
```
```sql
SELECT _id, status, fraudscore FROM orders WHERE _id = 'PED-AOVIVO-002'
```

Campo novo no MongoDB vira coluna nova no Iceberg em ~9s. Linhas antigas ficam
`NULL`. Sem ALTER TABLE, sem migração.

**5. A pergunta de negócio (2 min).** O fecho, e o argumento de custo.

```sql
-- sql/06_pergunta_de_negocio.sql
```

Receita por UF e mês, ticket médio, taxa de cancelamento e participação do app,
varrendo 18 meses. Depois `sql/07_top_produtos.sql`, com window function sobre
a base inteira.

O que dizer: "esse relatório não roda no cluster transacional. Se rodasse,
concorreria com o checkout. Aqui ele varre 5.000 pedidos no S3, e o M20 nem
sabe que a consulta existiu." É onde o cliente conecta lakehouse com custo:
não se escala banco operacional para servir BI.

**6. Time travel (2 min).** O trunfo de auditoria, e é de graça.

```sql
-- sql/08_time_travel.sql
SELECT snapshot_id, committed_at, operation
FROM "mongodb_iceberg_demo"."orders$snapshots"
ORDER BY committed_at DESC LIMIT 20;
```

Cada commit do processor virou um snapshot. Escolha um anterior ao UPDATE do
passo 2 e consulte a tabela como ela era naquele instante:

```sql
SELECT _id, status, amount FROM mongodb_iceberg_demo.orders
FOR TIMESTAMP AS OF TIMESTAMP '<antes do update>'
WHERE _id = 'PED-AOVIVO-001';
```

Medido: o mesmo pedido, já apagado do MongoDB, recuperado em três estados —
`PROCESSANDO`/2399.00 no snapshot do insert, `EM_TRANSPORTE`/2159.10 no do
update, e zero linhas no presente. Cada query levou menos de 1s.

O ciclo da demo aparece no histórico como `append`, `overwrite`, `delete` —
três linhas que contam a história inteira.

O que dizer: "ninguém configurou versionamento. Isso vem do formato. Auditoria
pergunta qual era o valor às 14h e a resposta é uma query, não um restore de
backup."

**7. O custo do analítico no operacional (1 min, opcional).**

```bash
./.venv/bin/python scripts/compare_aggregation.py
```

Roda a mesma agregação do `sql/06` contra o cluster e cronometra. Nesta escala
o MongoDB é **mais rápido** que o Athena (~270ms contra ~2,6s) — e o script diz
isso explicitamente. O ponto não é velocidade: é que essa varredura não tem
nada a ver com servir pedidos, e no cluster ela disputa cache, CPU e IO com o
checkout. Some 18 meses de histórico e alguns milhões de pedidos, e o custo de
manter tudo quente no cluster é o argumento.

Se o cliente for cético, esse é o slide que ganha: você mostrou o número que
contraria seu próprio produto e mesmo assim o argumento se sustenta.

## Números medidos (2026-08-24)

| Operação | Até visível no Athena |
|---|---|
| INSERT | ~10s |
| UPDATE | ~20s |
| DELETE | 30-60s |
| coluna nova | ~10s |

Delete é o mais lento dos quatro — se na demo a linha ainda aparecer, espere e
rode a query de novo em vez de anunciar falha.

Custo das queries do roteiro: `sql/06` varre ~450 KB em 2,6s; `sql/07`, 293 KB
em 2,2s. A tabela inteira (5.001 pedidos) escaneia 115 KB.

## O que dizer e o que não dizer

**Diga "near real-time", segundos a minutos.** Não diga "tempo real": são
commits de Iceberg, e prometer latência de streaming é criar objeção futura.

**Diga que o MongoDB é a fonte da verdade e o Iceberg é derivado.** É o que
sustenta a resposta sobre recuperação: dropar e reconstruir.

**Não fuja das limitações se perguntarem.** `Decimal128` vai para a DLQ,
conflito de tipo vai para a DLQ, e nome de campo com ponto derruba o pipeline.
A resposta honesta é validação na origem. Cliente técnico vai testar isso
depois; melhor ouvir de você primeiro.

## Depois da demo

```bash
./.venv/bin/python scripts/reset_demo.py
```

Remove os `PED-AOVIVO-*`. Não recria a tabela: o schema mantém `fraudscore`, o
que é fiel ao comportamento do Iceberg.

## Ideias para fortalecer

1. **Volume maior.** 5.000 pedidos sustentam a agregação, mas o custo do
   analítico no operacional só fica evidente com centenas de milhares — é onde
   o `compare_aggregation.py` inverteria o resultado a favor do Athena.
2. **Compaction.** O modo CDC gera muitos arquivos pequenos. Mostrar
   `OPTIMIZE ... REWRITE DATA` no Athena e a queda no tempo de query é um
   argumento de operação madura.
3. **Um segundo consumidor.** Apontar Spark ou Trino na mesma tabela prova o
   formato aberto na prática, em vez de afirmá-lo.
