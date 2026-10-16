-- Grain: one row per order item. One row is one unit sold, so there is no quantity column.
-- Measures: sale_price (additive), cost = the product's current cost (NULL if the product is
-- unknown).
-- Partitioned by the ORDER's date, the date that every report uses.
-- The columns are listed on purpose: a new column in Bronze must not reach the marts by accident.

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
