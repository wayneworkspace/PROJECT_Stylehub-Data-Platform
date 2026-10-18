-- One row per order; order_date is the day it was placed.

{{ config(
    partition_by={'field': 'order_date', 'data_type': 'date'}
) }}

SELECT
  order_id,
  user_id,
  status,
  total_amount,
  created_at,
  DATE(created_at) AS order_date
FROM {{ ref('stg_pg__orders') }}
