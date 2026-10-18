-- One row per unit sold, partitioned by the order's date.
-- Columns are listed so new Bronze columns stay out of marts.

{{ config(
    partition_by={'field': 'order_date', 'data_type': 'date'},
    cluster_by=['order_id', 'product_id']
) }}

SELECT
  id,
  order_id,
  user_id,
  product_id,
  status,
  sale_price,
  cost,
  order_date,
  created_at,
  shipped_at,
  delivered_at,
  returned_at
FROM {{ ref('int_order_items_joined_to_products') }}
