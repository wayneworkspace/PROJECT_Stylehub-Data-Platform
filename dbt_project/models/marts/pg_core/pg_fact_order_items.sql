-- One row per order item; total_cost uses today's product cost and
-- total_cost_at_sale the cost valid when the item was sold (SCD2 join).

-- Monthly partitions: daily ones held about 50 rows each and slowed every write.
{{ config(
    partition_by={'field': 'order_date', 'data_type': 'date', 'granularity': 'month'},
    cluster_by=['order_id', 'product_id']
) }}

WITH items AS (
  SELECT *
  FROM {{ ref('stg_pg__order_items') }}
),

orders AS (
  SELECT
    order_id,
    user_id,
    status,
    DATE(created_at) AS order_date
  FROM {{ ref('stg_pg__orders') }}
),

products AS (
  SELECT
    id AS product_id,
    cost
  FROM {{ ref('stg_pg__products') }}
),

history AS (
  SELECT
    product_key,
    product_id,
    cost,
    valid_from,
    valid_to
  FROM {{ ref('pg_dim_products_history') }}
)

SELECT
  i.id,
  i.order_id,
  o.user_id,
  i.product_id,
  h.product_key,  -- the product version on sale day (pg_dim_products_history)
  o.status,
  i.sale_price,
  i.quantity,
  i.amount,
  p.cost,
  i.quantity * p.cost AS total_cost,
  h.cost AS cost_at_sale,
  i.quantity * h.cost AS total_cost_at_sale,
  o.order_date,
  i.created_at,
  i.is_deleted,
  i.deleted_at
FROM items AS i
LEFT JOIN orders AS o
  ON i.order_id = o.order_id
LEFT JOIN products AS p
  ON i.product_id = p.product_id
LEFT JOIN history AS h
  ON
    i.product_id = h.product_id
    AND i.created_at >= h.valid_from
    AND i.created_at < h.valid_to
