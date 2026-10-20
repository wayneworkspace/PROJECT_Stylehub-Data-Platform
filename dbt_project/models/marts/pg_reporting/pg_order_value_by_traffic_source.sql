-- Average order value of counted orders, per customer traffic source.

WITH orders AS (
  SELECT
    o.total_amount,
    COALESCE(u.traffic_source, 'Unknown') AS traffic_source
  FROM {{ ref('pg_fact_orders') }} AS o
  LEFT JOIN {{ ref('pg_dim_users') }} AS u
    ON o.user_id = u.id
  WHERE {{ revenue_order_filter('o.status') }} AND NOT o.is_deleted
)

SELECT
  traffic_source,
  COUNT(*) AS n_orders,
  ROUND(AVG(total_amount), 2) AS avg_order_value
FROM orders
GROUP BY traffic_source
