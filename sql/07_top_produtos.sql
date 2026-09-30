-- Top produtos por receita, com participacao no total.
-- Serve para mostrar agregacao pesada sobre a base inteira.

SELECT
    product,
    COUNT(*)                                    AS pedidos,
    SUM(quantity)                               AS unidades,
    ROUND(SUM(amount), 2)                       AS receita,
    ROUND(100.0 * SUM(amount)
          / SUM(SUM(amount)) OVER (), 2)        AS pct_receita_total
FROM mongodb_iceberg_demo.orders
GROUP BY product
ORDER BY receita DESC;
