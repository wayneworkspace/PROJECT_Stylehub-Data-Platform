-- One row per shipped order, built from the order's dates.

SELECT
  order_id,
  user_id,
  shipped_at,
  delivered_at,
  returned_at
FROM {{ ref('int_orders_joined_to_item_totals') }}
WHERE shipped_at IS NOT NULL
