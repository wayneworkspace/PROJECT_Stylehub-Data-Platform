-- Grain: one row per order, carrying user_id. Each id takes its latest version in Bronze.
-- order_date is the day the order was placed, used by Gold.

CREATE OR REPLACE TABLE `${project}.${silver}.fact_orders`
PARTITION BY order_date
AS
WITH latest AS (
  SELECT *
  FROM `${project}.${bronze}.orders`
  QUALIFY ROW_NUMBER() OVER (PARTITION BY id ORDER BY updated_at DESC, _ingested_at DESC) = 1
)
SELECT
  id,
  user_id,
  status,
  CAST(total_amount AS NUMERIC) AS total_amount,
  CAST(created_at AS TIMESTAMP) AS created_at,
  DATE(CAST(created_at AS TIMESTAMP)) AS order_date,
  CAST(updated_at AS TIMESTAMP) AS updated_at
FROM latest;
