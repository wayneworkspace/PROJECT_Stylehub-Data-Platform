-- Average hours from shipped to delivered, per customer state.

WITH delivered AS (
  SELECT
    s.delivery_hours,
    COALESCE(u.state, 'Unknown') AS state
  FROM {{ ref('pg_fact_shipments') }} AS s
  LEFT JOIN {{ ref('pg_dim_users') }} AS u
    ON s.user_id = u.id
  WHERE s.delivered_at IS NOT NULL
)

SELECT
  state,
  COUNT(*) AS n_delivered,
  ROUND(AVG(delivery_hours), 1) AS avg_delivery_hours
FROM delivered
GROUP BY state
