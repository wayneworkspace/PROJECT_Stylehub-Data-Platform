-- Gold revenue must equal revenue worked out again from STAGING (Silver), by another route:
-- the item prices of orders that count as revenue (the same macro as Gold).
-- Gold reads the fact tables, this test reads
-- staging, so a mistake in a join or a filter of the marts shows up here.
-- IS DISTINCT FROM also fails when one side is NULL (an empty Gold table is a failure, not a pass).
-- Tagged gold because it needs daily_revenue, so it runs in the gold step.
{{ config(tags=['gold']) }}

WITH gold AS (
  SELECT SUM(revenue) AS total
  FROM {{ ref('daily_revenue') }}
),

staging AS (
  SELECT SUM(i.sale_price) AS total
  FROM {{ ref('stg_stylehub__order_items') }} AS i
  INNER JOIN {{ ref('stg_stylehub__orders') }} AS o
    ON i.order_id = o.order_id
  WHERE {{ revenue_order_filter('o.status') }}
)

SELECT
  gold.total AS gold_total,
  staging.total AS staging_total
FROM gold
CROSS JOIN staging
WHERE gold.total IS DISTINCT FROM staging.total
