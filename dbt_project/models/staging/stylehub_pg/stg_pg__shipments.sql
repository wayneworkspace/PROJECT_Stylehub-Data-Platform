-- One row per shipment: newest version across incremental Bronze.

WITH latest AS (
  {{ latest_pg_rows('pg_shipments') }}
)

SELECT
  id AS shipment_id,
  order_id,
  CAST(shipped_at AS TIMESTAMP) AS shipped_at,
  CAST(delivered_at AS TIMESTAMP) AS delivered_at,
  CAST(returned_at AS TIMESTAMP) AS returned_at,
  CAST(updated_at AS TIMESTAMP) AS updated_at
FROM latest
