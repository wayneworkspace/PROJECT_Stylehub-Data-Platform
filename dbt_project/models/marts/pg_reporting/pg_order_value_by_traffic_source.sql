-- Average order value of counted orders, per customer traffic source.

WITH orders AS (
  SELECT
    o.total_amount,
    COALESCE(u.traffic_source, 'Unknown') AS traffic_source
  FROM {{ ref('pg_fact_orders') }} AS o
  LEFT JOIN {{ ref('pg_dim_users') }} AS u
    ON o.user_id = u.id
  WHERE {{ pg_revenue_filter('o.status') }}
)

SELECT
  traffic_source,
  COUNT(*) AS n_orders,
  ROUND(AVG(total_amount), 2) AS avg_order_value
FROM orders
GROUP BY traffic_source
