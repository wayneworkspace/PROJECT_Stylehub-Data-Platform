-- Question: revenue and profit by category per month (session 5, exercise 1).
-- Rules at Gold: exclude Cancelled orders, profit = sale_price - cost, month = the order's month.

WITH valid_orders AS (
  SELECT order_id, order_date
  FROM {{ ref('fact_orders') }}
  WHERE status != 'Cancelled'
),
items AS (
  SELECT
    i.product_id,
    i.sale_price,
    i.cost,
    o.order_date
  FROM {{ ref('fact_order_items') }} AS i
  INNER JOIN valid_orders AS o USING (order_id)
)
SELECT
  DATE_TRUNC(i.order_date, MONTH) AS month,
  p.category,
  SUM(i.sale_price) AS revenue,
  SUM(i.sale_price - i.cost) AS profit
FROM items AS i
INNER JOIN {{ ref('dim_products') }} AS p
  ON i.product_id = p.id
GROUP BY month, p.category
