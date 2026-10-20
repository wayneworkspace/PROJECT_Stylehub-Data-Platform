-- Revenue and profit at today's cost, per month and category.

WITH items AS (
  SELECT
    DATE_TRUNC(i.order_date, MONTH) AS month,
    COALESCE(p.category, 'Unknown') AS category,
    i.amount,
    i.total_cost
  FROM {{ ref('pg_fact_order_items') }} AS i
  LEFT JOIN {{ ref('pg_dim_products') }} AS p
    ON i.product_id = p.id
  WHERE {{ pg_revenue_filter('i.status') }}
)

SELECT
  month,
  category,
  SUM(amount) AS revenue,
  SUM(IF(total_cost IS NULL, 0, amount - total_cost)) AS profit_at_current_cost,
  COUNTIF(total_cost IS NULL) AS n_items_without_cost
FROM items
GROUP BY month, category
