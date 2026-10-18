-- One row per event (~108M). Events are loaded once, so tag events keeps it
-- out of daily runs; after a new events load: dbt build --select tag:events

{{ config(
    tags=['events'],
    materialized='incremental',
    incremental_strategy='insert_overwrite',
    partition_by={'field': 'event_date', 'data_type': 'date'},
    cluster_by=['event_type', 'product_id']
) }}

{% set lookback_days = var('events_lookback_days', 3) %}

SELECT
  event_id,
  user_id,
  product_id,
  event_type,
  category_code,
  brand,
  price,
  user_session,
  event_time,
  DATE(event_time) AS event_date
FROM {{ ref('stg_stylehub__events') }}
{% if is_incremental() %}
-- _dbt_max_partition: newest event_date here; an empty table reads everything.
  WHERE
    DATE(event_time)
    >= DATE_SUB(COALESCE(_dbt_max_partition, DATE '1970-01-01'), INTERVAL {{ lookback_days }} DAY)
{% endif %}
