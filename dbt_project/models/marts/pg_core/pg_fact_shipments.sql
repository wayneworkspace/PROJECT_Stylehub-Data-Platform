-- One row per shipment, with the customer and hours to deliver.

WITH shipments AS (
  SELECT *
  FROM {{ ref('stg_pg__shipments') }}
),

orders AS (
  SELECT
    order_id,
    user_id
  FROM {{ ref('stg_pg__orders') }}
)

SELECT
  s.shipment_id,
  s.order_id,
  o.user_id,
  s.shipped_at,
  s.delivered_at,
  s.returned_at,
  s.is_deleted,
  s.deleted_at,
  TIMESTAMP_DIFF(s.delivered_at, s.shipped_at, HOUR) AS delivery_hours
FROM shipments AS s
LEFT JOIN orders AS o
  ON s.order_id = o.order_id
