-- Question: share of shipped orders that were returned, by the customer's state
-- (session 5, exercise 2).
-- Only an order that was shipped can be returned. A Cancelled or Processing order never left the
-- warehouse, so it is not in the denominator (it would make the rate look smaller than it is).
-- shipped_at is filled for Shipped, Complete and Returned orders (checked on the course data).

WITH orders AS (
  SELECT
    o.order_id,
    o.status,
    u.state
  FROM {{ ref('fact_orders') }} AS o
  LEFT JOIN {{ ref('dim_users') }} AS u
    ON o.user_id = u.id
  WHERE o.shipped_at IS NOT NULL
)

SELECT
  state,
  COUNT(*) AS n_orders,
  COUNTIF(status = 'Returned') AS n_returned,
  SAFE_DIVIDE(COUNTIF(status = 'Returned'), COUNT(*)) AS return_rate
FROM orders
GROUP BY state
