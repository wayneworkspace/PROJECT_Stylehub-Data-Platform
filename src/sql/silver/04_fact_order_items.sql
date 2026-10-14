-- Grain: one row per order item.
-- Measures: amount (additive), total_cost = the product's current cost * quantity.
-- Needs dim_products to exist (01_). Each id takes its latest version in Bronze.

CREATE OR REPLACE TABLE `${project}.${silver}.fact_order_items`
PARTITION BY DATE(created_at)
CLUSTER BY order_id, product_id
AS
WITH latest AS (
  SELECT *
  FROM `${project}.${bronze}.order_items`
  QUALIFY ROW_NUMBER() OVER (PARTITION BY id ORDER BY updated_at DESC, _ingested_at DESC) = 1
),
typed AS (
  SELECT
    id,
    order_id,
    product_id,
    CAST(sale_price AS NUMERIC) AS sale_price,
    CAST(quantity AS INT64) AS quantity,
    CAST(amount AS NUMERIC) AS amount,
    CAST(created_at AS TIMESTAMP) AS created_at,
    CAST(updated_at AS TIMESTAMP) AS updated_at
  FROM latest
),
products AS (
  SELECT id AS product_id, cost
  FROM `${project}.${silver}.dim_products`
)
SELECT
  t.*,
  t.quantity * p.cost AS total_cost
FROM typed AS t
LEFT JOIN products AS p USING (product_id);
