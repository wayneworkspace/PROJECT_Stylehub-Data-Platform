-- One row per day; revenue from item rows, excluding revenue_order_filter statuses.
-- revenue is gross; net_revenue = revenue - returned_amount.

WITH valid_orders AS (
  SELECT
    order_id,
    order_date,
    status
  FROM {{ ref('fact_orders') }}
  WHERE {{ revenue_order_filter('status') }}
),

orders_by_day AS (
  SELECT
    order_date,
    COUNT(*) AS n_orders
  FROM valid_orders
  GROUP BY order_date
),

revenue_by_day AS (
  SELECT
    o.order_date,
    SUM(i.sale_price) AS revenue,
    SUM(IF(o.status = 'Returned', i.sale_price, 0)) AS returned_amount,
    SUM(IF(o.status = 'Returned', 0, i.sale_price)) AS net_revenue
  FROM {{ ref('fact_order_items') }} AS i
  INNER JOIN valid_orders AS o USING (order_id)
  GROUP BY o.order_date
)

SELECT
  d.order_date,
  d.n_orders,
  COALESCE(r.revenue, 0) AS revenue,
  COALESCE(r.returned_amount, 0) AS returned_amount,
  COALESCE(r.net_revenue, 0) AS net_revenue
FROM orders_by_day AS d
LEFT JOIN revenue_by_day AS r USING (order_date)
