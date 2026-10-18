-- One row per order item; total_cost uses today's product cost.

{{ config(
    partition_by={'field': 'order_date', 'data_type': 'date'},
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
)

SELECT
  i.id,
  i.order_id,
  o.user_id,
  i.product_id,
  o.status,
  i.sale_price,
  i.quantity,
  i.amount,
  p.cost,
  i.quantity * p.cost AS total_cost,
  o.order_date,
  i.created_at
FROM items AS i
LEFT JOIN orders AS o
  ON i.order_id = o.order_id
LEFT JOIN products AS p
  ON i.product_id = p.product_id
