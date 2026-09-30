-- Valida o DELETE: zero linhas
--
SELECT *
FROM mongodb_iceberg_demo.orders
WHERE _id = 'PED-AOVIVO-001';

-- Expected after scripts/delete_order.py: 0 rows
