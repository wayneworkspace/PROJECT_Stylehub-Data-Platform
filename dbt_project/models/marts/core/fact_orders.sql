-- One row per order; order_date is the day it was placed.

{{ config(
    partition_by={'field': 'order_date', 'data_type': 'date'}
) }}

SELECT
  order_id,
  user_id,
  status,
  num_of_item,
  total_amount,
  created_at,
  DATE(created_at) AS order_date,
  shipped_at,
  delivered_at,
  returned_at
FROM {{ ref('int_orders_joined_to_item_totals') }}
