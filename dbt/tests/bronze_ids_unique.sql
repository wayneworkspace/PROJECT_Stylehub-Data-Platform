-- Each id must appear once in the newest Bronze snapshot of every table.
-- Staging keeps only the newest row of each id, so a duplicate id in Bronze would be hidden there,
-- and the unique tests on staging run after that step (they can never fail). This one looks at
-- Bronze itself. It reads only Bronze, so dbt build runs it BEFORE the models.
-- Any row returned here is a failure.
{{ config(tags=['silver']) }}

WITH orders AS (
  {{ latest_bronze_snapshot('orders') }}
),

order_items AS (
  {{ latest_bronze_snapshot('order_items') }}
),

products AS (
  {{ latest_bronze_snapshot('products') }}
),

users AS (
  {{ latest_bronze_snapshot('users') }}
),

ids AS (
  SELECT
    'orders' AS table_name,
    order_id AS id
  FROM orders
  UNION ALL
  SELECT
    'order_items' AS table_name,
    id
  FROM order_items
  UNION ALL
  SELECT
    'products' AS table_name,
    id
  FROM products
  UNION ALL
  SELECT
    'users' AS table_name,
    id
  FROM users
)

SELECT
  table_name,
  id,
  COUNT(*) AS n_rows
FROM ids
GROUP BY table_name, id
HAVING
  id IS NULL
  OR COUNT(*) > 1
