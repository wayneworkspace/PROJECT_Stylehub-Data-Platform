-- Grain: one row per order item. Adds the product's CURRENT cost to each item.
-- One row is one unit sold, so there is no quantity column.
-- Note: the item's created_at can be later than its shipped_at. Use the order's date for reports.

WITH items AS (
  SELECT *
  FROM {{ ref('stg_stylehub__order_items') }}
),
products AS (
  SELECT id AS product_id, cost
  FROM {{ ref('stg_stylehub__products') }}
)
SELECT
  i.*,
  p.cost AS cost
FROM items AS i
LEFT JOIN products AS p USING (product_id)
