-- Silver must hold what the newest Bronze snapshot holds: the same number of rows, and the same
-- total of the money columns (rounded to 2 decimals like staging does).
-- gold_matches_silver only compares Gold with Silver, by the same rule. This test compares Silver
-- with Bronze, so a join or a filter that drops or doubles rows in staging, intermediate or the
-- marts shows up here. Bronze itself is checked against the Raw file when it is loaded.
-- Any row returned here is a failure. IS DISTINCT FROM also fails when only one side is NULL.
{{ config(tags=['silver']) }}

WITH bronze_orders AS (
  {{ latest_bronze_snapshot('orders') }}
),

bronze_order_items AS (
  {{ latest_bronze_snapshot('order_items') }}
),

bronze_products AS (
  {{ latest_bronze_snapshot('products') }}
),

bronze_users AS (
  {{ latest_bronze_snapshot('users') }}
),

bronze AS (
  SELECT
    'orders' AS table_name,
    COUNT(DISTINCT order_id) AS n_rows,
    CAST(NULL AS NUMERIC) AS total
  FROM bronze_orders
  UNION ALL
  SELECT
    'order_items' AS table_name,
    COUNT(DISTINCT id) AS n_rows,
    SUM(ROUND(CAST(sale_price AS NUMERIC), 2)) AS total
  FROM bronze_order_items
  UNION ALL
  SELECT
    'products' AS table_name,
    COUNT(DISTINCT id) AS n_rows,
    SUM(ROUND(CAST(cost AS NUMERIC), 2)) AS total
  FROM bronze_products
  UNION ALL
  SELECT
    'users' AS table_name,
    COUNT(DISTINCT id) AS n_rows,
    CAST(NULL AS NUMERIC) AS total
  FROM bronze_users
),

silver AS (
  SELECT
    'orders' AS table_name,
    COUNT(*) AS n_rows,
    CAST(NULL AS NUMERIC) AS total
  FROM {{ ref('fact_orders') }}
  UNION ALL
  SELECT
    'order_items' AS table_name,
    COUNT(*) AS n_rows,
    SUM(sale_price) AS total
  FROM {{ ref('fact_order_items') }}
  UNION ALL
  SELECT
    'products' AS table_name,
    COUNT(*) AS n_rows,
    SUM(cost) AS total
  FROM {{ ref('dim_products') }}
  UNION ALL
  SELECT
    'users' AS table_name,
    COUNT(*) AS n_rows,
    CAST(NULL AS NUMERIC) AS total
  FROM {{ ref('dim_users') }}
)

SELECT
  b.table_name,
  b.n_rows AS bronze_rows,
  s.n_rows AS silver_rows,
  b.total AS bronze_total,
  s.total AS silver_total
FROM bronze AS b
INNER JOIN silver AS s USING (table_name)
WHERE
  b.n_rows != s.n_rows
  OR b.total IS DISTINCT FROM s.total
