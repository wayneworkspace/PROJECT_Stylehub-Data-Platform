-- Grain: one row per order item. Adds the product's CURRENT cost and the order's date.
-- One row is one unit sold, so there is no quantity column.
-- Cost is the cost TODAY, not the cost on the day of the sale (see docs/design/DECISIONS.md).
-- cost is NULL when the product is not in dim_products; the warn test items_without_cost lists
-- them.
-- order_date comes from the ORDER: the item's own created_at can be later than its shipped_at,
-- so reports and partitions use the order's date.

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
