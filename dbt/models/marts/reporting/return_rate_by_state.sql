-- Question: share of returned orders by the customer's state (session 5, exercise 2).

WITH orders AS (
  SELECT o.order_id, o.status, u.state
  FROM {{ ref('fact_orders') }} AS o
  LEFT JOIN {{ ref('dim_users') }} AS u
    ON o.user_id = u.id
)
SELECT
  state,
  COUNT(*) AS n_orders,
  COUNTIF(status = 'Returned') AS n_returned,
  SAFE_DIVIDE(COUNTIF(status = 'Returned'), COUNT(*)) AS return_rate
FROM orders
GROUP BY state
