-- Revenue and profit at today's cost, per month and category.
-- Unknown products count as 'Unknown', so revenue matches daily_revenue.

WITH valid_orders AS (
  SELECT order_id, order_date
  FROM {{ ref('fact_orders') }}
  WHERE {{ revenue_order_filter('status') }}
),

items AS (
  SELECT
    o.order_date,
    COALESCE(p.category, 'Unknown') AS category,
    i.sale_price,
    i.cost
  FROM {{ ref('fact_order_items') }} AS i
  INNER JOIN valid_orders AS o USING (order_id)
  LEFT JOIN {{ ref('dim_products') }} AS p
    ON i.product_id = p.id
)

SELECT
  DATE_TRUNC(order_date, MONTH) AS month,
  category,
  SUM(sale_price) AS revenue,
  SUM(IF(cost IS NULL, 0, sale_price - cost)) AS profit_at_current_cost,
  COUNTIF(cost IS NULL) AS n_items_without_cost
FROM items
GROUP BY month, category
