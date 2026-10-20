-- One row per order; order_date is the day it was placed.

-- Monthly partitions: daily ones held about 50 rows each and slowed every write.
{{ config(
    partition_by={'field': 'order_date', 'data_type': 'date', 'granularity': 'month'}
) }}

SELECT
  order_id,
  user_id,
  status,
  total_amount,
  created_at,
  DATE(created_at) AS order_date,
  is_deleted,
  deleted_at
FROM {{ ref('stg_pg__orders') }}
