-- Business rule: count every order except Cancelled (session 3). One row per day.

WITH valid_orders AS (
  SELECT order_date, total_amount
  FROM {{ ref('fact_orders') }}
  WHERE status != 'Cancelled'
)
SELECT
  order_date,
  COUNT(*) AS n_orders,
  SUM(total_amount) AS revenue
FROM valid_orders
GROUP BY order_date
