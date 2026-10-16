-- Business rule: count every order that is not in revenue_excluded_statuses (Cancelled by default,
-- see macros/revenue_order_filter.sql). One row per day.
-- Revenue is added up from the ITEM rows (fact_order_items), the same source as
-- monthly_revenue_by_category, so the two Gold tables share one lineage.
-- revenue is GROSS: Returned orders are inside it. returned_amount shows how much of it was
-- later returned, and net_revenue = revenue - returned_amount.
-- n_orders counts the counted orders, also an order that has no item row (it adds 0 revenue).

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
