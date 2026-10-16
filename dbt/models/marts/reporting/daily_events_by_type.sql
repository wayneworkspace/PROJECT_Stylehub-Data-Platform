-- Question: how many events, users and sessions per day and event type?
-- Reads only the columns it needs from the partitioned Silver table.
-- Incremental like fact_events: the first run builds everything, later runs rebuild the newest
-- event_date and the days before it (events_lookback_days), so a daily run does not scan all
-- 108 million events again. Rebuild everything with:
--   dbt build --full-refresh --select daily_events_by_type

{{ config(
    materialized='incremental',
    incremental_strategy='insert_overwrite',
    partition_by={'field': 'event_date', 'data_type': 'date'}
) }}

{% set lookback_days = var('events_lookback_days', 3) %}

SELECT
  event_date,
  event_type,
  COUNT(*) AS n_events,
  COUNT(DISTINCT user_id) AS n_users,
  COUNT(DISTINCT user_session) AS n_sessions
FROM {{ ref('fact_events') }}
{% if is_incremental() %}
-- _dbt_max_partition: the newest event_date already in this table (see fact_events.sql).
  WHERE
    event_date
    >= DATE_SUB(COALESCE(_dbt_max_partition, DATE '1970-01-01'), INTERVAL {{ lookback_days }} DAY)
{% endif %}
GROUP BY event_date, event_type
