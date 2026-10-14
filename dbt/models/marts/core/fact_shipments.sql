-- Grain: one row per shipped order. There is no shipments file in the course data,
-- so shipments are built from the dates on the order (shipped_at, delivered_at, returned_at).

SELECT
  order_id,
  user_id,
  shipped_at,
  delivered_at,
  returned_at
FROM {{ ref('int_orders_joined_to_item_totals') }}
WHERE shipped_at IS NOT NULL
