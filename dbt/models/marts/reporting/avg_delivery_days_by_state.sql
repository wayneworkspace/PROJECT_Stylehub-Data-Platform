-- Question: average delivery time, from shipped to received, by state (session 5, exercise 2).
-- One row per shipped order (see fact_shipments). Only shipments that have both shipped_at and delivered_at are counted.

WITH delivered AS (
  SELECT
    u.state,
    TIMESTAMP_DIFF(s.delivered_at, s.shipped_at, HOUR) / 24 AS delivery_days
  FROM {{ ref('fact_shipments') }} AS s
  LEFT JOIN {{ ref('dim_users') }} AS u
    ON s.user_id = u.id
  WHERE s.shipped_at IS NOT NULL
    AND s.delivered_at IS NOT NULL
)
SELECT
  state,
  COUNT(*) AS n_shipments,
  AVG(delivery_days) AS avg_delivery_days
FROM delivered
GROUP BY state
