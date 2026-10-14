-- Grain: one row per order. The CSV has no total_amount, so it is the sum of the item prices.
-- An order without items gets 0.

WITH totals AS (
  SELECT
    order_id,
    SUM(sale_price) AS total_amount
  FROM {{ ref('stg_stylehub__order_items') }}
  GROUP BY order_id
)
SELECT
  o.order_id,
  o.user_id,
  o.status,
  o.num_of_item,
  COALESCE(t.total_amount, 0) AS total_amount,
  o.created_at,
  o.shipped_at,
  o.delivered_at,
  o.returned_at
FROM {{ ref('stg_stylehub__orders') }} AS o
LEFT JOIN totals AS t USING (order_id)
