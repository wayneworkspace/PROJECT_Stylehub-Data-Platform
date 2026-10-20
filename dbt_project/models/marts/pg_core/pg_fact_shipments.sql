-- One row per shipment, with the customer and hours to deliver.

WITH shipments AS (
  SELECT *
  FROM {{ ref('stg_pg__shipments') }}
),

orders AS (
  SELECT
    order_id,
    user_id,
    is_deleted,
    deleted_at
  FROM {{ ref('stg_pg__orders') }}
)

SELECT
  s.shipment_id,
  s.order_id,
  o.user_id,
  s.shipped_at,
  s.delivered_at,
  s.returned_at,
  -- Deleted when the shipment or its order was deleted in Postgres.
  s.is_deleted OR COALESCE(o.is_deleted, FALSE) AS is_deleted,
  COALESCE(s.deleted_at, o.deleted_at) AS deleted_at,
  TIMESTAMP_DIFF(s.delivered_at, s.shipped_at, HOUR) AS delivery_hours
FROM shipments AS s
LEFT JOIN orders AS o
  ON s.order_id = o.order_id
