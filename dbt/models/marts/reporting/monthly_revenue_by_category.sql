-- Question: revenue and profit by category per month.
-- Rules at Gold: exclude the statuses of revenue_order_filter (Cancelled),
-- profit_at_current_cost = sale_price - the product's cost TODAY (not the cost on the sale day),
-- month = the order's month.
-- An item whose product is unknown still counts in revenue (category 'Unknown'), so the revenue
-- here adds up to daily_revenue.
-- An item without a cost adds 0 to profit_at_current_cost and is counted in n_items_without_cost.

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
