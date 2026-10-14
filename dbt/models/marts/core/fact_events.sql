-- Grain: one row per event (a view, a cart add, a purchase, ...). About 108 million rows.
-- Incremental: the first run builds everything. Later runs rebuild the newest event_date and the
-- days before it (insert_overwrite replaces whole partitions), so a daily run scans a few days,
-- not 15 GB. Events that arrive late for one of those days are picked up.
-- The window is the dbt variable events_lookback_days (default 3, see dbt_project.yml).
-- An event that arrives later than the window is missed: rebuild everything with
--   dbt build --full-refresh --select fact_events
-- The cleaning (NULL category, price rounding) is done in stg_stylehub__events.

{{ config(
    materialized='incremental',
    incremental_strategy='insert_overwrite',
    partition_by={'field': 'event_date', 'data_type': 'date'},
    cluster_by=['event_type', 'product_id']
) }}

{% set lookback_days = var('events_lookback_days', 3) %}
{% if execute and is_incremental() %}
  {% set last_day = run_query('SELECT MAX(event_date) AS d FROM ' ~ this).columns[0][0] %}
{% endif %}

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
{% if execute and is_incremental() and last_day is not none %}
WHERE DATE(event_time) >= DATE_SUB(DATE '{{ last_day }}', INTERVAL {{ lookback_days }} DAY)
{% endif %}
