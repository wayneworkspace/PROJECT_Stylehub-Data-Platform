-- One row per order day; revenue sums item amounts of counted orders.

WITH items AS (
  SELECT
    order_date,
    order_id,
    amount
  FROM {{ ref('pg_fact_order_items') }}
  WHERE {{ pg_revenue_filter('status') }}
)

SELECT
  order_date,
  COUNT(DISTINCT order_id) AS n_orders,
  SUM(amount) AS revenue
FROM items
GROUP BY order_date
