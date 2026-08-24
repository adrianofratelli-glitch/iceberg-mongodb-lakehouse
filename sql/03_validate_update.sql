-- Valida o UPDATE: status e valor novos
--
SELECT
    _id,
    status,
    amount
FROM mongodb_iceberg_demo.orders
WHERE _id = 'PED-AOVIVO-001';

-- Expected after scripts/update_order.py:
-- status = EM_TRANSPORTE
-- amount = 2159.10
