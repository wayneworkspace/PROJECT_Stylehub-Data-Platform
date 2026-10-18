-- One row per unit sold, with today's cost and order date.
-- cost is NULL for unknown products; order_date comes from the order.

WITH items AS (
  SELECT *
  FROM {{ ref('stg_stylehub__order_items') }}
),

orders AS (
  SELECT
    order_id,
    DATE(created_at) AS order_date
  FROM {{ ref('stg_stylehub__orders') }}
),

products AS (
  SELECT
    id AS product_id,
    cost
  FROM {{ ref('stg_stylehub__products') }}
)

SELECT
  i.id,
  i.order_id,
  i.user_id,
  i.product_id,
  i.status,
  i.sale_price,
  i.created_at,
  i.shipped_at,
  i.delivered_at,
  i.returned_at,
  o.order_date,
  p.cost
FROM items AS i
LEFT JOIN orders AS o
  ON i.order_id = o.order_id
LEFT JOIN products AS p
  ON i.product_id = p.product_id
