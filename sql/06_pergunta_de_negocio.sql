-- A pergunta que ninguem roda no cluster operacional.
--
-- Varredura de 18 meses de historico: receita por UF e por mes, ticket medio,
-- taxa de cancelamento e participacao do app. Em producao isso e um relatorio
-- que concorreria com o trafego transacional -- aqui roda sobre o Iceberg no
-- S3, sem tocar o MongoDB.

SELECT
    region,
    date_format(date_trunc('month', orderdate), '%Y-%m')   AS mes,
    COUNT(*)                                               AS pedidos,
    ROUND(SUM(amount), 2)                                  AS receita,
    ROUND(AVG(amount), 2)                                  AS ticket_medio,
    ROUND(100.0 * COUNT_IF(status = 'CANCELADO')
          / COUNT(*), 2)                                   AS pct_cancelado,
    ROUND(100.0 * COUNT_IF(channel = 'APP')
          / COUNT(*), 2)                                   AS pct_app
FROM mongodb_iceberg_demo.orders
GROUP BY region, date_trunc('month', orderdate)
ORDER BY receita DESC
LIMIT 25;
