-- Grain: one row per product.
-- Bronze keeps every daily snapshot; Silver takes the most recently ingested snapshot of each id.
-- Check the column names against the real schema before running.

CREATE OR REPLACE TABLE `${project}.${silver}.dim_products` AS
WITH latest AS (
  SELECT *
  FROM `${project}.${bronze}.products`
  QUALIFY ROW_NUMBER() OVER (PARTITION BY id ORDER BY _ingested_at DESC) = 1
)
SELECT
  id,
  name,
  category,
  brand,
  CAST(cost AS NUMERIC) AS cost,
  CAST(retail_price AS NUMERIC) AS retail_price
FROM latest;
