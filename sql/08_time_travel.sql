-- Time travel: a tabela como ela era antes da mudanca.
--
-- Iceberg guarda um snapshot por commit. Nada disso foi configurado -- vem de
-- graca com o formato. Serve para auditoria ("qual era o valor deste pedido
-- as 14h?") e para recuperar erro sem restore de backup.

-- 1. Historico de snapshots. Rode este primeiro e escolha um snapshot_id.
SELECT
    snapshot_id,
    committed_at,
    operation,
    summary['added-records']   AS adicionados,
    summary['deleted-records'] AS removidos
FROM "mongodb_iceberg_demo"."orders$snapshots"
ORDER BY committed_at DESC
LIMIT 20;

-- O ciclo da demo aparece como tres operacoes seguidas:
--   append     -> o INSERT   (scripts/insert_order.py)
--   overwrite  -> o UPDATE   (scripts/update_order.py)
--   delete     -> o DELETE   (scripts/delete_order.py)

-- 2. O pedido no snapshot do INSERT, antes do update.
--    Substitua pelo snapshot_id de operation = 'append'.
SELECT _id, status, amount
FROM mongodb_iceberg_demo.orders
FOR VERSION AS OF 1685044852325531853
WHERE _id = 'PED-AOVIVO-001';
-- Retorna: PROCESSANDO / 2399.00

-- 3. O mesmo pedido no snapshot do UPDATE.
--    Substitua pelo snapshot_id de operation = 'overwrite'.
SELECT _id, status, amount
FROM mongodb_iceberg_demo.orders
FOR VERSION AS OF 9188744916259474793
WHERE _id = 'PED-AOVIVO-001';
-- Retorna: EM_TRANSPORTE / 2159.10

-- 4. Por instante, sem precisar do snapshot_id.
SELECT _id, status, amount
FROM mongodb_iceberg_demo.orders
FOR TIMESTAMP AS OF TIMESTAMP '2026-08-24 19:09:30 UTC'
WHERE _id = 'PED-AOVIVO-001';

-- 5. E no presente o pedido nao existe mais -- foi deletado no MongoDB
--    e o delete propagou.
SELECT _id, status, amount
FROM mongodb_iceberg_demo.orders
WHERE _id = 'PED-AOVIVO-001';
-- Retorna: 0 linhas
