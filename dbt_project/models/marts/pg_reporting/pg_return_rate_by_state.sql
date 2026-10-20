-- Share of orders returned, per customer state.

WITH orders AS (
  SELECT
    o.status,
    COALESCE(u.state, 'Unknown') AS state
  FROM {{ ref('pg_fact_orders') }} AS o
  LEFT JOIN {{ ref('pg_dim_users') }} AS u
    ON o.user_id = u.id
  WHERE NOT o.is_deleted
)

SELECT
  state,
  COUNT(*) AS n_orders,
  COUNTIF(status = 'Returned') AS n_returned,
  ROUND(SAFE_DIVIDE(COUNTIF(status = 'Returned'), COUNT(*)), 4) AS return_rate
FROM orders
GROUP BY state
