-- Grain: one row per shipment. user_id comes from fact_orders (03_).
-- Check the column names against the real schema before running.

CREATE OR REPLACE TABLE `${project}.${silver}.fact_shipments` AS
WITH latest AS (
  SELECT *
  FROM `${project}.${bronze}.shipments`
  QUALIFY ROW_NUMBER() OVER (PARTITION BY id ORDER BY _ingested_at DESC) = 1
),
typed AS (
  SELECT
    id,
    order_id,
    CAST(shipped_at AS TIMESTAMP) AS shipped_at,
    CAST(delivered_at AS TIMESTAMP) AS delivered_at
  FROM latest
),
orders AS (
  SELECT id AS order_id, user_id
  FROM `${project}.${silver}.fact_orders`
)
SELECT
  t.*,
  o.user_id
FROM typed AS t
LEFT JOIN orders AS o USING (order_id);
